(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function setupReveals() {
    const items = [...document.querySelectorAll("[data-reveal]")];
    if (reduceMotion || !("IntersectionObserver" in window)) {
      items.forEach((item) => item.classList.add("v4-reveal-visible"));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.remove("v4-reveal-pending");
          entry.target.classList.add("v4-reveal-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8%", threshold: 0.08 },
    );

    items.forEach((item) => {
      if (item.getBoundingClientRect().top > window.innerHeight * 0.9) {
        item.classList.add("v4-reveal-pending");
        observer.observe(item);
      } else {
        item.classList.add("v4-reveal-visible");
      }
    });
  }

  function parseCharacters() {
    const data = document.querySelector("#v4-character-data");
    if (!data) return [];
    try {
      const parsed = JSON.parse(data.textContent || "[]");
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  function normalize(value) {
    return String(value || "")
      .toLocaleLowerCase("ru")
      .replace(/ё/g, "е")
      .trim();
  }

  function characterWord(count) {
    const tens = count % 100;
    const units = count % 10;
    if (tens >= 11 && tens <= 14) return "персонажей";
    if (units === 1) return "персонаж";
    if (units >= 2 && units <= 4) return "персонажа";
    return "персонажей";
  }

  function createCharacterCard(character) {
    const link = document.createElement("a");
    link.className = "v4-character";
    link.href = character.route || "/catalog/";

    const media = document.createElement("span");
    media.className = "v4-character__media";

    const image = document.createElement("img");
    image.src = character.hero || "";
    image.alt = character.name || "Персонаж";
    image.width = 480;
    image.height = 600;
    image.loading = "lazy";
    image.decoding = "async";
    image.style.objectFit = character.cover_fit === "contain" ? "contain" : "cover";
    const x = Number.isFinite(Number(character.cover_x)) ? Number(character.cover_x) : 50;
    const y = Number.isFinite(Number(character.cover_y)) ? Number(character.cover_y) : 50;
    image.style.objectPosition = `${Math.max(0, Math.min(100, x))}% ${Math.max(0, Math.min(100, y))}%`;
    media.append(image);

    const name = document.createElement("strong");
    name.textContent = character.name || "Персонаж";

    const category = document.createElement("small");
    category.textContent = character.primary_category || "Персонаж";

    link.append(media, name, category);
    return link;
  }

  function createEmptyState() {
    const empty = document.createElement("div");
    empty.className = "v4-catalog-empty";

    const title = document.createElement("h3");
    title.textContent = "Такого героя пока не нашли";

    const copy = document.createElement("p");
    copy.textContent = "Попробуйте другое имя или сбросьте категорию — выбранные фильтры останутся на месте.";

    empty.append(title, copy);
    return empty;
  }

  function setupCatalog() {
    const characters = parseCharacters();
    const grid = document.querySelector("[data-character-grid]");
    const search = document.querySelector("[data-character-search]");
    const filterGroup = document.querySelector("[data-character-filters]");
    const status = document.querySelector("[data-character-status]");
    const more = document.querySelector("[data-character-more]");
    if (!characters.length || !grid || !search || !filterGroup || !status || !more) return;

    const state = {
      filter: "all",
      query: "",
      limit: window.matchMedia("(min-width: 900px)").matches ? 10 : 8,
    };

    const pageSize = () => (window.matchMedia("(min-width: 900px)").matches ? 10 : 8);

    function filteredCharacters() {
      const query = normalize(state.query);
      return characters.filter((character) => {
        const categories = Array.isArray(character.categories) ? character.categories : [];
        const matchesCategory = state.filter === "all" || categories.includes(state.filter);
        const matchesQuery = !query || normalize(character.name).includes(query);
        return matchesCategory && matchesQuery;
      });
    }

    function render() {
      const matches = filteredCharacters();
      const visible = matches.slice(0, state.limit);
      const fragment = document.createDocumentFragment();
      visible.forEach((character) => fragment.append(createCharacterCard(character)));
      if (!matches.length) fragment.append(createEmptyState());

      grid.setAttribute("aria-busy", "true");
      grid.replaceChildren(fragment);
      grid.removeAttribute("aria-busy");

      status.textContent = state.query || state.filter !== "all"
        ? `Найдено: ${matches.length} ${characterWord(matches.length)}`
        : `${matches.length} ${characterWord(matches.length)}`;

      const remaining = Math.max(0, matches.length - visible.length);
      more.hidden = remaining === 0;
      more.textContent = remaining ? `Показать ещё (${remaining})` : "Показать ещё";
    }

    filterGroup.addEventListener("click", (event) => {
      const button = event.target.closest("[data-character-filter]");
      if (!button) return;
      state.filter = button.dataset.characterFilter || "all";
      state.limit = pageSize();
      filterGroup.querySelectorAll("[data-character-filter]").forEach((candidate) => {
        candidate.setAttribute("aria-pressed", candidate === button ? "true" : "false");
      });
      button.scrollIntoView({ inline: "center", block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
      render();
    });

    search.addEventListener("input", () => {
      state.query = search.value;
      state.limit = pageSize();
      render();
    });

    search.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !search.value) return;
      search.value = "";
      state.query = "";
      state.limit = pageSize();
      render();
    });

    more.addEventListener("click", () => {
      state.limit += pageSize();
      render();
    });

    render();
  }

  setupCatalog();
  setupReveals();
})();
