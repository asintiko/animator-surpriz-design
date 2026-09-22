(() => {
  "use strict";

  const apiUrl = new URL("../api/catalogs", window.location.href);
  const uploadUrl = new URL("../api/catalogs/upload", window.location.href);
  const defaultColor = "#21165b";
  const placementLabels = {
    homepage: "Главная",
    catalog: "Каталог",
    party_builder: "Подборщик",
  };
  const state = {
    data: null,
    selection: null,
    dragged: null,
    imageDrag: null,
    previewObjectUrl: "",
    filters: { characters: "", shows: "" },
    saveQueue: Promise.resolve(),
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const editor = $("[data-editor]");
  const editorEmpty = $("[data-editor-empty]");
  const editorForm = $("[data-editor-form]");
  const template = $("#admin-card-row-template");
  const saveState = $("[data-save-state]");
  const imagePreview = $("[data-image-preview]");
  const categoryEditor = $("[data-character-categories]");

  const clamp = (value, minimum = 0, maximum = 100) =>
    Math.min(maximum, Math.max(minimum, Number.isFinite(Number(value)) ? Number(value) : 50));

  const clampZoom = (value) => clamp(value, 100, 200);

  const setSaveState = (kind, message) => {
    saveState.className = `admin-save-state ${kind ? `is-${kind}` : ""}`.trim();
    $("span", saveState).textContent = message;
  };

  const assetUrl = (value) => {
    const source = String(value || "").trim();
    if (!source) return "";
    if (/^(?:data:|blob:|https?:\/\/)/i.test(source)) return source;
    return new URL(`../${source.replace(/^\/+/, "")}`, window.location.href).href;
  };

  const slugify = (value) => {
    const translit = {
      а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z",
      и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r",
      с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "ts", ч: "ch", ш: "sh",
      щ: "sch", ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
    };
    const normalized = String(value || "").toLowerCase().trim().split("")
      .map((character) => translit[character] ?? character).join("")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return normalized || `card-${Date.now().toString(36)}`;
  };

  const normalizeColor = (value) =>
    /^#[0-9a-f]{6}$/i.test(String(value || "")) ? String(value).toLowerCase() : defaultColor;

  const itemPosition = (item) => ({
    x: clamp(item?.image_position?.x),
    y: clamp(item?.image_position?.y),
  });

  const itemZoom = (item) => clampZoom(item?.image_zoom ?? 100);

  const formPosition = () => ({
    x: clamp(editorForm.elements.image_x.value),
    y: clamp(editorForm.elements.image_y.value),
  });

  const formZoom = () => clampZoom(editorForm.elements.image_zoom.value);

  const selectedIndex = () => {
    if (!state.selection || state.selection.isNew) return -1;
    return state.data[state.selection.kind].findIndex((item) => item.id === state.selection.id);
  };

  const selectedKind = () => state.selection?.kind || "characters";

  const applyImagePosition = (image, kind, position, zoom = 100) => {
    const scale = clampZoom(zoom) / 100;
    image.style.objectPosition = `${position.x}% ${position.y}%`;
    image.style.transformOrigin = `${position.x}% ${position.y}%`;
    if (kind === "characters") {
      image.style.objectFit = "contain";
      const shiftX = (50 - position.x) * 0.36;
      const shiftY = (50 - position.y) * 0.36;
      image.style.transform = `translate(${shiftX}%, ${shiftY}%) scale(${scale})`;
    } else {
      image.style.objectFit = "cover";
      image.style.transform = `scale(${scale})`;
    }
  };

  const renderSafeFrame = () => {
    const frame = document.createElement("i");
    frame.className = "admin-image-editor__safe-frame";
    frame.setAttribute("aria-hidden", "true");
    imagePreview.append(frame);
  };

  const updatePositionControls = (position, zoom = formZoom()) => {
    editorForm.elements.image_x.value = String(Math.round(position.x));
    editorForm.elements.image_y.value = String(Math.round(position.y));
    editorForm.elements.image_zoom.value = String(Math.round(clampZoom(zoom)));
    $('[data-position-output="x"]').value = `${Math.round(position.x)}%`;
    $('[data-position-output="y"]').value = `${Math.round(position.y)}%`;
    $('[data-position-output="zoom"]').value = `${Math.round(clampZoom(zoom))}%`;
  };

  const updateImagePreview = (value, position = formPosition(), zoom = formZoom()) => {
    const source = assetUrl(value);
    imagePreview.replaceChildren();
    imagePreview.classList.toggle("is-character", selectedKind() === "characters");
    updatePositionControls(position, zoom);

    if (!source) {
      const placeholder = document.createElement("span");
      placeholder.textContent = "Загрузите изображение";
      imagePreview.append(placeholder);
      renderSafeFrame();
      return;
    }

    const image = document.createElement("img");
    image.src = source;
    image.alt = "Предпросмотр изображения";
    applyImagePosition(image, selectedKind(), position, zoom);
    image.onerror = () => {
      imagePreview.replaceChildren();
      const error = document.createElement("span");
      error.textContent = "Изображение не найдено";
      imagePreview.append(error);
      renderSafeFrame();
    };
    imagePreview.append(image);
    renderSafeFrame();
  };

  const updateLiveCardPreview = () => {
    const title = editorForm.elements.title.value.trim() || "Название карточки";
    const description = editorForm.elements.description.value.trim() || "Короткое описание появится здесь.";
    const color = normalizeColor(editorForm.elements.title_color.value);
    $("[data-title-preview]").textContent = title;
    $("[data-title-preview]").style.color = color;
    $("[data-description-preview]").textContent = description;
    $("[data-description-count]").textContent = String(editorForm.elements.description.value.length);
  };

  const setTitleColor = (value) => {
    const color = normalizeColor(value);
    editorForm.elements.title_color.value = color;
    $("[data-custom-title-color]").value = color;
    $$("[data-title-color]").forEach((swatch) => {
      swatch.classList.toggle("is-selected", swatch.dataset.titleColor.toLowerCase() === color);
    });
    updateLiveCardPreview();
  };

  const collectionLabel = (kind) =>
    kind === "characters" ? "Каталог персонажей" : "Каталог шоу-программ";

  const placementSummary = (item) => {
    const labels = (item.placements || []).map((placement) => placementLabels[placement]).filter(Boolean);
    return labels.length ? labels.join(" · ") : "Нигде не показывается";
  };

  const renderList = (kind) => {
    const list = $(`[data-admin-list="${kind}"]`);
    const query = state.filters[kind].trim().toLocaleLowerCase("ru");
    list.replaceChildren();

    state.data[kind].forEach((item, index) => {
      const haystack = `${item.title} ${item.description}`.toLocaleLowerCase("ru");
      if (query && !haystack.includes(query)) return;

      const row = template.content.firstElementChild.cloneNode(true);
      row.dataset.kind = kind;
      row.dataset.index = String(index);
      row.dataset.itemId = item.id;
      row.classList.toggle("is-selected", state.selection?.kind === kind && state.selection.id === item.id);

      const thumb = $(".admin-card-row__thumb", row);
      if (item.image) {
        const image = document.createElement("img");
        image.src = assetUrl(item.image);
        image.alt = "";
        applyImagePosition(image, kind, itemPosition(item), itemZoom(item));
        thumb.append(image);
      }
      const title = $(".admin-card-row__copy strong", row);
      title.textContent = item.title || "Без названия";
      title.style.color = normalizeColor(item.title_color);
      $(".admin-card-row__copy p", row).textContent = item.description || "Описание не заполнено";
      $(".admin-card-row__placement", row).textContent = placementSummary(item);

      const visibility = $(".admin-card-row__switch input", row);
      visibility.checked = item.active !== false;
      visibility.dataset.visibility = "";

      const up = $('[data-move="up"]', row);
      const down = $('[data-move="down"]', row);
      up.disabled = index === 0;
      down.disabled = index === state.data[kind].length - 1;
      $(".admin-card-row__edit", row).dataset.edit = "";
      list.append(row);
    });
  };

  const renderLists = () => {
    renderList("characters");
    renderList("shows");
  };

  const snapshot = () => JSON.parse(JSON.stringify(state.data));

  const persist = () => {
    const payload = snapshot();
    setSaveState("saving", "Сохраняем изменения…");
    state.saveQueue = state.saveQueue.catch(() => {}).then(async () => {
      const response = await fetch(apiUrl, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.error || "Не удалось сохранить изменения");
      state.data = result;
      setSaveState("saved", "Все изменения сохранены");
    }).catch((error) => {
      setSaveState("error", error.message);
      throw error;
    });
    return state.saveQueue;
  };

  const revokePreviewObjectUrl = () => {
    if (!state.previewObjectUrl) return;
    URL.revokeObjectURL(state.previewObjectUrl);
    state.previewObjectUrl = "";
  };

  const closeEditor = () => {
    revokePreviewObjectUrl();
    state.selection = null;
    editorForm.hidden = true;
    editorEmpty.hidden = false;
    renderLists();
  };

  const openEditor = (kind, index = -1) => {
    revokePreviewObjectUrl();
    const isNew = index < 0;
    const item = isNew ? {
      id: "",
      title: "",
      description: "",
      image: "",
      alt: "",
      cta_label: "Заказать",
      href: "/party-builder/",
      active: true,
      title_color: defaultColor,
      image_position: { x: 50, y: 50 },
      image_zoom: 100,
      categories: [],
      placements: ["homepage", "catalog", "party_builder"],
    } : state.data[kind][index];

    state.selection = { kind, id: item.id, isNew };
    editorEmpty.hidden = true;
    editorForm.hidden = false;
    $("[data-editor-kind]").textContent = collectionLabel(kind);
    $("[data-editor-title]").textContent = isNew ? "Новая карточка" : item.title;
    editorForm.elements.title.value = item.title;
    editorForm.elements.description.value = item.description;
    editorForm.elements.image.value = item.image;
    editorForm.elements.alt.value = item.alt;
    editorForm.elements.cta_label.value = item.cta_label || "Заказать";
    editorForm.elements.href.value = item.href || "/party-builder/";
    editorForm.elements.active.checked = item.active !== false;
    const placements = new Set(item.placements || []);
    $$('input[name="placements"]', editorForm).forEach((input) => {
      input.checked = placements.has(input.value);
    });
    categoryEditor.hidden = kind !== "characters";
    const categories = new Set(item.categories || []);
    $$('input[name="categories"]', editorForm).forEach((input) => {
      input.checked = categories.has(input.value);
    });
    $("[data-delete-card]").hidden = isNew;
    $("[data-upload-state]").textContent = "PNG, JPG или WebP до 8 МБ";
    updatePositionControls(itemPosition(item), itemZoom(item));
    setTitleColor(item.title_color);
    updateLiveCardPreview();
    updateImagePreview(item.image, itemPosition(item), itemZoom(item));
    renderLists();
    editor.scrollTo({ top: 0, behavior: "smooth" });
  };

  const saveEditor = async () => {
    if (!state.selection) return;
    const { kind, isNew } = state.selection;
    const index = selectedIndex();
    const title = editorForm.elements.title.value.trim();
    const image = editorForm.elements.image.value.trim();
    if (!image) throw new Error("Сначала загрузите изображение");

    const item = {
      id: isNew ? `${kind === "characters" ? "character" : "show"}-${slugify(title)}` : state.selection.id,
      title,
      description: editorForm.elements.description.value.trim(),
      image,
      alt: editorForm.elements.alt.value.trim(),
      cta_label: editorForm.elements.cta_label.value.trim() || "Заказать",
      href: editorForm.elements.href.value.trim() || "/party-builder/",
      active: editorForm.elements.active.checked,
      title_color: normalizeColor(editorForm.elements.title_color.value),
      image_position: formPosition(),
      image_zoom: formZoom(),
      categories: kind === "characters"
        ? $$('input[name="categories"]:checked', editorForm).map((input) => input.value)
        : [],
      placements: $$('input[name="placements"]:checked', editorForm).map((input) => input.value),
    };

    if (isNew) {
      const ids = new Set(state.data[kind].map((entry) => entry.id));
      const baseId = item.id;
      let suffix = 2;
      while (ids.has(item.id)) item.id = `${baseId}-${suffix++}`;
      state.data[kind].push(item);
      state.selection = { kind, id: item.id, isNew: false };
    } else {
      if (index < 0) throw new Error("Карточка больше не найдена");
      state.data[kind][index] = item;
    }

    renderLists();
    await persist();
    const savedIndex = state.data[kind].findIndex((entry) => entry.id === item.id);
    openEditor(kind, savedIndex);
  };

  const moveCard = async (kind, index, direction) => {
    const items = state.data[kind];
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    [items[index], items[target]] = [items[target], items[index]];
    renderLists();
    await persist();
  };

  const toggleVisibility = async (kind, index, active) => {
    state.data[kind][index].active = active;
    if (state.selection?.id === state.data[kind][index].id) editorForm.elements.active.checked = active;
    await persist();
  };

  const deleteCurrentCard = async () => {
    const index = selectedIndex();
    const { kind } = state.selection;
    const item = state.data[kind][index];
    if (!item || !window.confirm(`Удалить карточку «${item.title}»?`)) return;
    state.data[kind].splice(index, 1);
    closeEditor();
    await persist();
  };

  const uploadImage = async (file) => {
    const uploadState = $("[data-upload-state]");
    revokePreviewObjectUrl();
    state.previewObjectUrl = URL.createObjectURL(file);
    updateImagePreview(state.previewObjectUrl);
    uploadState.textContent = "Предпросмотр готов, загружаем оригинал…";

    const body = new FormData();
    body.append("image", file);
    const response = await fetch(uploadUrl, { method: "POST", body });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.error || "Не удалось загрузить изображение");
    editorForm.elements.image.value = result.path;
    revokePreviewObjectUrl();
    updateImagePreview(result.path);
    uploadState.textContent = "Изображение загружено. Настройте кадр и сохраните карточку.";
  };

  const setPosition = (position) => {
    const normalized = { x: clamp(position.x), y: clamp(position.y) };
    updatePositionControls(normalized, formZoom());
    const image = imagePreview.querySelector("img");
    if (image) applyImagePosition(image, selectedKind(), normalized, formZoom());
  };

  const setZoom = (zoom) => {
    const normalized = clampZoom(zoom);
    const position = formPosition();
    updatePositionControls(position, normalized);
    const image = imagePreview.querySelector("img");
    if (image) applyImagePosition(image, selectedKind(), position, normalized);
  };

  document.addEventListener("click", (event) => {
    const add = event.target.closest("[data-add-card]");
    if (add) return openEditor(add.dataset.addCard);

    const color = event.target.closest("[data-title-color]");
    if (color) return setTitleColor(color.dataset.titleColor);

    const row = event.target.closest(".admin-card-row");
    if (!row) return;
    const kind = row.dataset.kind;
    const index = Number(row.dataset.index);
    if (event.target.closest("[data-edit]")) return openEditor(kind, index);
    const move = event.target.closest("[data-move]");
    if (move) moveCard(kind, index, move.dataset.move === "up" ? -1 : 1)
      .catch((error) => setSaveState("error", error.message));
  });

  document.addEventListener("change", (event) => {
    const toggle = event.target.closest("[data-visibility]");
    if (!toggle) return;
    const row = toggle.closest(".admin-card-row");
    toggleVisibility(row.dataset.kind, Number(row.dataset.index), toggle.checked)
      .catch((error) => setSaveState("error", error.message));
  });

  document.addEventListener("dragstart", (event) => {
    const row = event.target.closest(".admin-card-row");
    if (!row) return;
    state.dragged = { kind: row.dataset.kind, index: Number(row.dataset.index) };
    row.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
  });

  document.addEventListener("dragover", (event) => {
    const row = event.target.closest(".admin-card-row");
    if (!row || !state.dragged || row.dataset.kind !== state.dragged.kind) return;
    event.preventDefault();
    $$(".admin-card-row.is-over").forEach((item) => item.classList.remove("is-over"));
    row.classList.add("is-over");
  });

  document.addEventListener("drop", async (event) => {
    const row = event.target.closest(".admin-card-row");
    if (!row || !state.dragged || row.dataset.kind !== state.dragged.kind) return;
    event.preventDefault();
    const to = Number(row.dataset.index);
    const { kind, index: from } = state.dragged;
    if (from !== to) {
      const [moved] = state.data[kind].splice(from, 1);
      state.data[kind].splice(to, 0, moved);
      renderLists();
      await persist().catch((error) => setSaveState("error", error.message));
    }
  });

  document.addEventListener("dragend", () => {
    state.dragged = null;
    $$(".admin-card-row.is-dragging, .admin-card-row.is-over")
      .forEach((item) => item.classList.remove("is-dragging", "is-over"));
  });

  imagePreview.addEventListener("pointerdown", (event) => {
    if (!imagePreview.querySelector("img") || event.button !== 0) return;
    const position = formPosition();
    state.imageDrag = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      x: position.x,
      y: position.y,
    };
    imagePreview.setPointerCapture(event.pointerId);
    imagePreview.classList.add("is-dragging");
  });

  imagePreview.addEventListener("pointermove", (event) => {
    if (state.imageDrag?.pointerId !== event.pointerId) return;
    const rect = imagePreview.getBoundingClientRect();
    setPosition({
      x: state.imageDrag.x - ((event.clientX - state.imageDrag.clientX) / rect.width) * 100,
      y: state.imageDrag.y - ((event.clientY - state.imageDrag.clientY) / rect.height) * 100,
    });
  });

  const finishImageDrag = (event) => {
    if (state.imageDrag?.pointerId !== event.pointerId) return;
    if (imagePreview.hasPointerCapture(event.pointerId)) imagePreview.releasePointerCapture(event.pointerId);
    state.imageDrag = null;
    imagePreview.classList.remove("is-dragging");
  };
  imagePreview.addEventListener("pointerup", finishImageDrag);
  imagePreview.addEventListener("pointercancel", finishImageDrag);
  imagePreview.addEventListener("keydown", (event) => {
    const deltas = {
      ArrowLeft: { x: 2, y: 0 },
      ArrowRight: { x: -2, y: 0 },
      ArrowUp: { x: 0, y: 2 },
      ArrowDown: { x: 0, y: -2 },
    };
    const delta = deltas[event.key];
    if (!delta) return;
    event.preventDefault();
    const position = formPosition();
    setPosition({ x: position.x + delta.x, y: position.y + delta.y });
  });

  editorForm.addEventListener("submit", (event) => {
    event.preventDefault();
    saveEditor().catch((error) => setSaveState("error", error.message));
  });
  $("[data-editor-close]").addEventListener("click", closeEditor);
  $("[data-delete-card]").addEventListener("click", () =>
    deleteCurrentCard().catch((error) => setSaveState("error", error.message)));
  $("[data-position-reset]").addEventListener("click", () => {
    setZoom(100);
    setPosition({ x: 50, y: 50 });
  });
  $$('input[name="image_x"], input[name="image_y"]', editorForm).forEach((input) => {
    input.addEventListener("input", () => setPosition(formPosition()));
  });
  editorForm.elements.image_zoom.addEventListener("input", () => setZoom(formZoom()));
  editorForm.elements.title.addEventListener("input", updateLiveCardPreview);
  editorForm.elements.description.addEventListener("input", updateLiveCardPreview);
  $("[data-custom-title-color]").addEventListener("input", (event) => setTitleColor(event.target.value));
  $$("[data-catalog-search]").forEach((input) => {
    input.addEventListener("input", () => {
      state.filters[input.dataset.catalogSearch] = input.value;
      renderList(input.dataset.catalogSearch);
    });
  });
  $("[data-image-file]").addEventListener("change", (event) => {
    const [file] = event.target.files;
    if (!file) return;
    uploadImage(file).catch((error) => {
      revokePreviewObjectUrl();
      updateImagePreview(editorForm.elements.image.value);
      $("[data-upload-state]").textContent = error.message;
      setSaveState("error", error.message);
    });
    event.target.value = "";
  });

  const start = async () => {
    try {
      const response = await fetch(apiUrl, { cache: "no-store" });
      if (!response.ok) throw new Error("Не удалось загрузить данные каталогов");
      state.data = await response.json();
      renderLists();
      setSaveState("saved", "Все изменения сохранены");
      if (state.data.characters.length) openEditor("characters", 0);
    } catch (error) {
      setSaveState("error", error.message);
    }
  };

  start();
})();
