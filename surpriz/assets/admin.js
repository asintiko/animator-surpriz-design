/* ==========================================================================
   Админ-панель «Сюрприз» — логика.

   Работает без сервера. Данные — data/site.json.
   Сохранение:
     1. File System Access API — пишет прямо в файл сайта (Chrome/Edge);
     2. скачивание файла — универсальный фолбэк (Safari, Firefox);
     3. автосохранение черновика в localStorage.

   Изображения, добавленные через панель, кодируются в data:URL и хранятся
   внутри JSON. Это позволяет обойтись без сервера: файл остаётся
   самодостаточным. Перед вставкой картинка сжимается и (опционально)
   у неё вырезается однотонный фон.
   ========================================================================== */
(() => {
  "use strict";

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  const LS_DRAFT = "surpriz:draft";
  const LS_PREVIEW = "surpriz:preview";
  const LS_HISTORY = "surpriz:history";
  const LS_AUTH = "surpriz:auth";
  const ACCESS_CODE = "surpriz2026";   // меняется здесь же, в этом файле
  const HISTORY_LIMIT = 10;

  let site = null;
  let original = null;
  let dirty = false;
  let dirHandle = null;   // сохранённый доступ к папке сайта (Chrome/Edge)

  /* ── Утилиты ─────────────────────────────────────────────────────────── */

  const icon = (name) =>
    `<svg class="icon" aria-hidden="true"><use href="./assets/icons.svg#${name}"></use></svg>`;

  const esc = (s = "") =>
    String(s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const clone = (v) => JSON.parse(JSON.stringify(v));

  /** Транслитерация в slug: нужен для новых записей и имён файлов. */
  const slugify = (str) => {
    const map = {
      а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z",
      и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r",
      с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "ts", ч: "ch", ш: "sh",
      щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
    };
    return String(str).toLowerCase().trim()
      .split("").map((c) => (c in map ? map[c] : c)).join("")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || `item-${Date.now().toString(36)}`;
  };

  const toast = (text, kind = "ok") => {
    const icons = { ok: "i-check", warn: "i-shield", err: "i-close" };
    const el = document.createElement("div");
    el.className = `toast toast--${kind}`;
    el.innerHTML = `${icon(icons[kind])}<span>${esc(text)}</span>`;
    $("[data-toasts]").append(el);
    setTimeout(() => {
      el.style.transition = "opacity .25s, transform .25s";
      el.style.opacity = "0";
      el.style.transform = "translateX(16px)";
      setTimeout(() => el.remove(), 260);
    }, 3200);
  };

  const markDirty = (state = true) => {
    dirty = state;
    const box = $("[data-status]");
    box.classList.toggle("is-dirty", state);
    $("[data-status-text]").textContent = state ? "Есть несохранённые правки" : "Всё сохранено";
    if (state) {
      try { localStorage.setItem(LS_DRAFT, JSON.stringify(site)); } catch { /* переполнение — не критично */ }
    }
  };

  /* ── Обработка изображений ───────────────────────────────────────────── */

  /**
   * Уменьшает картинку и кодирует в data:URL (WebP, с фолбэком на PNG для alpha).
   * Прозрачность сохраняется, поэтому вырезанные PNG остаются вырезанными.
   */
  const processImage = (file, { maxSide = 900, cutout = false } = {}) =>
    new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Не удалось прочитать файл"));
      reader.onload = () => {
        const img = new Image();
        img.onerror = () => reject(new Error("Файл не похож на изображение"));
        img.onload = () => {
          const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
          const w = Math.round(img.width * scale);
          const h = Math.round(img.height * scale);
          const canvas = document.createElement("canvas");
          canvas.width = w;
          canvas.height = h;
          const ctx = canvas.getContext("2d", { willReadFrequently: cutout });
          ctx.drawImage(img, 0, 0, w, h);
          if (cutout) removeFlatBackground(ctx, w, h);
          // WebP держит альфу и весит меньше PNG; при отказе — PNG.
          let url = canvas.toDataURL("image/webp", 0.86);
          if (!url.startsWith("data:image/webp")) url = canvas.toDataURL("image/png");
          resolve({ src: url, w, h });
        };
        img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });

  /**
   * Вырезание однотонного фона прямо в браузере.
   * Алгоритм: цвет фона берём как медиану по рамке кадра, затем заливкой
   * от границ помечаем связную область похожего цвета и делаем её прозрачной.
   * Это заметно аккуратнее «удалить все похожие пиксели», потому что не
   * пробивает дыры в костюме того же оттенка.
   */
  function removeFlatBackground(ctx, w, h) {
    const data = ctx.getImageData(0, 0, w, h);
    const px = data.data;
    const band = Math.max(2, Math.round(Math.min(w, h) * 0.02));

    const samples = [[], [], []];
    for (let y = 0; y < h; y += 2) {
      for (let x = 0; x < w; x += 2) {
        if (x >= band && x < w - band && y >= band && y < h - band) continue;
        const i = (y * w + x) * 4;
        samples[0].push(px[i]); samples[1].push(px[i + 1]); samples[2].push(px[i + 2]);
      }
    }
    if (!samples[0].length) return;
    const median = samples.map((arr) => {
      arr.sort((a, b) => a - b);
      return arr[arr.length >> 1];
    });

    const tolerance = 42;             // порог «это фон» в единицах 0-255
    const soft = tolerance * 1.9;     // зона мягкого края
    const visited = new Uint8Array(w * h);
    const stack = [];

    const near = (i) => {
      const d = Math.hypot(px[i] - median[0], px[i + 1] - median[1], px[i + 2] - median[2]);
      return d;
    };

    const push = (x, y) => {
      if (x < 0 || y < 0 || x >= w || y >= h) return;
      const p = y * w + x;
      if (visited[p]) return;
      if (near(p * 4) > soft) return;
      visited[p] = 1;
      stack.push(p);
    };

    for (let x = 0; x < w; x += 1) { push(x, 0); push(x, h - 1); }
    for (let y = 0; y < h; y += 1) { push(0, y); push(w - 1, y); }

    while (stack.length) {
      const p = stack.pop();
      const x = p % w;
      const y = (p - x) / w;
      const i = p * 4;
      const d = near(i);
      // Внутри порога — полностью прозрачно, в переходной зоне — плавно.
      px[i + 3] = d <= tolerance ? 0 : Math.round(255 * Math.min(1, (d - tolerance) / (soft - tolerance)));
      push(x - 1, y); push(x + 1, y); push(x, y - 1); push(x, y + 1);
    }

    ctx.putImageData(data, 0, 0);
  }

  const pickImage = () => new Promise((resolve) => {
    const input = $("[data-file-image]");
    input.value = "";
    input.onchange = () => resolve(input.files[0] || null);
    input.click();
  });

  /* ── Загрузка и сохранение ───────────────────────────────────────────── */

  async function loadData() {
    let base = null;
    try {
      const res = await fetch("./data/site.json", { cache: "no-cache" });
      if (res.ok) base = await res.json();
    } catch { /* file:// — читаем только черновик */ }

    original = base ? clone(base) : null;

    let draft = null;
    try {
      const raw = localStorage.getItem(LS_DRAFT);
      if (raw) draft = JSON.parse(raw);
    } catch { /* повреждённый черновик игнорируем */ }

    if (draft) {
      site = draft;
      markDirty(true);
      toast("Загружен сохранённый черновик", "warn");
    } else if (base) {
      site = base;
      markDirty(false);
    } else {
      toast("Не удалось прочитать data/site.json. Откройте сайт через локальный сервер или загрузите файл вручную.", "err");
      site = emptySite();
    }

    // Подстраховка: гарантируем наличие всех коллекций.
    site.meta ||= {};
    site.hero ||= { usp: [], layers: [] };
    site.hero.usp ||= [];
    site.hero.layers ||= [];
    site.stats ||= [];
    site.categories ||= [];
    site.shows ||= [];
    site.characters ||= [];
    site.proof ||= [];
    site.steps ||= [];
    site.faq ||= [];
  }

  const emptySite = () => ({
    version: "6.0",
    meta: {}, hero: { usp: [], layers: [] }, stats: [],
    categories: [{ id: "all", label: "Все", icon: "i-sparkles" }],
    shows: [], characters: [], proof: [], steps: [], faq: [],
  });

  const serialize = () => JSON.stringify(site, null, 1);

  function pushHistory() {
    try {
      const list = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]");
      list.unshift({ at: Date.now(), data: site });
      localStorage.setItem(LS_HISTORY, JSON.stringify(list.slice(0, HISTORY_LIMIT)));
    } catch {
      // localStorage переполнен (много data:URL картинок) — историю чистим.
      try { localStorage.removeItem(LS_HISTORY); } catch { /* нечего делать */ }
    }
  }

  async function saveToFile() {
    if (!("showDirectoryPicker" in window)) {
      toast("Этот браузер не умеет писать в файл. Используйте «Скачать site.json».", "warn");
      return downloadJson();
    }
    try {
      if (!dirHandle) {
        toast("Выберите папку сайта — ту, где лежит index.html", "warn");
        dirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
      }
      const perm = await dirHandle.requestPermission({ mode: "readwrite" });
      if (perm !== "granted") throw new Error("Нет доступа на запись");

      const dataDir = await dirHandle.getDirectoryHandle("data", { create: true });
      const fileHandle = await dataDir.getFileHandle("site.json", { create: true });
      const writable = await fileHandle.createWritable();
      await writable.write(serialize());
      await writable.close();

      pushHistory();
      localStorage.removeItem(LS_DRAFT);
      markDirty(false);
      toast("Файл data/site.json обновлён");
    } catch (err) {
      if (err?.name === "AbortError") return;
      console.error(err);
      toast(`Не удалось записать файл: ${err.message}`, "err");
    }
  }

  function downloadJson() {
    const blob = new Blob([serialize()], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "site.json";
    a.click();
    URL.revokeObjectURL(a.href);
    pushHistory();
    toast("Файл скачан. Положите его в папку data/ вместо старого.");
  }

  function importJson() {
    const input = $("[data-file-json]");
    input.value = "";
    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      try {
        const parsed = JSON.parse(await file.text());
        if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.characters)) {
          throw new Error("Файл не похож на site.json");
        }
        site = parsed;
        markDirty(true);
        renderAll();
        toast("Данные загружены из файла");
      } catch (err) {
        toast(`Ошибка чтения: ${err.message}`, "err");
      }
    };
    input.click();
  }

  function openPreview() {
    try {
      localStorage.setItem(LS_PREVIEW, JSON.stringify(site));
      window.open("./index.html", "_blank", "noopener");
      toast("Предпросмотр открыт в новой вкладке");
    } catch {
      toast("Не хватает места в браузере для предпросмотра. Сохраните файл и откройте сайт.", "err");
    }
  }

  /* ── Модальное окно ──────────────────────────────────────────────────── */

  const modal = {
    el: null,
    onSave: null,
    onDelete: null,

    open({ title, body, onSave, onDelete = null }) {
      this.el ||= $("[data-modal]");
      $("[data-modal-title]").textContent = title;
      $("[data-modal-body]").innerHTML = body;
      this.onSave = onSave;
      this.onDelete = onDelete;
      $("[data-modal-delete]").hidden = !onDelete;
      this.el.classList.add("is-open");
      // Фокус на первое поле — можно сразу печатать.
      setTimeout(() => $("[data-modal-body] input, [data-modal-body] textarea")?.focus(), 60);
    },

    close() {
      this.el?.classList.remove("is-open");
      this.onSave = null;
      this.onDelete = null;
    },
  };

  /* ── Формы (конструкторы разметки) ───────────────────────────────────── */

  const fieldText = (label, name, value = "", { type = "text", note = "" } = {}) => `
    <div class="field">
      <label for="f-${name}">${esc(label)}</label>
      <input type="${type}" id="f-${name}" name="${name}" value="${esc(value)}">
      ${note ? `<span class="field__note">${note}</span>` : ""}
    </div>`;

  const fieldArea = (label, name, value = "", note = "") => `
    <div class="field">
      <label for="f-${name}">${esc(label)}</label>
      <textarea id="f-${name}" name="${name}">${esc(value)}</textarea>
      ${note ? `<span class="field__note">${note}</span>` : ""}
    </div>`;

  const ICON_CHOICES = [
    "i-sparkles", "i-spark", "i-star", "i-heart", "i-gift", "i-cake", "i-balloon",
    "i-snowflake", "i-ribbon", "i-mask", "i-crown", "i-camera", "i-characters",
    "i-shield", "i-clock", "i-wallet", "i-calendar", "i-check", "i-play", "i-filter",
  ];

  const fieldIcon = (label, name, value = "i-sparkles") => `
    <div class="field">
      <label for="f-${name}">${esc(label)}</label>
      <select id="f-${name}" name="${name}">
        ${ICON_CHOICES.map((ic) =>
          `<option value="${ic}"${ic === value ? " selected" : ""}>${ic.replace("i-", "")}</option>`).join("")}
      </select>
    </div>`;

  /** Блок загрузки изображения: превью на шахматке + опция вырезки фона. */
  const fieldImage = (image = null, { cutoutOption = true } = {}) => `
    <div class="field">
      <span>Изображение</span>
      <div class="preview" data-img-preview>
        ${image?.src
          ? `<img src="${esc(image.src)}" alt="">`
          : `<span style="color:var(--a-muted);font-size:13px">Пока не выбрано</span>`}
      </div>
      <div class="drop" data-img-drop tabindex="0" role="button">
        ${icon("i-upload")}
        <b>Выбрать файл или перетащить сюда</b>
        <span>JPG, PNG или WebP. Уменьшим и сожмём автоматически.</span>
      </div>
      ${cutoutOption ? `
      <label class="check" style="margin-top:8px">
        <input type="checkbox" name="cutout" checked>
        ${icon("i-sparkles")} Вырезать однотонный фон
      </label>
      <span class="field__note">Работает для студийных кадров на ровном фоне.
      Для сложных фотографий снимите галочку.</span>` : ""}
    </div>`;

  /** Навешивает обработчики на блок загрузки внутри модального окна. */
  function bindImageField(state) {
    const drop = $("[data-img-drop]");
    const preview = $("[data-img-preview]");
    if (!drop) return;

    const apply = async (file) => {
      if (!file) return;
      const cutout = $('[data-modal-body] input[name="cutout"]')?.checked ?? false;
      preview.innerHTML = `<span style="color:var(--a-muted);font-size:13px">Обрабатываю…</span>`;
      try {
        const result = await processImage(file, { cutout });
        state.image = { src: result.src, w: result.w, h: result.h, srcset: "" };
        preview.innerHTML = `<img src="${result.src}" alt="">`;
        toast(cutout ? "Фон вырезан" : "Изображение готово");
      } catch (err) {
        preview.innerHTML = `<span style="color:var(--a-danger);font-size:13px">${esc(err.message)}</span>`;
      }
    };

    drop.addEventListener("click", async () => apply(await pickImage()));
    drop.addEventListener("keydown", async (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); apply(await pickImage()); }
    });
    ["dragenter", "dragover"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("is-over"); }));
    ["dragleave", "drop"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("is-over"); }));
    drop.addEventListener("drop", (e) => apply(e.dataTransfer.files[0]));
  }

  const formValues = () => {
    const out = {};
    $$("[data-modal-body] [name]").forEach((el) => {
      out[el.name] = el.type === "checkbox" ? el.checked : el.value.trim();
    });
    return out;
  };

  /* ── Редакторы сущностей ─────────────────────────────────────────────── */

  function editShow(index) {
    const isNew = index === -1;
    const item = isNew
      ? { slug: "", name: "", summary: "", price: "от 1 000 000 сум", duration: "1 час",
          icon: "i-sparkles", accent: "#c94a16", image: null, route: "", builder_url: "", gallery: [] }
      : clone(site.shows[index]);
    const state = { image: item.image };

    modal.open({
      title: isNew ? "Новое шоу" : `Шоу: ${item.name}`,
      body: `
        ${fieldText("Название", "name", item.name)}
        ${fieldArea("Описание", "summary", item.summary)}
        <div class="row row--3">
          ${fieldText("Цена", "price", item.price)}
          ${fieldText("Длительность", "duration", item.duration)}
          ${fieldText("Цвет акцента", "accent", item.accent, { type: "text", note: "HEX, например #c94a16" })}
        </div>
        ${fieldIcon("Иконка", "icon", item.icon)}
        ${fieldImage(item.image)}
        ${fieldText("Ссылка на страницу шоу", "route", item.route, { type: "url" })}
        ${fieldText("Ссылка «Добавить в праздник»", "builder_url", item.builder_url, { type: "url" })}
      `,
      onSave: () => {
        const v = formValues();
        if (!v.name) { toast("Введите название", "err"); return false; }
        if (!state.image?.src) { toast("Добавьте изображение шоу", "err"); return false; }
        const slug = item.slug || slugify(v.name);
        const next = {
          slug, name: v.name, summary: v.summary, price: v.price, duration: v.duration,
          icon: v.icon, accent: v.accent || "#c94a16",
          image: state.image, lqip: "",
          route: v.route || `${site.meta.site_url || ""}show-programs/${slug}/`,
          builder_url: v.builder_url || `${site.meta.builder_url || ""}?program=${slug}`,
          gallery: item.gallery || [],
        };
        if (isNew) site.shows.push(next); else site.shows[index] = next;
        return true;
      },
      onDelete: isNew ? null : () => { site.shows.splice(index, 1); },
    });
    bindImageField(state);
  }

  function editCharacter(index) {
    const isNew = index === -1;
    const item = isNew
      ? { slug: "", name: "", description: "", categories: [], image: null, gallery: [] }
      : clone(site.characters[index]);
    const state = { image: item.image };

    const cats = site.categories.filter((c) => c.id !== "all");

    modal.open({
      title: isNew ? "Новый персонаж" : `Персонаж: ${item.name}`,
      body: `
        ${fieldText("Имя", "name", item.name)}
        ${fieldArea("Короткое описание", "description", item.description,
          "1–2 предложения: что делает персонаж на празднике.")}
        <div class="field">
          <span>Категории</span>
          <div class="checks">
            ${cats.map((c) => `
              <label class="check">
                <input type="checkbox" name="cat:${c.id}"${item.categories.includes(c.id) ? " checked" : ""}>
                ${icon(c.icon || "i-star")} ${esc(c.label)}
              </label>`).join("")}
          </div>
        </div>
        ${fieldImage(item.image)}
      `,
      onSave: () => {
        const v = formValues();
        if (!v.name) { toast("Введите имя персонажа", "err"); return false; }
        if (!state.image?.src) { toast("Добавьте фотографию", "err"); return false; }
        const categories = Object.keys(v)
          .filter((k) => k.startsWith("cat:") && v[k])
          .map((k) => k.slice(4));
        if (!categories.length) { toast("Выберите хотя бы одну категорию", "err"); return false; }
        const next = {
          slug: item.slug || slugify(v.name),
          name: v.name,
          description: v.description,
          categories,
          image: state.image,
          lqip: "",
          source: item.source || "",
          gallery: item.gallery || [],
        };
        if (isNew) site.characters.push(next); else site.characters[index] = next;
        return true;
      },
      onDelete: isNew ? null : () => { site.characters.splice(index, 1); },
    });
    bindImageField(state);
  }

  function editCategory(index) {
    const isNew = index === -1;
    const item = isNew ? { id: "", label: "", icon: "i-star" } : clone(site.categories[index]);
    const isAll = item.id === "all";

    modal.open({
      title: isNew ? "Новая категория" : `Категория: ${item.label}`,
      body: `
        ${fieldText("Название", "label", item.label)}
        ${fieldIcon("Иконка", "icon", item.icon)}
        ${isAll ? `<div class="note note--warn">${icon("i-shield")}
          <span>Это служебная категория «Все» — её нельзя удалить, она всегда первая.</span></div>` : ""}
      `,
      onSave: () => {
        const v = formValues();
        if (!v.label) { toast("Введите название", "err"); return false; }
        const next = { id: item.id || slugify(v.label), label: v.label, icon: v.icon };
        if (isNew) site.categories.push(next); else site.categories[index] = next;
        return true;
      },
      onDelete: (isNew || isAll) ? null : () => {
        const id = site.categories[index].id;
        site.categories.splice(index, 1);
        // Чистим ссылки на удалённую категорию у персонажей.
        site.characters.forEach((ch) => {
          ch.categories = ch.categories.filter((c) => c !== id);
        });
      },
    });
  }

  function editProof(index) {
    const isNew = index === -1;
    const item = isNew ? { id: "", caption: "", image: null } : clone(site.proof[index]);
    const state = { image: item.image };

    modal.open({
      title: isNew ? "Новый кадр" : "Кадр галереи",
      body: `
        ${fieldText("Подпись", "caption", item.caption)}
        ${fieldImage(item.image, { cutoutOption: false })}
      `,
      onSave: () => {
        const v = formValues();
        if (!state.image?.src) { toast("Добавьте изображение", "err"); return false; }
        const next = {
          id: item.id || `shot-${Date.now().toString(36)}`,
          caption: v.caption,
          image: state.image,
          lqip: "",
        };
        if (isNew) site.proof.push(next); else site.proof[index] = next;
        return true;
      },
      onDelete: isNew ? null : () => { site.proof.splice(index, 1); },
    });
    bindImageField(state);
  }

  function editSimple({ list, index, title, fields, build }) {
    const isNew = index === -1;
    const item = isNew ? {} : clone(list[index]);
    modal.open({
      title,
      body: fields(item),
      onSave: () => {
        const v = formValues();
        const next = build(v, item);
        if (!next) return false;
        if (isNew) list.push(next); else list[index] = next;
        return true;
      },
      onDelete: isNew ? null : () => { list.splice(index, 1); },
    });
  }

  const editUsp = (i) => editSimple({
    list: site.hero.usp, index: i, title: "Преимущество",
    fields: (it) => fieldText("Текст", "text", it.text || "") + fieldIcon("Иконка", "icon", it.icon || "i-check"),
    build: (v) => (v.text ? { icon: v.icon, text: v.text } : (toast("Введите текст", "err"), null)),
  });

  const editStat = (i) => editSimple({
    list: site.stats, index: i, title: "Счётчик",
    fields: (it) => `
      <div class="row row--2">
        ${fieldText("Число", "value", it.value ?? "", { type: "number" })}
        ${fieldText("Подпись", "label", it.label || "")}
      </div>
      ${fieldIcon("Иконка", "icon", it.icon || "i-star")}`,
    build: (v) => (v.label && v.value !== ""
      ? { value: Number(v.value), label: v.label, icon: v.icon }
      : (toast("Заполните число и подпись", "err"), null)),
  });

  const editStep = (i) => editSimple({
    list: site.steps, index: i, title: "Шаг заказа",
    fields: (it) => fieldText("Заголовок", "title", it.title || "")
      + fieldArea("Описание", "text", it.text || "")
      + fieldIcon("Иконка", "icon", it.icon || "i-check"),
    build: (v) => (v.title ? { icon: v.icon, title: v.title, text: v.text } : (toast("Введите заголовок", "err"), null)),
  });

  const editFaq = (i) => editSimple({
    list: site.faq, index: i, title: "Вопрос и ответ",
    fields: (it) => fieldText("Вопрос", "q", it.q || "") + fieldArea("Ответ", "a", it.a || ""),
    build: (v) => (v.q && v.a ? { q: v.q, a: v.a } : (toast("Заполните вопрос и ответ", "err"), null)),
  });

  /* ── Отрисовка списков ───────────────────────────────────────────────── */

  const emptyBlock = (text) => `
    <div class="empty">${icon("i-search")}<p>${esc(text)}</p></div>`;

  const itemRow = ({ index, thumb, cover, name, meta, tags = [], kind }) => `
    <div class="item" draggable="true" data-index="${index}" data-kind="${kind}">
      <span class="item__grip" aria-hidden="true">${icon("i-drag")}</span>
      <span class="item__thumb${cover ? " item__thumb--cover" : ""}"
            style="${thumb ? `background-image:url('${esc(thumb)}')` : ""}"></span>
      <span>
        <span class="item__name">${esc(name)}</span>
        ${meta ? `<span class="item__meta">${esc(meta)}</span>` : ""}
        ${tags.length ? `<span class="item__tags">${tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</span>` : ""}
      </span>
      <span class="item__actions">
        <button class="btn btn--ghost btn--sm btn--icon" type="button" data-edit="${index}" aria-label="Изменить">
          ${icon("i-edit")}
        </button>
      </span>
    </div>`;

  const searchState = { shows: "", characters: "" };
  const filterState = { characters: "all" };

  function renderShows() {
    const box = $('[data-list="shows"]');
    const q = searchState.shows.toLowerCase();
    const rows = site.shows
      .map((s, i) => ({ s, i }))
      .filter(({ s }) => !q || s.name.toLowerCase().includes(q));
    box.innerHTML = rows.length
      ? rows.map(({ s, i }) => itemRow({
          index: i, kind: "shows", thumb: s.image?.src, cover: true,
          name: s.name, meta: `${s.duration} · ${s.price}`,
        })).join("")
      : emptyBlock("Шоу не найдены");
  }

  function renderCharacters() {
    const box = $('[data-list="characters"]');
    const q = searchState.characters.toLowerCase();
    const cat = filterState.characters;
    const labels = new Map(site.categories.map((c) => [c.id, c.label]));
    const rows = site.characters
      .map((c, i) => ({ c, i }))
      .filter(({ c }) => (!q || c.name.toLowerCase().includes(q))
        && (cat === "all" || c.categories.includes(cat)));
    box.innerHTML = rows.length
      ? rows.map(({ c, i }) => itemRow({
          index: i, kind: "characters", thumb: c.image?.src, cover: false,
          name: c.name, meta: c.description,
          tags: c.categories.filter((x) => x !== "all").map((x) => labels.get(x) || x),
        })).join("")
      : emptyBlock("Персонажи не найдены");
  }

  function renderCategories() {
    const box = $('[data-list="categories"]');
    box.innerHTML = site.categories.map((c, i) => {
      const used = site.characters.filter((ch) => ch.categories.includes(c.id)).length;
      return itemRow({
        index: i, kind: "categories", thumb: "", cover: false,
        name: c.label,
        meta: c.id === "all" ? "служебная — показывает всех" : `персонажей: ${used}`,
      });
    }).join("");
  }

  function renderProof() {
    const box = $('[data-list="proof"]');
    box.innerHTML = site.proof.length
      ? site.proof.map((p, i) => itemRow({
          index: i, kind: "proof", thumb: p.image?.src, cover: true,
          name: p.caption || "Без подписи",
        })).join("")
      : emptyBlock("Кадров пока нет");
  }

  const renderMini = (key, list, format) => {
    const box = $(`[data-list="${key}"]`);
    if (!box) return;
    box.innerHTML = list.length
      ? list.map((item, i) => `
        <div class="item" draggable="true" data-index="${i}" data-kind="${key}"
             style="grid-template-columns:auto minmax(0,1fr) auto">
          <span class="item__grip" aria-hidden="true">${icon("i-drag")}</span>
          <span>
            <span class="item__name">${esc(format(item).name)}</span>
            ${format(item).meta ? `<span class="item__meta">${esc(format(item).meta)}</span>` : ""}
          </span>
          <span class="item__actions">
            <button class="btn btn--ghost btn--sm btn--icon" type="button" data-edit="${i}" aria-label="Изменить">
              ${icon("i-edit")}
            </button>
          </span>
        </div>`).join("")
      : emptyBlock("Пока пусто");
  };

  function renderHistory() {
    const box = $('[data-list="history"]');
    let list = [];
    try { list = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]"); } catch { /* нет истории */ }
    box.innerHTML = list.length
      ? list.map((entry, i) => `
        <div class="item" style="grid-template-columns:auto minmax(0,1fr) auto">
          <span class="item__grip" aria-hidden="true">${icon("i-clock")}</span>
          <span>
            <span class="item__name">${new Date(entry.at).toLocaleString("ru-RU")}</span>
            <span class="item__meta">персонажей: ${entry.data?.characters?.length ?? 0},
              шоу: ${entry.data?.shows?.length ?? 0}</span>
          </span>
          <span class="item__actions">
            <button class="btn btn--ghost btn--sm" type="button" data-restore="${i}">Восстановить</button>
          </span>
        </div>`).join("")
      : emptyBlock("Сохранений пока не было");
  }

  function renderBindings() {
    $$("[data-bind]").forEach((el) => {
      const path = el.dataset.bind.split(".");
      let value = site;
      for (const key of path) value = value?.[key];
      el.value = value ?? "";
    });
  }

  function renderTiles() {
    $("[data-tiles]").innerHTML = [
      { v: site.characters.length, l: "персонажей в каталоге" },
      { v: site.shows.length, l: "шоу-программ" },
      { v: site.categories.length - 1, l: "категорий" },
      { v: site.proof.length, l: "кадров в галерее" },
      { v: site.faq.length, l: "вопросов в FAQ" },
    ].map((t) => `<div class="tile"><b>${t.v}</b><span>${t.l}</span></div>`).join("");
  }

  function renderCounts() {
    $("[data-count-shows]").textContent = site.shows.length;
    $("[data-count-characters]").textContent = site.characters.length;
    $("[data-count-categories]").textContent = site.categories.length;
    $("[data-count-proof]").textContent = site.proof.length;
    $("[data-count-faq]").textContent = site.faq.length;
  }

  function renderCategoryFilter() {
    const sel = $('[data-filter="characters"]');
    sel.innerHTML = site.categories
      .map((c) => `<option value="${c.id}"${c.id === filterState.characters ? " selected" : ""}>${esc(c.label)}</option>`)
      .join("");
  }

  function renderAll() {
    renderTiles();
    renderCounts();
    renderCategoryFilter();
    renderShows();
    renderCharacters();
    renderCategories();
    renderProof();
    renderMini("usp", site.hero.usp, (it) => ({ name: it.text, meta: it.icon }));
    renderMini("stats", site.stats, (it) => ({ name: `${it.value} — ${it.label}`, meta: it.icon }));
    renderMini("steps", site.steps, (it) => ({ name: it.title, meta: it.text }));
    renderMini("faq", site.faq, (it) => ({ name: it.q, meta: it.a }));
    renderHistory();
    renderBindings();
  }

  /* ── Перетаскивание для сортировки ───────────────────────────────────── */

  const COLLECTIONS = {
    shows: () => site.shows,
    characters: () => site.characters,
    categories: () => site.categories,
    proof: () => site.proof,
    usp: () => site.hero.usp,
    stats: () => site.stats,
    steps: () => site.steps,
    faq: () => site.faq,
  };

  function initDrag() {
    let dragged = null;

    document.addEventListener("dragstart", (e) => {
      const item = e.target.closest(".item[draggable]");
      if (!item) return;
      dragged = item;
      item.classList.add("is-dragging");
      e.dataTransfer.effectAllowed = "move";
      // Safari требует непустые данные, иначе drop не срабатывает.
      e.dataTransfer.setData("text/plain", item.dataset.index);
    });

    document.addEventListener("dragend", () => {
      dragged?.classList.remove("is-dragging");
      $$(".item.is-over").forEach((el) => el.classList.remove("is-over"));
      dragged = null;
    });

    document.addEventListener("dragover", (e) => {
      const over = e.target.closest(".item[draggable]");
      if (!dragged || !over || over === dragged) return;
      if (over.dataset.kind !== dragged.dataset.kind) return;
      e.preventDefault();
      $$(".item.is-over").forEach((el) => el.classList.remove("is-over"));
      over.classList.add("is-over");
    });

    document.addEventListener("drop", (e) => {
      const over = e.target.closest(".item[draggable]");
      if (!dragged || !over || over === dragged) return;
      const kind = dragged.dataset.kind;
      if (over.dataset.kind !== kind) return;
      e.preventDefault();

      const list = COLLECTIONS[kind]?.();
      if (!list) return;
      const from = Number(dragged.dataset.index);
      const to = Number(over.dataset.index);
      const [moved] = list.splice(from, 1);
      list.splice(to, 0, moved);

      markDirty(true);
      renderAll();
      toast("Порядок изменён");
    });
  }

  /* ── Навигация и общие события ───────────────────────────────────────── */

  const TAB_TITLES = {
    dashboard: "Обзор",
    shows: "Шоу-программы",
    characters: "Персонажи",
    categories: "Категории",
    gallery: "Живые кадры",
    texts: "Тексты и первый экран",
    faq: "Вопросы и шаги",
    settings: "Контакты и SEO",
    backup: "Сохранение",
  };

  function initTabs() {
    $$("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.tab;
        $$("[data-tab]").forEach((b) => b.classList.toggle("is-active", b === btn));
        $$("[data-panel]").forEach((p) => p.classList.toggle("is-active", p.dataset.panel === tab));
        $("[data-topbar-title]").textContent = TAB_TITLES[tab] || "";
        $("[data-side]").classList.remove("is-open");
        $("[data-scrim]").classList.remove("is-open");
        window.scrollTo({ top: 0 });
      });
    });

    const toggle = () => {
      $("[data-side]").classList.toggle("is-open");
      $("[data-scrim]").classList.toggle("is-open");
    };
    $("[data-side-toggle]").addEventListener("click", toggle);
    $("[data-scrim]").addEventListener("click", toggle);
  }

  const EDITORS = {
    shows: editShow,
    characters: editCharacter,
    categories: editCategory,
    proof: editProof,
    usp: editUsp,
    stats: editStat,
    steps: editStep,
    faq: editFaq,
  };

  const ADD_ACTIONS = {
    show: () => editShow(-1),
    character: () => editCharacter(-1),
    category: () => editCategory(-1),
    proof: () => editProof(-1),
    usp: () => editUsp(-1),
    stat: () => editStat(-1),
    step: () => editStep(-1),
    faq: () => editFaq(-1),
  };

  function initEvents() {
    // Кнопки «добавить».
    $$("[data-add]").forEach((btn) => {
      btn.addEventListener("click", () => ADD_ACTIONS[btn.dataset.add]?.());
    });

    // Кнопки «изменить» внутри списков.
    document.addEventListener("click", (e) => {
      const editBtn = e.target.closest("[data-edit]");
      if (editBtn) {
        const kind = editBtn.closest(".item")?.dataset.kind;
        EDITORS[kind]?.(Number(editBtn.dataset.edit));
        return;
      }
      const restore = e.target.closest("[data-restore]");
      if (restore) {
        try {
          const list = JSON.parse(localStorage.getItem(LS_HISTORY) || "[]");
          const entry = list[Number(restore.dataset.restore)];
          if (!entry) return;
          site = clone(entry.data);
          markDirty(true);
          renderAll();
          toast("Версия восстановлена — не забудьте сохранить");
        } catch {
          toast("Не удалось восстановить версию", "err");
        }
      }
    });

    // Модальное окно.
    $$("[data-modal-close]").forEach((b) => b.addEventListener("click", () => modal.close()));
    $("[data-modal]").addEventListener("click", (e) => {
      if (e.target === $("[data-modal]")) modal.close();
    });
    $("[data-modal-save]").addEventListener("click", () => {
      if (modal.onSave?.() === false) return;
      modal.close();
      markDirty(true);
      renderAll();
    });
    $("[data-modal-delete]").addEventListener("click", () => {
      if (!window.confirm("Удалить запись? Действие можно отменить только откатом версии.")) return;
      modal.onDelete?.();
      modal.close();
      markDirty(true);
      renderAll();
      toast("Запись удалена", "warn");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") modal.close();
      // Ctrl/Cmd+S — быстрое сохранение.
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        saveToFile();
      }
    });

    // Поиск и фильтр.
    $('[data-search="shows"]').addEventListener("input", (e) => {
      searchState.shows = e.target.value;
      renderShows();
    });
    $('[data-search="characters"]').addEventListener("input", (e) => {
      searchState.characters = e.target.value;
      renderCharacters();
    });
    $('[data-filter="characters"]').addEventListener("change", (e) => {
      filterState.characters = e.target.value;
      renderCharacters();
    });

    // Поля с прямой привязкой к данным.
    $$("[data-bind]").forEach((el) => {
      el.addEventListener("input", () => {
        const path = el.dataset.bind.split(".");
        const last = path.pop();
        let target = site;
        for (const key of path) {
          target[key] ??= {};
          target = target[key];
        }
        target[last] = el.value;
        markDirty(true);
        if (el.dataset.bind.startsWith("meta.")) renderTiles();
      });
    });

    // Действия верхней панели и раздела сохранения.
    const ACTIONS = {
      save: saveToFile,
      "save-file": saveToFile,
      download: downloadJson,
      import: importJson,
      preview: openPreview,
      reset: () => {
        if (!window.confirm("Удалить черновик и вернуться к сохранённой версии?")) return;
        localStorage.removeItem(LS_DRAFT);
        localStorage.removeItem(LS_PREVIEW);
        if (original) {
          site = clone(original);
          markDirty(false);
          renderAll();
          toast("Черновик сброшен");
        } else {
          window.location.reload();
        }
      },
    };
    $$("[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => ACTIONS[btn.dataset.action]?.());
    });

    // Предупреждение о несохранённых правках.
    window.addEventListener("beforeunload", (e) => {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    });
  }

  /* ── Вход ────────────────────────────────────────────────────────────── */

  function initGate() {
    const gate = $("[data-gate]");
    if (sessionStorage.getItem(LS_AUTH) === "1") {
      gate.hidden = true;
      return true;
    }
    $("[data-gate-form]").addEventListener("submit", (e) => {
      e.preventDefault();
      const value = $("#gate-pass").value;
      if (value === ACCESS_CODE) {
        sessionStorage.setItem(LS_AUTH, "1");
        gate.hidden = true;
        start();
      } else {
        $("[data-gate-error]").textContent = "Неверный код доступа";
        $("#gate-pass").value = "";
        $("#gate-pass").focus();
      }
    });
    return false;
  }

  /* ── Старт ───────────────────────────────────────────────────────────── */

  let started = false;
  async function start() {
    if (started) return;
    started = true;
    await loadData();
    renderAll();
    initTabs();
    initEvents();
    initDrag();
  }

  if (initGate()) start();
})();
