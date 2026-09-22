(() => {
  "use strict";

  const grid = document.querySelector("[data-character-grid]");
  const filtersBar = document.querySelector("[data-filters]");
  const emptyMessage = document.querySelector("[data-empty]");
  const searchInput = document.querySelector("[data-character-search]");
  const searchClear = document.querySelector("[data-search-clear]");
  const searchStatus = document.querySelector("[data-search-status]");
  if (!grid) return;

  const endpoints = ["/api/catalogs"];
  let CATEGORY_LABELS = {
    superheroes: "Супергерой",
    princesses: "Принцесса",
    boys: "Для мальчиков",
    girls: "Для девочек",
    cartoons: "Мультгерой",
  };
  let CATEGORY_ORDER = ["superheroes", "princesses", "cartoons", "boys", "girls"];

  const CYR_TO_LAT = {
    а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "e", ж: "zh", з: "z",
    и: "i", й: "y", к: "k", л: "l", м: "m", н: "n", о: "o", п: "p", р: "r",
    с: "s", т: "t", у: "u", ф: "f", х: "h", ц: "c", ч: "ch", ш: "sh", щ: "sch",
    ъ: "", ы: "y", ь: "", э: "e", ю: "yu", я: "ya",
  };
  const LAT_TO_CYR_DIGRAPHS = [
    ["shch", "щ"], ["sch", "щ"], ["zh", "ж"], ["ch", "ч"], ["sh", "ш"],
    ["yo", "ё"], ["ya", "я"], ["yu", "ю"], ["ts", "ц"], ["kh", "х"],
    ["ye", "е"], ["ph", "ф"],
  ];
  const LAT_TO_CYR_SINGLE = {
    a: "а", b: "б", c: "к", d: "д", e: "е", f: "ф", g: "г", h: "х", i: "и",
    j: "й", k: "к", l: "л", m: "м", n: "н", o: "о", p: "п", q: "к", r: "р",
    s: "с", t: "т", u: "у", v: "в", w: "в", x: "кс", y: "ы", z: "з",
  };
  const SYNONYM_GROUPS = [
    ["паук", "spider", "spiderman", "spaydermen", "человек паук", "чел паук"],
    ["ледибаг", "ladybug", "miraculous", "леди баг", "супер кот", "cat noir", "супергерои"],
    ["эльза", "elsa", "frozen", "холодное сердце"],
    ["анна", "anna", "frozen", "холодное сердце"],
    ["олаф", "olaf", "frozen", "снеговик", "холодное сердце"],
    ["рапунцель", "rapunzel", "tangled"],
    ["белль", "belle", "beauty and the beast", "красавица и чудовище"],
    ["бэтмен", "batman"],
    ["супермен", "superman", "супергёрл", "supergirl"],
    ["халк", "hulk"],
    ["капитан америка", "captain america"],
    ["железный человек", "iron man", "ironman"],
    ["чёрная пантера", "black panther", "черная пантера", "ваканда"],
    ["дэдпул", "deadpool"],
    ["наруто", "naruto", "сакура", "sakura", "аниме", "ниндзя", "ninja"],
    ["микки", "mickey", "минни", "minnie", "мышонок", "disney", "дисней"],
    ["соник", "sonic", "эми", "amy", "ёжик соник"],
    ["винни пух", "winnie pooh", "винни", "pooh"],
    ["маша и медведь", "masha", "маша", "медведь", "bear"],
    ["щенячий патруль", "paw patrol", "чейз", "chase", "скай", "skye", "гонщик"],
    ["три кота", "kid e cats", "коржик", "карамелька", "компот", "котики"],
    ["фиксики", "fixies", "симка", "нолик", "simka", "nolik"],
    ["among us", "амонг ас", "амонгас", "инопланетяне"],
    ["помни", "pomni", "digital circus", "цифровой цирк"],
    ["леди баг", "ladybug"],
    ["жасмин", "jasmine", "аладдин", "aladdin"],
    ["пони", "pony", "my little pony", "единорог", "unicorn", "радужная пони"],
    ["hello kitty", "хелло китти", "китти", "kitty", "sanrio", "санрио"],
    ["куроми", "kuromi", "my melody", "май мелоди", "sanrio"],
    ["акула", "shark", "baby shark", "бэби шарк", "малыш акула"],
    ["динозавр", "dinosaur", "ти рекс", "trex", "t rex", "тирекс"],
    ["клоун", "clown", "клоуны"],
    ["игра в кальмара", "squid game", "сквид гейм"],
    ["brawl stars", "бравл старс", "спайк", "шелли", "ворон", "spike", "shelly", "crow"],
    ["лабубу", "labubu"],
    ["зверополис", "zootopia", "джуди", "ник", "judy", "nick"],
    ["пряничные человечки", "gingerbread", "пряник"],
    ["футболисты", "football", "футбол", "футболист", "soccer"],
    ["сафари", "safari", "джунгли", "животные"],
    ["стимпанк", "steampunk"],
    ["гавайская вечеринка", "hawaii", "гавайи", "hawaiian"],
    ["морская команда", "sailors", "моряки", "море"],
    ["спортивная вечеринка", "sport", "спорт"],
    ["племенная вечеринка", "tribal", "племя"],
    ["принцесса", "princess", "принцессы"],
    ["дед мороз", "santa", "санта", "санта клаус", "новый год"],
    ["снегурочка", "snow maiden"],
    ["супергерой", "superhero", "супергерои", "марвел", "marvel", "dc"],
    ["мультгерой", "cartoon", "мультик", "мультфильм", "мультгерои"],
    ["девочка", "girl", "девочкам", "для девочек"],
    ["мальчик", "boy", "мальчикам", "для мальчиков"],
  ];

  const normalizeSearch = (value) => {
    const lowered = String(value ?? "").toLowerCase();
    let out = "";
    for (const char of lowered) out += CYR_TO_LAT[char] ?? char;
    return out
      .normalize("NFKD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
  };

  const latinToCyrillic = (value) => {
    let text = String(value ?? "").toLowerCase();
    for (const [latin, cyr] of LAT_TO_CYR_DIGRAPHS) text = text.split(latin).join(cyr);
    let out = "";
    for (const char of text) out += LAT_TO_CYR_SINGLE[char] ?? char;
    return out;
  };

  const SYNONYM_INDEX = (() => {
    const index = new Map();
    for (const group of SYNONYM_GROUPS) {
      const forms = new Set();
      for (const term of group) {
        const normalized = normalizeSearch(term);
        if (!normalized) continue;
        forms.add(normalized);
        forms.add(normalized.replace(/ /g, ""));
      }
      for (const form of forms) {
        const existing = index.get(form) || new Set();
        forms.forEach((value) => existing.add(value));
        index.set(form, existing);
      }
    }
    return index;
  })();

  const expandQueryVariants = (value) => {
    const variants = new Set();
    const raw = String(value ?? "").toLowerCase().trim();
    if (!raw) return variants;
    const candidates = new Set([raw]);
    const cyrillicForm = latinToCyrillic(raw);
    if (cyrillicForm !== raw) candidates.add(cyrillicForm);
    for (const candidate of candidates) {
      const normalized = normalizeSearch(candidate);
      if (!normalized) continue;
      variants.add(normalized);
      const compact = normalized.replace(/ /g, "");
      if (compact) variants.add(compact);
      for (const key of [normalized, compact]) {
        const synonyms = SYNONYM_INDEX.get(key);
        if (synonyms) synonyms.forEach((item) => variants.add(item));
      }
      for (const token of normalized.split(" ")) {
        const synonyms = SYNONYM_INDEX.get(token);
        if (synonyms) synonyms.forEach((item) => variants.add(item));
      }
    }
    return variants;
  };

  const buildHaystack = (character) => {
    const parts = [
      character.title,
      character.id,
      character.description,
      character.alt,
      (character.categories || []).map((slug) => CATEGORY_LABELS[slug] || slug).join(" "),
      (character.categories || []).join(" "),
    ];
    const normalized = normalizeSearch(parts.join(" "));
    const extras = new Set();
    for (const token of normalized.split(" ")) {
      const synonyms = SYNONYM_INDEX.get(token);
      if (synonyms) synonyms.forEach((item) => extras.add(item));
    }
    const phrases = [normalizeSearch(character.title), normalized.replace(/ /g, "")];
    for (const phrase of phrases) {
      const synonyms = SYNONYM_INDEX.get(phrase);
      if (synonyms) synonyms.forEach((item) => extras.add(item));
    }
    const enriched = extras.size ? `${normalized} ${[...extras].sort().join(" ")}` : normalized;
    return { text: enriched, compact: enriched.replace(/ /g, "") };
  };

  const editDistanceAtMost = (a, b, limit) => {
    if (Math.abs(a.length - b.length) > limit) return false;
    let previous = Array.from({ length: b.length + 1 }, (_, index) => index);
    for (let i = 1; i <= a.length; i += 1) {
      const current = [i];
      let rowMin = i;
      for (let j = 1; j <= b.length; j += 1) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost);
        if (current[j] < rowMin) rowMin = current[j];
      }
      if (rowMin > limit) return false;
      previous = current;
    }
    return previous[b.length] <= limit;
  };

  const fuzzyContains = (haystack, needle, limit = 1) => {
    if (!needle || !haystack) return false;
    if (haystack.includes(needle)) return true;
    if (needle.length < 5) return false;
    for (const size of [needle.length - limit, needle.length, needle.length + limit]) {
      if (size <= 0 || size > haystack.length) continue;
      for (let i = 0; i <= haystack.length - size; i += 1) {
        if (editDistanceAtMost(haystack.slice(i, i + size), needle, limit)) return true;
      }
    }
    return false;
  };

  const matchesSearch = (character, query) => {
    const raw = query.trim();
    if (!raw) return true;
    const { text, compact } = character._search;
    const variants = expandQueryVariants(raw);
    for (const variant of variants) {
      if (variant && (text.includes(variant) || compact.includes(variant))) return true;
    }
    const tokens = normalizeSearch(raw).split(" ").filter(Boolean);
    if (!tokens.length) return false;
    if (tokens.every((token) => text.includes(token) || compact.includes(token))) return true;
    return tokens.every((token) => fuzzyContains(text, token) || fuzzyContains(compact, token));
  };

  const searchScore = (character, query) => {
    const normalizedQuery = normalizeSearch(query);
    const compactQuery = normalizedQuery.replace(/ /g, "");
    const name = normalizeSearch(character.title);
    const compactName = name.replace(/ /g, "");
    const variants = expandQueryVariants(query);
    const { text, compact } = character._search;
    if (name === normalizedQuery) return 0;
    if (compactQuery && compactName === compactQuery) return 1;
    if (name.startsWith(normalizedQuery)) return 2;
    if (normalizedQuery && name.includes(normalizedQuery)) return 3;
    if ([...variants].some((variant) => variant && name.includes(variant))) return 4;
    if (compactQuery && compact.includes(compactQuery)) return 5;
    if (normalizedQuery && text.includes(normalizedQuery)) return 6;
    if ([...variants].some((variant) => variant && text.includes(variant))) return 7;
    return 8;
  };

  let characters = [];
  let activeFilter = "all";
  let searchQuery = "";

  const loadCatalogs = async () => {
    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, { cache: "no-store" });
        if (!response.ok) continue;
        return await response.json();
      } catch (_) {
        // Try the static fallback below.
      }
    }
    throw new Error("catalog-unavailable");
  };

  const toPageHref = (href) => {
    const value = String(href || "").trim();
    return !value || value.startsWith("#") ? "/party-builder/" : value;
  };

  const toImageHref = (source) => {
    const value = String(source || "").trim();
    if (/^https?:\/\//i.test(value) || value.startsWith("/")) return value;
    return `/surpriz/${value.replace(/^\//, "")}`;
  };

  const characterImageBase = (source) => {
    const match = source.match(/^(\/surpriz\/assets\/img\/characters\/.+)-(?:800|1200)\.webp(?:\?.*)?$/);
    return match ? match[1] : "";
  };

  const makeCharacterSource = (base, format, sizes) => {
    if (!base) return null;
    const source = document.createElement("source");
    source.type = `image/${format}`;
    source.srcset = [480, 768, 1200].map((width) => `${base}-${width}.${format}?v=b08fa6fb14d2 ${width}w`).join(", ");
    source.sizes = sizes;
    return source;
  };

  const makePayloadSource = (entries, format, sizes) => {
    if (!Array.isArray(entries) || !entries.length) return null;
    const source = document.createElement("source");
    source.type = `image/${format}`;
    source.srcset = entries
      .filter((entry) => entry && entry.src && Number(entry.width) > 0)
      .map((entry) => `${entry.src} ${entry.width}w`)
      .join(", ");
    if (!source.srcset) return null;
    source.sizes = sizes;
    return source;
  };

  const makeTextElement = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
  };

  const primaryLabel = (categories) => {
    const list = Array.isArray(categories) ? categories : [];
    const match = CATEGORY_ORDER.find((category) => list.includes(category));
    return match ? CATEGORY_LABELS[match] : "Персонаж";
  };

  const createCharacterCard = (character, index) => {
    const article = document.createElement("article");
    article.className = "cat-card";
    article.style.setProperty("--accent", character.title_color || "#6c1be3");

    const media = document.createElement("div");
    media.className = "cat-card__media";
    const picture = document.createElement("picture");
    const image = document.createElement("img");
    const imageHref = toImageHref(character.image);
    const imageBase = characterImageBase(imageHref);
    const imageSources = character.image_sources && typeof character.image_sources === "object"
      ? character.image_sources
      : null;
    const imageSizes = "(max-width: 767px) 46vw, (max-width: 1100px) 30vw, 24vw";
    if (imageSources) {
      const avif = makePayloadSource(imageSources.avif, "avif", imageSizes);
      const webp = makePayloadSource(imageSources.webp, "webp", imageSizes);
      if (avif) picture.append(avif);
      if (webp) picture.append(webp);
      image.src = toImageHref(imageSources.fallback || imageHref);
    } else if (imageBase) {
      picture.append(makeCharacterSource(imageBase, "avif", imageSizes), makeCharacterSource(imageBase, "webp", imageSizes));
      image.src = `${imageBase}-1200.webp?v=b08fa6fb14d2`;
    } else {
      image.src = imageHref;
    }
    image.alt = character.alt || character.title || "Персонаж на детский праздник";
    image.loading = index < 4 ? "eager" : "lazy";
    image.decoding = "async";
    image.width = 800;
    image.height = 1200;
    const position = character.image_position || {};
    image.style.objectPosition = `${position.x ?? 50}% ${position.y ?? 50}%`;
    const zoom = Math.max(100, Math.min(200, Number(character.image_zoom) || 100)) / 100;
    image.style.setProperty("--image-zoom", zoom);
    picture.append(image);
    media.append(picture, makeTextElement("span", "cat-card__tag", primaryLabel(character.categories)));

    const body = document.createElement("div");
    body.className = "cat-card__body";
    const title = document.createElement("h3");
    title.className = "cat-card__title";
    const titleLink = document.createElement("a");
    titleLink.className = "cat-card__title-link";
    titleLink.href = String(character.detail_href || toPageHref(character.href));
    titleLink.textContent = character.title || "Персонаж";
    title.append(titleLink);
    body.append(title);
    body.append(
      makeTextElement(
        "p",
        "cat-card__description",
        character.description || "Любимый герой приедет на ваш праздник.",
      ),
    );

    const actions = document.createElement("div");
    actions.className = "cat-card__actions";
    const order = document.createElement("a");
    order.className = "cat-card__order";
    order.href = toPageHref(character.href);
    order.textContent = character.cta_label || "Заказать";
    order.setAttribute("aria-label", `${order.textContent}: ${character.title || "персонаж"}`);
    const question = document.createElement("a");
    question.className = "cat-card__question";
    question.href = String(character.detail_href || toPageHref(character.href));
    question.textContent = "Подробнее →";
    actions.append(order, question);
    body.append(actions);

    article.append(media, body);
    return article;
  };

  const revealCards = () => {
    const cards = [...grid.querySelectorAll(".cat-card:not(.cat-card--loading)")];
    if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      cards.forEach((card) => card.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -6%", threshold: 0.05 },
    );
    cards.forEach((card) => observer.observe(card));
  };

  const matchesCategory = (character, filter) =>
    filter === "all" ||
    (Array.isArray(character.categories) && character.categories.includes(filter));

  const matchesFilter = (character) =>
    matchesCategory(character, activeFilter) && matchesSearch(character, searchQuery);

  const renderGrid = () => {
    const visible = characters.filter(matchesFilter);
    if (searchQuery.trim()) {
      visible.sort((left, right) => searchScore(left, searchQuery) - searchScore(right, searchQuery));
    }
    grid.replaceChildren(...visible.map(createCharacterCard));
    if (emptyMessage) emptyMessage.hidden = visible.length > 0;
    if (searchStatus) {
      const query = searchQuery.trim();
      searchStatus.hidden = !query;
      if (query) {
        searchStatus.textContent = visible.length
          ? `Найдено: ${visible.length}`
          : "Ничего не нашли — попробуйте другое имя или выберите категорию";
      }
    }
    if (searchClear) searchClear.hidden = !searchQuery.trim();
    revealCards();
  };

  const updateFilters = () => {
    if (!filtersBar) return;
    filtersBar.hidden = false;
    const searched = characters.filter((character) => matchesSearch(character, searchQuery));
    filtersBar.querySelectorAll("[data-filter]").forEach((button) => {
      const value = button.dataset.filter;
      const count = searched.filter((character) => matchesCategory(character, value)).length;
      const counter = button.querySelector("[data-filter-count]");
      if (counter) counter.textContent = String(count);
      button.hidden = count === 0 && value !== activeFilter && value !== "all";
      const isActive = value === activeFilter;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  };

  const renderFilters = (filters) => {
    if (!filtersBar || !Array.isArray(filters) || !filters.length) return;
    const normalized = filters.filter((item) => item && item.slug && item.label);
    if (!normalized.some((item) => item.slug === "all")) {
      normalized.unshift({ slug: "all", label: "Все", icon: "/surpriz/assets/icons/categories/all-heroes.svg" });
    }
    CATEGORY_LABELS = Object.fromEntries(
      normalized.filter((item) => item.slug !== "all").map((item) => [item.slug, item.label]),
    );
    CATEGORY_ORDER = normalized.filter((item) => item.slug !== "all").map((item) => item.slug);
    filtersBar.replaceChildren(...normalized.map((item) => {
      const button = document.createElement("button");
      button.className = `cat-filter${item.slug === "all" ? " is-active" : ""}`;
      button.type = "button";
      button.dataset.filter = item.slug;
      button.setAttribute("aria-pressed", item.slug === "all" ? "true" : "false");
      const icon = document.createElement("img");
      icon.src = item.icon || "/surpriz/assets/icons/categories/all-heroes.svg";
      icon.alt = "";
      icon.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = item.label;
      const count = document.createElement("em");
      count.dataset.filterCount = "";
      count.textContent = "0";
      button.append(icon, label, count);
      return button;
    }));
  };

  const applyFilter = (value, { updateUrl = true } = {}) => {
    activeFilter = Object.prototype.hasOwnProperty.call(CATEGORY_LABELS, value) || value === "all" ? value : "all";
    updateFilters();
    renderGrid();
    if (!updateUrl) return;
    const url = new URL(window.location.href);
    if (activeFilter === "all") url.searchParams.delete("character");
    else url.searchParams.set("character", activeFilter);
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  };

  if (filtersBar) {
    filtersBar.addEventListener("click", (event) => {
      const button = event.target.closest("[data-filter]");
      if (!button) return;
      applyFilter(button.dataset.filter);
    });
  }

  const applySearch = (value) => {
    searchQuery = String(value || "").slice(0, 60);
    updateFilters();
    renderGrid();
  };

  if (searchInput) {
    let searchTimer = 0;
    searchInput.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => applySearch(searchInput.value), 140);
    });
    searchInput.addEventListener("search", () => applySearch(searchInput.value));
    searchInput.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !searchInput.value) return;
      searchInput.value = "";
      applySearch("");
    });
  }

  if (searchClear) {
    searchClear.addEventListener("click", () => {
      if (searchInput) {
        searchInput.value = "";
        searchInput.focus();
      }
      applySearch("");
    });
  }

  const render = async () => {
    try {
      const data = await loadCatalogs();
      renderFilters(data.filters);
      characters = (Array.isArray(data.characters) ? data.characters : []).filter(
        (character) =>
          character &&
          character.active !== false &&
          Array.isArray(character.placements) &&
          character.placements.includes("catalog"),
      );
      if (!characters.length) throw new Error("empty-catalog");
      characters.forEach((character) => {
        character._search = buildHaystack(character);
      });
      const params = new URL(window.location.href).searchParams;
      const requestedSearch = (params.get("q") || "").trim();
      if (requestedSearch && searchInput) {
        searchInput.value = requestedSearch.slice(0, 60);
        searchQuery = searchInput.value;
      }
      applyFilter(params.get("character") || "all", { updateUrl: false });
    } catch (_) {
      if (emptyMessage) emptyMessage.hidden = true;
      const message = document.createElement("p");
      message.className = "cat-catalog__error";
      message.textContent = "Каталог временно не загрузился. Позвоните нам — мы расскажем обо всех персонажах.";
      grid.replaceChildren(message);
    }
  };

  render();
})();
