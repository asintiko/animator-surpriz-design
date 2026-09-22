(() => {
  "use strict";

  const list = document.querySelector("[data-show-list]");
  if (!list) return;

  const endpoints = ["/api/shows", "/surpriz/api/shows"];

  const loadCatalogs = async () => {
    for (const endpoint of endpoints) {
      try {
        const response = await fetch(endpoint, {
          cache: "no-cache",
          headers: { Accept: "application/json" },
        });
        if (!response.ok) continue;
        return await response.json();
      } catch (_) {}
    }
    throw new Error("catalog-unavailable");
  };

  const toPageHref = (href) => {
    const value = String(href || "").trim();
    return !value || value.startsWith("#") ? "/party-builder/" : value;
  };

  const toImageHref = (source) => {
    const value = String(source || "").trim();
    if (!value) return "";
    if (/^https?:\/\//i.test(value) || value.startsWith("/")) return value;
    return `/surpriz/${value.replace(/^\//, "")}`;
  };

  const makeTextElement = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
  };

  const toGroupSlug = (show) => String(show && show.variant_group_slug || "").trim();

  const collapseVariantGroups = (shows) => {
    const handled = new Set();
    return shows.flatMap((show) => {
      const groupSlug = toGroupSlug(show);
      if (!groupSlug) return [show];
      if (handled.has(groupSlug)) return [];
      handled.add(groupSlug);
      const variants = shows.filter((candidate) => toGroupSlug(candidate) === groupSlug);
      if (variants.length < 2) return [show];
      const groupName = String(variants[0].variant_group_name || "").trim();
      return [{
        ...variants[0],
        id: groupSlug,
        title: groupName || variants[0].title,
        variant_label: "",
        duration_label: "",
        price_label: "",
        cta_label: "Собрать шоу",
        variants,
      }];
    });
  };

  const makeResponsiveSource = (format, sources) => {
    if (!Array.isArray(sources) || !sources.length) return null;
    const source = document.createElement("source");
    source.type = `image/${format}`;
    source.srcset = sources
      .filter((item) => item && item.src && Number(item.width) > 0)
      .map((item) => `${toImageHref(item.src)} ${Number(item.width)}w`)
      .join(", ");
    source.sizes = "(max-width: 899px) calc(100vw - 28px), (max-width: 1100px) 52vw, 680px";
    return source.srcset ? source : null;
  };

  const createShowCard = (show, index) => {
    const article = document.createElement("article");
    article.className = "show-card";
    article.dataset.showId = String(show.id || "");
    // The homepage links here as /show-programs/#<group>, so each card needs an id.
    if (show.id) article.id = String(show.id);
    article.style.setProperty("--accent", show.title_color || "#6c1be3");

    const detailHref = String(show.detail_href || toPageHref(show.href));
    const media = document.createElement("a");
    media.href = detailHref;
    media.setAttribute("aria-label", `Подробнее: ${show.title || "шоу-программа"}`);
    media.className = "show-card__media";
    const imageHref = toImageHref(show.image);
    if (!imageHref) {
      media.classList.add("show-card__media--empty");
    } else {
      const picture = document.createElement("picture");
      const imageSources = show.image_sources || {};
      const avifSource = makeResponsiveSource("avif", imageSources.avif);
      const webpSource = makeResponsiveSource("webp", imageSources.webp);
      if (avifSource) picture.append(avifSource);
      if (webpSource) picture.append(webpSource);
      const image = document.createElement("img");
      image.src = imageHref;
      image.alt = show.alt || show.title || "Шоу-программа";
      image.loading = "lazy";
      image.decoding = "async";
      image.width = Math.max(1, Number(show.image_width) || 1200);
      image.height = Math.max(1, Number(show.image_height) || 1600);
      const position = show.image_position || {};
      image.style.objectPosition = `${position.x ?? 50}% ${position.y ?? 50}%`;
      image.style.objectFit = show.cover_fit === "contain" ? "contain" : "cover";
      image.style.transformOrigin = `${position.x ?? 50}% ${position.y ?? 50}%`;
      const zoom = Math.max(100, Math.min(200, Number(show.image_zoom) || 100)) / 100;
      image.style.setProperty("--image-zoom", zoom);
      const mobilePosition = show.mobile_image_position || position;
      const mobileZoom = Math.max(100, Math.min(200, Number(show.mobile_image_zoom) || Number(show.image_zoom) || 100)) / 100;
      image.style.setProperty("--mobile-image-x", `${mobilePosition.x ?? position.x ?? 50}%`);
      image.style.setProperty("--mobile-image-y", `${mobilePosition.y ?? position.y ?? 50}%`);
      const mobileFit = show.mobile_cover_fit === "contain" || show.mobile_cover_fit === "cover"
        ? show.mobile_cover_fit
        : (show.cover_fit === "contain" ? "contain" : "cover");
      image.style.setProperty("--mobile-image-fit", mobileFit);
      image.style.setProperty("--mobile-image-zoom", mobileZoom);
      picture.append(image);
      media.append(picture);
    }

    const body = document.createElement("div");
    body.className = "show-card__body";
    body.append(makeTextElement("span", "show-card__number", `Шоу-программа ${String(index + 1).padStart(2, "0")}`));
    const title = document.createElement("h3");
    title.className = "show-card__title";
    const titleLink = document.createElement("a");
    titleLink.className = "show-card__title-link";
    titleLink.href = detailHref;
    titleLink.textContent = show.title || "Шоу-программа";
    title.append(titleLink);
    body.append(title);
    body.append(makeTextElement("p", "show-card__description", show.description || "Яркая программа для вашего праздника."));

    const chips = document.createElement("div");
    chips.className = "show-card__chips";
    const ageLabel = String(show.age_label || "").trim();
    const hasMeaningfulAge = ageLabel && !/^0\s*[-–]\s*0\b/.test(ageLabel);
    const durationChip = makeTextElement("span", "show-card__chip", "");
    const priceChip = makeTextElement("span", "show-card__chip", "");
    const factElements = [durationChip, priceChip];
    if (hasMeaningfulAge) factElements.push(makeTextElement("span", "show-card__chip", `Возраст: ${ageLabel}`));
    if (show.variant_label) factElements.push(makeTextElement("span", "show-card__chip", `Формат: ${show.variant_label}`));
    const setFact = (chip, prefix, value) => {
      const text = String(value || "").trim();
      chip.textContent = text ? `${prefix}: ${text}` : "";
    };
    const syncFacts = () => {
      const visible = factElements.filter((chip) => chip.textContent);
      chips.replaceChildren(...visible);
      chips.hidden = !visible.length;
    };
    setFact(durationChip, "Длительность", show.duration_label);
    setFact(priceChip, "Стоимость", show.price_label);
    syncFacts();
    body.append(chips);

    const actions = document.createElement("div");
    actions.className = "show-card__actions";
    const order = document.createElement("a");
    order.className = "show-card__order";
    order.href = toPageHref(show.href);
    order.textContent = show.cta_label || "Заказать";
    order.setAttribute("aria-label", `${order.textContent}: ${show.title || "шоу-программа"}`);
    const question = document.createElement("a");
    question.className = "show-card__question";
    question.href = detailHref;
    question.textContent = "Подробнее →";

    const variants = Array.isArray(show.variants) ? show.variants : [];
    if (variants.length) {
      const fieldset = document.createElement("fieldset");
      fieldset.className = "show-card__variants";
      const legend = document.createElement("legend");
      legend.textContent = "Выберите формат";
      fieldset.append(legend);

      const selectVariant = (variant) => {
        const detailHref = String(variant.detail_href || toPageHref(variant.href));
        order.href = toPageHref(variant.href);
        order.setAttribute("aria-label", `${order.textContent}: ${show.title}, ${variant.variant_label || variant.title}`);
        titleLink.href = detailHref;
        question.href = detailHref;
        question.textContent = "Подробнее о формате →";
        setFact(durationChip, "Длительность", variant.duration_label || show.duration_label);
        setFact(priceChip, "Стоимость", variant.price_label || show.price_label);
        syncFacts();
      };

      variants.forEach((variant, variantIndex) => {
        const label = document.createElement("label");
        label.className = "show-card__variant";
        const input = document.createElement("input");
        input.type = "radio";
        input.name = `show-variant-${show.id || index}`;
        input.value = variant.id || variant.variant_label || String(variantIndex);
        input.checked = variantIndex === 0;

        const choice = document.createElement("span");
        choice.className = "show-card__variant-choice";
        const copy = document.createElement("span");
        copy.className = "show-card__variant-copy";
        copy.append(
          makeTextElement("strong", "", variant.variant_label || variant.title || "Формат"),
          makeTextElement("small", "", variant.description || ""),
        );
        choice.append(copy, makeTextElement("b", "", variant.price_label || ""));
        label.append(input, choice);
        input.addEventListener("change", () => {
          if (input.checked) selectVariant(variant);
        });
        fieldset.append(label);
      });

      body.append(fieldset);
      selectVariant(variants[0]);
    }

    actions.append(order, question);
    body.append(actions);

    article.append(media, body);
    return article;
  };

  const observeCards = () => {
    const cards = [...document.querySelectorAll(".show-card:not(.show-card--loading)")];
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!("IntersectionObserver" in window) || reducedMotion) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.animate(
            [
              { opacity: 0.72, transform: "translateY(12px)" },
              { opacity: 1, transform: "translateY(0)" },
            ],
            { duration: 360, easing: "cubic-bezier(.2,.7,.2,1)", fill: "none" },
          );
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8%", threshold: 0.08 },
    );
    cards.forEach((card) => observer.observe(card));
  };

  const render = async () => {
    try {
      const data = await loadCatalogs();
      const shows = (Array.isArray(data.shows) ? data.shows : []).filter(
        (show) => show && show.active !== false && Array.isArray(show.placements) && show.placements.includes("catalog"),
      );
      if (!shows.length) throw new Error("empty-catalog");
      const displayShows = collapseVariantGroups(shows);
      list.replaceChildren(...displayShows.map(createShowCard));
      list.setAttribute("aria-busy", "false");
      observeCards();
      // Cards render after navigation, so the browser has already given up on
      // the hash by the time the target exists.
      const requested = decodeURIComponent(window.location.hash.slice(1));
      if (requested) {
        const target = document.getElementById(requested);
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "center" });
          target.classList.add("show-card--highlighted");
          window.setTimeout(() => target.classList.remove("show-card--highlighted"), 2400);
        }
      }
    } catch (_) {
      const message = document.createElement("p");
      message.className = "show-catalog__error";
      message.textContent = "Каталог временно не загрузился. Позвоните нам — мы расскажем обо всех программах.";
      list.replaceChildren(message);
      list.setAttribute("aria-busy", "false");
    }
  };

  render();
})();
