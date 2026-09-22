/* ==========================================================================
   Сюрприз V6 — логика лендинга. Чистый ES-модульный JS, без зависимостей.

   Данные читаются из data/site.json, что даёт две вещи:
     • контент правится через админку (admin.html) без правки разметки;
     • при открытии по file:// работает фолбэк на встроенный <script id="site-data">.
   ========================================================================== */
(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  /* ── Утилиты ─────────────────────────────────────────────────────────── */

  const icon = (name, cls = "icon") =>
    `<svg class="${cls}" aria-hidden="true"><use href="./assets/icons.svg#${name}"></use></svg>`;

  const escapeHtml = (str = "") =>
    String(str).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  /** Склонение существительного по числу: plural(5, ['герой','героя','героев']). */
  const plural = (n, forms) => {
    const mod100 = n % 100;
    const mod10 = n % 10;
    if (mod100 > 10 && mod100 < 20) return forms[2];
    if (mod10 === 1) return forms[0];
    if (mod10 >= 2 && mod10 <= 4) return forms[1];
    return forms[2];
  };

  const debounce = (fn, ms = 140) => {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  };

  /** Единый рендер <img> с blur-up плейсхолдером и корректными размерами. */
  const imgTag = (pic, { alt, cls = "", sizes = "", lqip = "", eager = false }) => {
    if (!pic || !pic.src) return "";
    const style = lqip ? ` style="--lqip:url('${lqip}')" data-lqip` : "";
    return `<img class="${cls} is-loading" src="${pic.src}"${pic.srcset ? ` srcset="${pic.srcset}"` : ""}` +
      `${sizes ? ` sizes="${sizes}"` : ""} width="${pic.w}" height="${pic.h}" alt="${escapeHtml(alt)}"` +
      ` loading="${eager ? "eager" : "lazy"}" decoding="async"` +
      `${eager ? ' fetchpriority="high"' : ""}${style}>`;
  };

  /** Снимает blur, когда картинка догрузилась (в т.ч. если она уже в кэше). */
  const watchImages = (root = document) => {
    $$("img.is-loading", root).forEach((img) => {
      const done = () => {
        img.classList.remove("is-loading");
        img.classList.add("is-loaded");
      };
      if (img.complete && img.naturalWidth > 0) done();
      else img.addEventListener("load", done, { once: true });
      img.addEventListener("error", () => img.classList.remove("is-loading"), { once: true });
    });
  };

  /* ── Загрузка данных ─────────────────────────────────────────────────── */

  async function loadSite() {
    // Черновик из админки имеет приоритет — так работает предпросмотр.
    try {
      const draft = localStorage.getItem("surpriz:preview");
      if (draft) return JSON.parse(draft);
    } catch { /* localStorage может быть недоступен — не критично */ }

    try {
      const res = await fetch("./data/site.json", { cache: "no-cache" });
      if (res.ok) return await res.json();
    } catch {
      // file:// блокирует fetch — падаем на встроенную копию данных.
    }

    const inline = $("#site-data");
    if (inline) return JSON.parse(inline.textContent);
    throw new Error("Не удалось загрузить данные сайта");
  }

  /* ── Секция «Шоу-программы» ──────────────────────────────────────────── */

  function initShows(site) {
    const stage = $("[data-stage]");
    const picker = $("[data-picker]");
    if (!stage || !picker || !site.shows.length) return;

    const media = $("[data-stage-media]", stage);
    const els = {
      badge: $("[data-stage-badge]", stage),
      title: $("[data-stage-title]", stage),
      text: $("[data-stage-text]", stage),
      duration: $("[data-stage-duration]", stage),
      price: $("[data-stage-price]", stage),
      route: $("[data-stage-route]", stage),
      builder: $("[data-stage-builder]", stage),
    };

    // Слои изображений создаём один раз: переключение = смена класса,
    // поэтому нет мигания и повторной загрузки.
    const layers = site.shows.map((show, i) => {
      const el = document.createElement("img");
      el.className = "stage__img";
      el.src = show.image.src;
      if (show.image.srcset) el.srcset = show.image.srcset;
      el.sizes = "(min-width: 900px) 56vw, 92vw";
      el.width = show.image.w;
      el.height = show.image.h;
      el.alt = show.name;
      el.loading = i === 0 ? "eager" : "lazy";
      el.decoding = "async";
      if (i === 0) el.fetchPriority = "high";
      media.prepend(el);
      return el;
    });

    picker.innerHTML = site.shows.map((show, i) => `
      <button class="picker__item${i === 0 ? " is-active" : ""}" type="button"
              data-show="${i}" aria-pressed="${i === 0}">
        <img class="picker__thumb" src="${show.image.src}" width="${show.image.w}"
             height="${show.image.h}" alt="" loading="lazy" decoding="async">
        <span class="picker__label">${escapeHtml(show.name)}<span>${escapeHtml(show.duration)}</span></span>
      </button>`).join("");

    let active = -1;
    const select = (index) => {
      if (index === active) return;
      const show = site.shows[index];
      active = index;

      layers.forEach((el, i) => el.classList.toggle("is-active", i === index));
      stage.style.setProperty("--accent", show.accent);

      els.badge.innerHTML = `${icon(show.icon)}<span>Шоу-программа</span>`;
      els.title.textContent = show.name;
      els.text.textContent = show.summary;
      els.duration.innerHTML = `${icon("i-clock")}<span>${escapeHtml(show.duration)}</span>`;
      els.price.innerHTML = `${icon("i-wallet")}<span>${escapeHtml(show.price)}</span>`;
      els.route.href = show.route;
      els.builder.href = show.builder_url;

      $$(".picker__item", picker).forEach((btn, i) => {
        btn.classList.toggle("is-active", i === index);
        btn.setAttribute("aria-pressed", String(i === index));
      });
    };

    picker.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-show]");
      if (btn) select(Number(btn.dataset.show));
    });

    // Стрелки влево/вправо переключают шоу, когда фокус внутри пикера.
    picker.addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const delta = e.key === "ArrowRight" ? 1 : -1;
      const next = (active + delta + site.shows.length) % site.shows.length;
      select(next);
      $$(".picker__item", picker)[next].focus();
    });

    select(0);
    watchImages(stage);
  }

  /* ── Каталог персонажей ──────────────────────────────────────────────── */

  // Пастельные подложки под прозрачные PNG: цвет закреплён за слагом,
  // поэтому карточка всегда выглядит одинаково между визитами.
  const CARD_TINTS = [
    ["#fff2e2", "#ffe0c8"], ["#e8f4ff", "#d4e8ff"], ["#f0ecff", "#e0d8ff"],
    ["#e6f9f1", "#d0f0e2"], ["#fff0f4", "#ffdce8"], ["#fdf6dc", "#f8ecc0"],
    ["#eaf6ff", "#d8ecfb"], ["#f6f0e8", "#eae0d2"],
  ];

  const tintFor = (slug) => {
    let hash = 0;
    for (let i = 0; i < slug.length; i += 1) hash = (hash * 31 + slug.charCodeAt(i)) % 9973;
    const [a, b] = CARD_TINTS[hash % CARD_TINTS.length];
    return `linear-gradient(160deg, ${a}, ${b})`;
  };

  function initCatalog(site) {
    const grid = $("[data-grid]");
    const filters = $("[data-filters]");
    const searchWrap = $("[data-search]");
    if (!grid) return;

    const input = $("input", searchWrap);
    const clearBtn = $("[data-search-clear]", searchWrap);
    const counter = $("[data-count]");
    const empty = $("[data-empty]");

    const categoryLabel = new Map(site.categories.map((c) => [c.id, c.label]));

    filters.innerHTML = site.categories.map((cat, i) => `
      <button class="filter${i === 0 ? " is-active" : ""}" type="button"
              data-cat="${cat.id}" aria-pressed="${i === 0}">
        ${icon(cat.icon)}<span>${escapeHtml(cat.label)}</span>
      </button>`).join("");

    const cardHtml = (ch) => {
      const primary = ch.categories.find((c) => c !== "all");
      return `
      <article class="card" data-slug="${ch.slug}" style="--card-bg:${tintFor(ch.slug)}">
        <div class="card__media">
          <span class="card__glow"></span>
          ${primary ? `<span class="card__tag">${escapeHtml(categoryLabel.get(primary) || "")}</span>` : ""}
          ${imgTag(ch.image, {
            alt: ch.name,
            cls: "card__img",
            sizes: "(min-width: 1100px) 240px, (min-width: 700px) 30vw, 46vw",
            lqip: ch.lqip,
          })}
        </div>
        <div class="card__body">
          <h3 class="card__name">${escapeHtml(ch.name)}</h3>
          ${ch.description ? `<p class="card__desc">${escapeHtml(ch.description)}</p>` : ""}
        </div>
        <a class="card__link" href="${site.meta.builder_url}?character=${ch.slug}">
          <span class="u-visually-hidden">Подробнее: ${escapeHtml(ch.name)}</span>
        </a>
      </article>`;
    };

    let category = "all";
    let query = "";

    const matches = (ch) => {
      if (category !== "all" && !ch.categories.includes(category)) return false;
      if (!query) return true;
      const haystack = `${ch.name} ${ch.description}`.toLowerCase();
      return haystack.includes(query);
    };

    /**
     * Перерисовка с FLIP-анимацией: запоминаем позиции карточек до смены DOM,
     * после — сдвигаем их transform'ом в старое место и отпускаем.
     * Так перестановка при фильтрации выглядит плавной, а не «дёргано».
     */
    const render = () => {
      const before = new Map();
      if (!reduceMotion) {
        $$(".card", grid).forEach((el) => before.set(el.dataset.slug, el.getBoundingClientRect()));
      }

      const visible = site.characters.filter(matches);
      grid.innerHTML = visible.map(cardHtml).join("");

      counter.textContent = visible.length
        ? `${visible.length} ${plural(visible.length, ["программа", "программы", "программ"])}`
        : "Ничего не найдено";
      // Заглушку показываем только при пустом результате.
      empty.hidden = visible.length !== 0;

      if (!reduceMotion) {
        $$(".card", grid).forEach((el) => {
          const prev = before.get(el.dataset.slug);
          if (!prev) {
            el.animate(
              [{ opacity: 0, transform: "scale(.94)" }, { opacity: 1, transform: "none" }],
              { duration: 260, easing: "cubic-bezier(.16,1,.3,1)" },
            );
            return;
          }
          const next = el.getBoundingClientRect();
          const dx = prev.left - next.left;
          const dy = prev.top - next.top;
          if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
          el.animate(
            [{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }],
            { duration: 340, easing: "cubic-bezier(.16,1,.3,1)" },
          );
        });
      }

      watchImages(grid);
    };

    filters.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-cat]");
      if (!btn) return;
      category = btn.dataset.cat;
      $$(".filter", filters).forEach((el) => {
        const on = el === btn;
        el.classList.toggle("is-active", on);
        el.setAttribute("aria-pressed", String(on));
      });
      render();
    });

    const onSearch = debounce(() => {
      query = input.value.trim().toLowerCase();
      searchWrap.classList.toggle("has-value", input.value.length > 0);
      render();
    }, 120);

    input.addEventListener("input", onSearch);
    clearBtn.addEventListener("click", () => {
      input.value = "";
      query = "";
      searchWrap.classList.remove("has-value");
      render();
      input.focus();
    });

    // Escape очищает поиск, если поле в фокусе.
    input.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && input.value) {
        e.preventDefault();
        clearBtn.click();
      }
    });

    render();
  }

  /* ── Галерея «Живые кадры» + лайтбокс ────────────────────────────────── */

  function initProof(site) {
    const masonry = $("[data-masonry]");
    if (!masonry || !site.proof.length) return;

    masonry.innerHTML = site.proof.map((item, i) => `
      <figure data-index="${i}" tabindex="0" role="button"
              aria-label="Открыть кадр: ${escapeHtml(item.caption)}">
        ${imgTag(item.image, {
          alt: item.caption,
          sizes: "(min-width: 1100px) 400px, (min-width: 700px) 44vw, 92vw",
          lqip: item.lqip,
        })}
        ${item.caption ? `<figcaption>${escapeHtml(item.caption)}</figcaption>` : ""}
      </figure>`).join("");

    watchImages(masonry);

    const box = $("[data-lightbox]");
    const boxImg = $("[data-lightbox-img]", box);
    const boxCaption = $("[data-lightbox-caption]", box);
    let index = 0;
    let lastFocused = null;

    const show = (i) => {
      index = (i + site.proof.length) % site.proof.length;
      const item = site.proof[index];
      boxImg.src = item.image.src;
      if (item.image.srcset) boxImg.srcset = item.image.srcset;
      boxImg.alt = item.caption;
      boxCaption.textContent = item.caption;
    };

    const open = (i) => {
      lastFocused = document.activeElement;
      show(i);
      box.classList.add("is-open");
      box.removeAttribute("inert");
      document.body.classList.add("is-locked");
      $("[data-lightbox-close]", box).focus();
    };

    const close = () => {
      box.classList.remove("is-open");
      box.setAttribute("inert", "");
      document.body.classList.remove("is-locked");
      lastFocused?.focus();
    };

    masonry.addEventListener("click", (e) => {
      const fig = e.target.closest("figure");
      if (fig) open(Number(fig.dataset.index));
    });

    masonry.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const fig = e.target.closest("figure");
      if (!fig) return;
      e.preventDefault();
      open(Number(fig.dataset.index));
    });

    $("[data-lightbox-close]", box).addEventListener("click", close);
    $("[data-lightbox-prev]", box).addEventListener("click", () => show(index - 1));
    $("[data-lightbox-next]", box).addEventListener("click", () => show(index + 1));
    box.addEventListener("click", (e) => { if (e.target === box) close(); });

    document.addEventListener("keydown", (e) => {
      if (!box.classList.contains("is-open")) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowLeft") show(index - 1);
      if (e.key === "ArrowRight") show(index + 1);
    });

    // Свайп по горизонтали на мобильных.
    let touchX = null;
    box.addEventListener("touchstart", (e) => { touchX = e.touches[0].clientX; }, { passive: true });
    box.addEventListener("touchend", (e) => {
      if (touchX === null) return;
      const dx = e.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 48) show(index + (dx < 0 ? 1 : -1));
      touchX = null;
    }, { passive: true });
  }

  /* ── Статические секции из данных ────────────────────────────────────── */

  function initStatic(site) {
    // Hero
    const heroTitle = $("[data-hero-title]");
    if (heroTitle) {
      // Последнее слово выделяем цветом — акцент в две строки читается лучше.
      const words = site.hero.title.split(" ");
      const tail = words.pop();
      heroTitle.innerHTML = `${escapeHtml(words.join(" "))} <em>${escapeHtml(tail)}</em>`;
    }
    const set = (sel, text) => { const el = $(sel); if (el) el.textContent = text; };
    set("[data-hero-kicker-text]", site.hero.kicker);
    set("[data-hero-lead]", site.hero.lead);
    set("[data-hero-primary]", site.hero.primary_cta);

    const uspList = $("[data-hero-usp]");
    if (uspList) {
      uspList.innerHTML = site.hero.usp
        .map((u) => `<li>${icon(u.icon)}<span>${escapeHtml(u.text)}</span></li>`).join("");
    }

    // Слои hero: центральный кадр + два по бокам.
    const stageEl = $("[data-hero-stage]");
    if (stageEl && site.hero.layers.length) {
      const [main, left, right] = site.hero.layers;
      const layer = (item, cls, eager) => item ? `
        <div class="hero__layer hero__layer--${cls}" data-parallax="${cls}">
          ${imgTag(item.image, {
            alt: "",
            sizes: "(min-width: 960px) 40vw, 70vw",
            lqip: item.lqip,
            eager,
          })}
        </div>` : "";
      stageEl.insertAdjacentHTML("beforeend",
        layer(left, "left", false) + layer(right, "right", false) + layer(main, "main", true));
      watchImages(stageEl);
    }

    // Счётчики
    const trust = $("[data-stats]");
    if (trust) {
      trust.innerHTML = site.stats.map((s) => `
        <div class="stat">
          <span class="stat__icon">${icon(s.icon)}</span>
          <span>
            <span class="stat__value" data-counter="${s.value}">0</span>
            <span class="stat__label">${escapeHtml(s.label)}</span>
          </span>
        </div>`).join("");
    }

    // Шаги
    const steps = $("[data-steps]");
    if (steps) {
      steps.innerHTML = site.steps.map((s, i) => `
        <article class="step" data-reveal style="--reveal-delay:${i * 90}ms">
          <span class="step__icon">${icon(s.icon)}</span>
          <h3 class="step__title">${escapeHtml(s.title)}</h3>
          <p class="step__text">${escapeHtml(s.text)}</p>
        </article>`).join("");
    }

    // FAQ
    const faq = $("[data-faq]");
    if (faq) {
      faq.innerHTML = site.faq.map((item) => `
        <details>
          <summary>${escapeHtml(item.q)}${icon("i-chevron-down")}</summary>
          <p class="faq__answer">${escapeHtml(item.a)}</p>
        </details>`).join("");
    }

    // Контакты (шапка, финальный блок, подвал)
    $$("[data-phone]").forEach((el) => {
      el.href = site.meta.phone_href;
      const label = $("[data-phone-text]", el);
      if (label) label.textContent = site.meta.phone;
    });
    $$("[data-telegram]").forEach((el) => { el.href = site.meta.telegram; });
    $$("[data-instagram]").forEach((el) => { el.href = site.meta.instagram; });
    $$("[data-whatsapp]").forEach((el) => { el.href = site.meta.whatsapp; });
    $$("[data-builder]").forEach((el) => { el.href = site.meta.builder_url; });
    set("[data-year]", String(new Date().getFullYear()));
  }

  /* ── Анимация счётчиков ──────────────────────────────────────────────── */

  function initCounters() {
    const nodes = $$("[data-counter]");
    if (!nodes.length) return;

    if (reduceMotion) {
      nodes.forEach((el) => { el.textContent = el.dataset.counter; });
      return;
    }

    const run = (el) => {
      const target = Number(el.dataset.counter);
      const duration = 1100;
      const start = performance.now();
      const tick = (now) => {
        const t = Math.min(1, (now - start) / duration);
        // easeOutCubic — быстрый старт, мягкая остановка.
        const eased = 1 - (1 - t) ** 3;
        el.textContent = String(Math.round(target * eased));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    };

    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        run(entry.target);
        io.unobserve(entry.target);
      });
    }, { threshold: 0.6 });

    nodes.forEach((el) => io.observe(el));
  }

  /* ── Reveal по скроллу ───────────────────────────────────────────────── */

  function initReveal() {
    const nodes = $$("[data-reveal]");
    if (!nodes.length) return;
    if (reduceMotion) {
      nodes.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    nodes.forEach((el) => io.observe(el));
  }

  /* ── Шапка, меню, навигация ──────────────────────────────────────────── */

  function initChrome() {
    const header = $("[data-header]");
    if (header) {
      const onScroll = () => header.classList.toggle("is-stuck", window.scrollY > 8);
      onScroll();
      window.addEventListener("scroll", onScroll, { passive: true });
    }

    // Мобильное меню с ловушкой фокуса.
    const drawer = $("[data-drawer]");
    const burger = $("[data-burger]");
    if (drawer && burger) {
      let lastFocused = null;
      const openDrawer = () => {
        lastFocused = document.activeElement;
        drawer.classList.add("is-open");
        drawer.removeAttribute("inert");
        document.body.classList.add("is-locked");
        $(".drawer__link", drawer)?.focus();
      };
      const closeDrawer = () => {
        drawer.classList.remove("is-open");
        drawer.setAttribute("inert", "");
        document.body.classList.remove("is-locked");
        lastFocused?.focus();
      };
      burger.addEventListener("click", openDrawer);
      $("[data-drawer-close]", drawer)?.addEventListener("click", closeDrawer);
      $(".drawer__scrim", drawer)?.addEventListener("click", closeDrawer);
      $$("a", drawer).forEach((a) => a.addEventListener("click", closeDrawer));
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && drawer.classList.contains("is-open")) closeDrawer();
      });
    }

    // Подсветка активного раздела в навигации и таб-баре.
    const sections = $$("main section[id]");
    const links = $$("[data-nav-link]");
    if (sections.length && links.length) {
      const io = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const id = entry.target.id;
          links.forEach((l) => l.classList.toggle("is-active", l.dataset.navLink === id));
        });
      }, { rootMargin: "-45% 0px -50% 0px" });
      sections.forEach((s) => io.observe(s));
    }
  }

  /* ── Магнитный блик на кнопках ───────────────────────────────────────── */

  function initButtonGlow() {
    if (reduceMotion) return;
    document.addEventListener("pointermove", (e) => {
      const btn = e.target.closest(".btn");
      if (!btn) return;
      const r = btn.getBoundingClientRect();
      btn.style.setProperty("--mx", `${((e.clientX - r.left) / r.width) * 100}%`);
      btn.style.setProperty("--my", `${((e.clientY - r.top) / r.height) * 100}%`);
    }, { passive: true });
  }

  /* ── Параллакс hero ─────────────────────────────────────────────────── */

  function initParallax() {
    if (reduceMotion || window.matchMedia("(hover: none)").matches) return;
    const stage = $("[data-hero-stage]");
    if (!stage) return;
    const layers = $$("[data-parallax]", stage);
    if (!layers.length) return;

    const depth = { main: 10, left: 20, right: 16 };
    let raf = 0;

    stage.addEventListener("pointermove", (e) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const r = stage.getBoundingClientRect();
        const nx = (e.clientX - r.left) / r.width - 0.5;
        const ny = (e.clientY - r.top) / r.height - 0.5;
        layers.forEach((el) => {
          const d = depth[el.dataset.parallax] ?? 12;
          const base = el.classList.contains("hero__layer--main") ? "translateX(-50%) " : "";
          el.style.transform = `${base}translate3d(${(-nx * d).toFixed(2)}px, ${(-ny * d * 0.6).toFixed(2)}px, 0)`;
        });
      });
    }, { passive: true });

    stage.addEventListener("pointerleave", () => {
      layers.forEach((el) => {
        el.style.transform = el.classList.contains("hero__layer--main") ? "translateX(-50%)" : "";
      });
    });
  }

  /* ── Старт ───────────────────────────────────────────────────────────── */

  async function boot() {
    let site;
    try {
      site = await loadSite();
    } catch (err) {
      console.error("[Сюрприз] данные не загружены:", err);
      return;
    }

    initStatic(site);
    initShows(site);
    initCatalog(site);
    initProof(site);
    initChrome();
    initCounters();
    initReveal();
    initButtonGlow();
    initParallax();
    watchImages();

    document.documentElement.classList.add("is-ready");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
