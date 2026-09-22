(() => {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const desktopMode = window.matchMedia("(min-width: 851px)");
  const DATA_SOURCES = ["/api/catalogs"];
  const AUTOPLAY_DELAY = 3800;
  const MANUAL_PAUSE = 5200;
  const CHARACTER_CATEGORY_LABELS = {
    all: "Все персонажи",
    superheroes: "Супергерои",
    princesses: "Принцессы",
    boys: "Для мальчиков",
    girls: "Для девочек",
    cartoons: "Мультгерои",
  };
  const requestedCategory = new URLSearchParams(window.location.search).get("character");
  const selectedCharacterCategory = Object.hasOwn(CHARACTER_CATEGORY_LABELS, requestedCategory || "")
    ? requestedCategory
    : null;

  const loadCatalogData = async () => {
    let lastError = null;
    for (const source of DATA_SOURCES) {
      try {
        const response = await fetch(new URL(source, document.baseURI), { cache: "no-cache" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("Не удалось загрузить каталоги");
  };

  const characterImageBase = (source) => {
    const match = source.match(/^(\/surpriz\/assets\/img\/characters\/.+)-(?:800|1200)\.webp(?:\?.*)?$/);
    return match ? match[1] : "";
  };

  const makeSource = (format, srcset, sizes) => {
    if (!srcset) return null;
    const source = document.createElement("source");
    source.type = `image/${format}`;
    source.srcset = srcset;
    source.sizes = sizes;
    return source;
  };

  const createCard = (item, kind) => {
    const clampPosition = (value) => {
      const numeric = Number(value);
      return Number.isFinite(numeric) ? Math.min(100, Math.max(0, numeric)) : 50;
    };
    const position = {
      x: clampPosition(item.image_position?.x),
      y: clampPosition(item.image_position?.y),
    };
    const numericZoom = Number(item.image_zoom);
    const zoom = Number.isFinite(numericZoom) ? Math.min(200, Math.max(100, numericZoom)) / 100 : 1;
    const listItem = document.createElement("li");
    listItem.className = "catalog-strip__item";
    listItem.dataset.itemId = item.id;

    const article = document.createElement("article");
    article.className = `catalog-card catalog-card--${kind === "shows" ? "show" : "character"}`;

    const builderHref = String(item.href || "/party-builder/");
    // The card itself opens the detail page (description, bigger photo); only the
    // order button jumps straight into the builder.
    const detailHref = String(item.detail_href || "").trim() || builderHref;
    const media = document.createElement("a");
    media.className = "catalog-card__media";
    media.href = detailHref;
    media.setAttribute("aria-label", `Подробнее: ${item.title}`);
    const picture = document.createElement("picture");
    const image = document.createElement("img");
    const imageSource = String(item.image || "").trim();
    const imageHref = !imageSource || /^https?:\/\//i.test(imageSource) || imageSource.startsWith("/")
      ? imageSource
      : `/surpriz/${imageSource.replace(/^\//, "")}`;
    const imageSizes = "(max-width: 600px) 46vw, (max-width: 850px) 32vw, 24vw";
    const characterBase = kind === "characters" ? characterImageBase(imageHref) : "";
    let imageSrc = "";
    if (item.image_sources) {
      ["avif", "webp"].forEach((format) => {
        const entries = Array.isArray(item.image_sources[format]) ? item.image_sources[format] : [];
        const srcset = entries
          .filter((entry) => entry && entry.src && Number(entry.width) > 0)
          .map((entry) => `${entry.src} ${entry.width}w`)
          .join(", ");
        const source = makeSource(format, srcset, imageSizes);
        if (source) picture.append(source);
      });
      imageSrc = String(item.image_sources.fallback || imageHref);
    } else if (characterBase) {
      picture.append(
        makeSource("avif", [480, 768, 1200].map((width) => `${characterBase}-${width}.avif?v=b970d6020c37 ${width}w`).join(", "), imageSizes),
        makeSource("webp", [480, 768, 1200].map((width) => `${characterBase}-${width}.webp?v=b970d6020c37 ${width}w`).join(", "), imageSizes),
      );
      imageSrc = `${characterBase}-1200.webp?v=b970d6020c37`;
    } else {
      imageSrc = imageHref;
    }
    if (imageSrc) image.src = imageSrc;
    image.alt = item.alt || item.title;
    image.loading = "lazy";
    image.decoding = "async";
    image.width = Number(item.image_width) || 800;
    image.height = Number(item.image_height) || 1200;
    const isCharacter = kind === "characters";
    const readFit = (value, fallback) => (value === "cover" || value === "contain" ? value : fallback);
    const fit = readFit(item.cover_fit, isCharacter ? "contain" : "cover");
    image.style.objectFit = fit;
    image.style.objectPosition = `${position.x}% ${position.y}%`;
    image.style.transformOrigin = `${position.x}% ${position.y}%`;
    // One formula everywhere — the admin editor, the detail pages and these cards
    // all paint object-position + scale, so a crop cannot look different per surface.
    image.style.transform = `scale(${zoom})`;

    const mobilePositionRaw = item.mobile_image_position || {};
    const mobilePosition = {
      x: clampPosition(mobilePositionRaw.x ?? position.x),
      y: clampPosition(mobilePositionRaw.y ?? position.y),
    };
    const mobileZoomRaw = Number(item.mobile_image_zoom);
    const mobileZoom = Number.isFinite(mobileZoomRaw) ? Math.min(200, Math.max(100, mobileZoomRaw)) / 100 : zoom;
    image.style.setProperty("--mobile-image-x", `${mobilePosition.x}%`);
    image.style.setProperty("--mobile-image-y", `${mobilePosition.y}%`);
    image.style.setProperty("--mobile-image-fit", readFit(item.mobile_cover_fit, fit));
    image.style.setProperty("--mobile-image-zoom", mobileZoom);
    if (imageSrc || picture.childElementCount) picture.append(image);
    media.append(picture);

    const body = document.createElement("div");
    body.className = "catalog-card__body";
    const title = document.createElement("h3");
    title.className = "catalog-card__title";
    const titleLink = document.createElement("a");
    titleLink.className = "catalog-card__title-link";
    titleLink.href = detailHref;
    titleLink.textContent = item.title;
    title.append(titleLink);
    if (/^#[0-9a-f]{6}$/i.test(item.title_color || "")) title.style.color = item.title_color;
    const description = document.createElement("p");
    description.className = "catalog-card__description";
    description.textContent = item.description;
    const order = document.createElement("a");
    order.className = "catalog-card__order";
    order.href = builderHref;
    order.textContent = item.cta_label || "Заказать";
    order.setAttribute("aria-label", `${order.textContent}: ${item.title}`);

    const details = document.createElement("a");
    details.className = "catalog-card__details";
    details.href = detailHref;
    details.textContent = "Подробнее";
    details.setAttribute("aria-label", `Подробнее: ${item.title}`);

    body.append(title, description, details, order);
    article.append(media, body);
    listItem.append(article);
    return listItem;
  };

  const makeClone = (item, copyName) => {
    const clone = item.cloneNode(true);
    clone.dataset.copy = copyName;
    clone.setAttribute("aria-hidden", "true");
    clone.inert = true;
    clone.querySelectorAll("a, button, input, select, textarea, [tabindex]").forEach((element) => {
      element.tabIndex = -1;
    });
    return clone;
  };

  const initCarousel = (carousel, items, settings) => {
    const viewport = carousel.querySelector("[data-catalog-viewport]");
    const track = carousel.querySelector("[data-catalog-track]");
    const previousButton = carousel.querySelector("[data-catalog-prev]");
    const nextButton = carousel.querySelector("[data-catalog-next]");
    const kind = carousel.dataset.catalogKind;
    const abortController = new AbortController();
    const { signal } = abortController;
    const pauseReasons = new Set();
    let autoplayTimer = 0;
    let manualTimer = 0;
    let scrollTimer = 0;
    let frameId = 0;
    let buttonFrameId = 0;
    let pointerStartX = 0;
    let pointerStartScroll = 0;
    let pointerId = null;
    let didDrag = false;
    let step = 0;
    let cycleWidth = 0;
    let originalStart = 0;
    let afterStart = 0;
    let circular = false;
    let buttonsEnabled = false;

    if (items) {
      const categoryMode = kind === "characters" && selectedCharacterCategory;
      const activeItems = items.filter((item) => {
        const placements = Array.isArray(item.placements) ? item.placements : [];
        const categories = Array.isArray(item.categories) ? item.categories : [];
        return (
          item.active !== false &&
          item.title &&
          item.image &&
          placements.includes(categoryMode ? "catalog" : "homepage") &&
          (!categoryMode || selectedCharacterCategory === "all" || categories.includes(selectedCharacterCategory))
        );
      });
      track.replaceChildren(...activeItems.map((item) => createCard(item, kind)));
      if (categoryMode) {
        carousel.setAttribute("aria-label", `Персонажи: ${CHARACTER_CATEGORY_LABELS[selectedCharacterCategory]}`);
      }
    }

    const sourceItems = [...track.children];
    sourceItems.forEach((item, index) => {
      item.dataset.copy = "original";
      item.dataset.position = String(index);
      item.dataset.itemId ||= `fallback-${kind}-${index}`;
    });

    const clearCopies = () => {
      track.querySelectorAll('[data-copy="before"], [data-copy="after"]').forEach((item) => item.remove());
    };

    const maximumScroll = () => Math.max(0, viewport.scrollWidth - viewport.clientWidth);

    const updateButtons = () => {
      previousButton.hidden = !buttonsEnabled;
      nextButton.hidden = !buttonsEnabled;
      if (!buttonsEnabled) {
        previousButton.disabled = true;
        nextButton.disabled = true;
        return;
      }
      if (circular) {
        previousButton.disabled = false;
        nextButton.disabled = false;
        return;
      }

      const maximum = maximumScroll();
      previousButton.disabled = viewport.scrollLeft <= 2;
      nextButton.disabled = maximum <= 2 || viewport.scrollLeft >= maximum - 2;
    };

    const scheduleButtonUpdate = () => {
      if (buttonFrameId) return;
      buttonFrameId = window.requestAnimationFrame(() => {
        buttonFrameId = 0;
        updateButtons();
      });
    };

    const setButtons = (enabled) => {
      buttonsEnabled = enabled;
      updateButtons();
    };

    const normalizePosition = () => {
      if (!circular || !cycleWidth) return;
      let nextScroll = viewport.scrollLeft;
      if (nextScroll < originalStart - step * 0.55) nextScroll += cycleWidth;
      if (nextScroll >= afterStart - step * 0.55) nextScroll -= cycleWidth;
      if (Math.abs(nextScroll - viewport.scrollLeft) > 1) {
        viewport.classList.add("is-jumping");
        viewport.scrollLeft = nextScroll;
        window.requestAnimationFrame(() => viewport.classList.remove("is-jumping"));
      }
    };

    const scheduleNormalize = () => {
      window.clearTimeout(scrollTimer);
      scrollTimer = window.setTimeout(normalizePosition, 140);
    };

    const scheduleAutoplay = () => {
      window.clearTimeout(autoplayTimer);
      if (
        !circular ||
        !desktopMode.matches ||
        reducedMotion.matches ||
        settings?.autoplay_enabled === false ||
        pauseReasons.size
      ) return;
      autoplayTimer = window.setTimeout(() => {
        moveBy(1, false);
        scheduleAutoplay();
      }, AUTOPLAY_DELAY);
    };

    const pause = (reason) => {
      pauseReasons.add(reason);
      window.clearTimeout(autoplayTimer);
    };

    const resume = (reason) => {
      pauseReasons.delete(reason);
      scheduleAutoplay();
    };

    const pauseAfterManualAction = () => {
      pause("manual");
      window.clearTimeout(manualTimer);
      manualTimer = window.setTimeout(() => resume("manual"), MANUAL_PAUSE);
    };

    function moveBy(direction, isManual = true) {
      if (!step) return;
      viewport.scrollBy({
        behavior: reducedMotion.matches ? "auto" : "smooth",
        left: step * direction,
      });
      if (isManual) pauseAfterManualAction();
    }

    const measure = ({ preservePosition = true } = {}) => {
      window.cancelAnimationFrame(frameId);
      frameId = window.requestAnimationFrame(() => {
        const originalItems = [...track.querySelectorAll('[data-copy="original"]')];
        const visibleCount = Math.max(1, Math.round(viewport.clientWidth / (originalItems[0]?.getBoundingClientRect().width || viewport.clientWidth)));
        const shouldLoop = desktopMode.matches && originalItems.length > visibleCount;
        const currentItem = originalItems.reduce((closest, item) => {
          if (!closest) return item;
          return Math.abs(item.offsetLeft - viewport.scrollLeft) < Math.abs(closest.offsetLeft - viewport.scrollLeft) ? item : closest;
        }, null);
        const currentId = currentItem?.dataset.itemId;

        clearCopies();
        circular = false;
        cycleWidth = 0;
        originalStart = 0;
        afterStart = 0;

        if (shouldLoop) {
          const before = originalItems.map((item) => makeClone(item, "before"));
          const after = originalItems.map((item) => makeClone(item, "after"));
          track.prepend(...before);
          track.append(...after);
          const firstOriginal = track.querySelector('[data-copy="original"]');
          const secondOriginal = firstOriginal?.nextElementSibling;
          const firstAfter = track.querySelector('[data-copy="after"]');
          originalStart = firstOriginal?.offsetLeft || 0;
          afterStart = firstAfter?.offsetLeft || 0;
          step = secondOriginal ? secondOriginal.offsetLeft - originalStart : viewport.clientWidth;
          cycleWidth = afterStart - originalStart;
          circular = cycleWidth > step;
          if (!preservePosition || viewport.scrollLeft < step) viewport.scrollLeft = originalStart;
          else normalizePosition();
        } else {
          const first = originalItems[0];
          const second = originalItems[1];
          step = second ? second.offsetLeft - first.offsetLeft : viewport.clientWidth;
          if (!preservePosition) {
            viewport.scrollLeft = first?.offsetLeft || 0;
          } else if (currentId) {
            const current = track.querySelector(`[data-item-id="${CSS.escape(currentId)}"]`);
            if (current) viewport.scrollLeft = current.offsetLeft;
          }
        }

        setButtons(sourceItems.length > visibleCount);
        carousel.classList.toggle("is-circular", circular);
        scheduleAutoplay();
      });
    };

    previousButton.addEventListener("click", () => moveBy(-1), { signal });
    nextButton.addEventListener("click", () => moveBy(1), { signal });
    viewport.addEventListener("scroll", () => {
      scheduleNormalize();
      scheduleButtonUpdate();
    }, { passive: true, signal });
    viewport.addEventListener("scrollend", () => {
      normalizePosition();
      updateButtons();
    }, { signal });
    viewport.addEventListener("keydown", (event) => {
      if (event.target !== viewport) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        moveBy(event.key === "ArrowLeft" ? -1 : 1);
      }
    }, { signal });

    carousel.addEventListener("pointerenter", () => pause("hover"), { signal });
    carousel.addEventListener("pointerleave", () => resume("hover"), { signal });
    carousel.addEventListener("focusin", () => pause("focus"), { signal });
    carousel.addEventListener("focusout", () => {
      window.requestAnimationFrame(() => {
        if (!carousel.matches(":focus-within")) resume("focus");
      });
    }, { signal });

    viewport.addEventListener("pointerdown", (event) => {
      if (event.pointerType !== "mouse" || event.button !== 0) return;
      pointerId = event.pointerId;
      pointerStartX = event.clientX;
      pointerStartScroll = viewport.scrollLeft;
      didDrag = false;
      // Capturing here retargets every later event — including the click — to the
      // viewport, so links inside the cards never received it. Capture only once
      // the pointer has actually travelled far enough to be a drag.
      viewport.classList.add("is-dragging");
      pause("drag");
    }, { signal });

    viewport.addEventListener("pointermove", (event) => {
      if (pointerId !== event.pointerId) return;
      const distance = event.clientX - pointerStartX;
      // A small threshold treated the slightest wobble during a click as a drag.
      if (!didDrag && Math.abs(distance) > 12) {
        didDrag = true;
        viewport.setPointerCapture(pointerId);
      }
      if (!didDrag) return;
      event.preventDefault();
      viewport.scrollLeft = pointerStartScroll - distance;
    }, { signal });

    const finishDrag = (event) => {
      if (pointerId !== event.pointerId) return;
      if (viewport.hasPointerCapture(pointerId)) viewport.releasePointerCapture(pointerId);
      pointerId = null;
      viewport.classList.remove("is-dragging");
      resume("drag");
      if (didDrag && step) {
        viewport.scrollTo({
          behavior: reducedMotion.matches ? "auto" : "smooth",
          left: Math.round(viewport.scrollLeft / step) * step,
        });
        pauseAfterManualAction();
      }
      // Clear the flag right after the click that follows this pointerup, so a
      // drag can never swallow a later, unrelated click.
      window.setTimeout(() => { didDrag = false; }, 0);
    };
    viewport.addEventListener("pointerup", finishDrag, { signal });
    viewport.addEventListener("pointercancel", finishDrag, { signal });
    viewport.addEventListener("click", (event) => {
      if (!didDrag) return;
      event.preventDefault();
      event.stopPropagation();
      didDrag = false;
    }, { capture: true, signal });

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) pause("hidden");
      else resume("hidden");
    }, { signal });

    const mediaChanged = () => measure({ preservePosition: false });
    desktopMode.addEventListener("change", mediaChanged, { signal });
    reducedMotion.addEventListener("change", scheduleAutoplay, { signal });
    if ("ResizeObserver" in window) {
      const observer = new ResizeObserver(() => measure());
      observer.observe(viewport);
      signal.addEventListener("abort", () => observer.disconnect(), { once: true });
    } else {
      window.addEventListener("resize", measure, { passive: true, signal });
    }

    measure({ preservePosition: false });
    window.addEventListener("pageshow", () => measure(), { signal });
    return () => {
      abortController.abort();
      window.clearTimeout(autoplayTimer);
      window.clearTimeout(manualTimer);
      window.clearTimeout(scrollTimer);
      window.cancelAnimationFrame(frameId);
      window.cancelAnimationFrame(buttonFrameId);
    };
  };

  // Partner logos are managed in the admin panel. The markup ships with the
  // current set so the strip survives an API outage; a live answer replaces it.
  const renderPartners = (partners) => {
    const strip = document.querySelector(".legacy-trust__logos");
    if (!strip || !Array.isArray(partners) || !partners.length) return;
    const nodes = partners
      .filter((partner) => partner && String(partner.logo || "").trim())
      .map((partner) => {
        const image = document.createElement("img");
        image.src = String(partner.logo);
        image.alt = String(partner.name || "Партнёр");
        image.loading = "lazy";
        image.decoding = "async";
        const href = String(partner.href || "").trim();
        if (!href) return image;
        const link = document.createElement("a");
        link.href = href;
        link.rel = "noopener";
        if (/^https?:\/\//i.test(href)) link.target = "_blank";
        link.append(image);
        return link;
      });
    if (nodes.length) strip.replaceChildren(...nodes);
  };

  // Neon Start/Medium/Lux and the two Squid Game lengths are formats of one
  // programme, not separate shows. The builder and the show catalog already
  // collapse them; the homepage carousel showed every variant as its own card.
  const collapseShowVariants = (shows) => {
    if (!Array.isArray(shows)) return shows;
    const handled = new Set();
    return shows.flatMap((show) => {
      const groupSlug = String(show?.variant_group_slug || "").trim();
      if (!groupSlug) return [show];
      if (handled.has(groupSlug)) return [];
      handled.add(groupSlug);
      const variants = shows.filter((item) => String(item?.variant_group_slug || "").trim() === groupSlug);
      if (variants.length < 2) return [show];
      const groupName = String(variants[0].variant_group_name || "").trim();
      return [{
        ...variants[0],
        id: groupSlug,
        title: groupName || variants[0].title,
        alt: groupName || variants[0].alt,
        cta_label: "Выбрать формат",
        // Send the visitor to the show catalog, where the grouped card lists
        // every format with its price so they can compare before ordering.
        href: `/show-programs/#${groupSlug}`,
        detail_href: `/show-programs/#${groupSlug}`,
        variant_count: variants.length,
      }];
    });
  };

  const start = async () => {
    const carousels = [...document.querySelectorAll("[data-catalog-carousel]")];
    let data = null;
    try {
      data = await loadCatalogData();
    } catch (error) {
      console.warn("Каталоги работают на встроенных резервных карточках.", error);
    }

    carousels.forEach((carousel) => {
      const kind = carousel.dataset.catalogKind;
      const items = kind === "shows" ? collapseShowVariants(data?.[kind]) : data?.[kind];
      initCarousel(carousel, items, data?.settings || {});
    });
    renderPartners(data?.partners);
  };

  start();
})();
