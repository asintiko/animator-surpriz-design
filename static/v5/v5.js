(() => {
  "use strict";

  const root = document.documentElement;
  const body = document.body;
  const reducedMotionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const finePointerQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
  let prefersReducedMotion = reducedMotionQuery.matches;
  let revealObserver = null;

  const parseJson = (selector) => {
    const source = document.querySelector(selector);
    if (!source) {
      return [];
    }

    try {
      const value = JSON.parse(source.textContent || "[]");
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  };

  const createMediaPlaceholder = () => {
    const placeholder = document.createElement("span");
    placeholder.className = "v5-media-placeholder";
    placeholder.setAttribute("aria-hidden", "true");
    const mark = document.createElement("span");
    mark.append(document.createElement("i"), document.createElement("i"), document.createElement("i"));
    placeholder.append(mark);
    return placeholder;
  };

  const setMediaState = (image, state) => {
    const frame = image?.closest?.("[data-media-frame]");
    if (!frame) return;
    frame.classList.toggle("is-loading", state === "loading");
    frame.classList.toggle("is-loaded", state === "loaded");
    frame.classList.toggle("is-error", state === "error");
  };

  const bindMediaImage = (image) => {
    if (!(image instanceof HTMLImageElement) || image.dataset.mediaStateBound === "true") return;
    image.dataset.mediaStateBound = "true";
    image.addEventListener("load", () => setMediaState(image, "loaded"));
    image.addEventListener("error", () => setMediaState(image, "error"));
    if (image.complete) {
      setMediaState(image, image.naturalWidth > 0 ? "loaded" : "error");
    } else {
      setMediaState(image, "loading");
    }
  };

  document.querySelectorAll("[data-media-image]").forEach(bindMediaImage);

  const setMotionPreference = (matches) => {
    prefersReducedMotion = matches;
    root.classList.toggle("v5-motion-ready", !matches);

    if (matches) {
      revealObserver?.disconnect();
      document.querySelectorAll(".v5-reveal-pending").forEach((element) => {
        element.classList.remove("v5-reveal-pending");
        element.classList.add("v5-reveal-visible");
      });
    }
  };

  setMotionPreference(prefersReducedMotion);
  reducedMotionQuery.addEventListener?.("change", (event) => {
    setMotionPreference(event.matches);
  });

  const header = document.querySelector("[data-header]");
  if (header) {
    let headerFrame = 0;
    const updateHeader = () => {
      header.classList.toggle("is-scrolled", window.scrollY > 16);
      headerFrame = 0;
    };

    updateHeader();
    window.addEventListener(
      "scroll",
      () => {
        if (!headerFrame) {
          headerFrame = window.requestAnimationFrame(updateHeader);
        }
      },
      { passive: true },
    );
  }

  const menu = document.querySelector("[data-menu]");
  const menuOpenButton = document.querySelector("[data-menu-open]");
  if (menu && menuOpenButton) {
    const menuCloseButtons = menu.querySelectorAll("[data-menu-close]");
    const menuPanel = menu.querySelector(".v5-menu__panel");
    const focusableSelector = [
      "a[href]",
      "button:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "textarea:not([disabled])",
      "[tabindex]:not([tabindex='-1'])",
    ].join(",");
    let menuIsOpen = false;
    let previousFocus = null;

    const closeMenu = ({ restoreFocus = true } = {}) => {
      if (!menuIsOpen) {
        return;
      }

      menuIsOpen = false;
      menu.classList.remove("is-open");
      menu.setAttribute("aria-hidden", "true");
      menu.setAttribute("inert", "");
      menuOpenButton.setAttribute("aria-expanded", "false");
      menuOpenButton.setAttribute("aria-label", "Открыть меню");
      body.classList.remove("v5-menu-open");

      if (restoreFocus) {
        const fallbackFocus = document.querySelector(".v5-header .v5-brand");
        const focusTarget = previousFocus instanceof HTMLElement && previousFocus.offsetParent !== null
          ? previousFocus
          : fallbackFocus;
        focusTarget?.focus({ preventScroll: true });
      }
    };

    const openMenu = () => {
      if (menuIsOpen) {
        return;
      }

      menuIsOpen = true;
      previousFocus = document.activeElement;
      menu.removeAttribute("inert");
      menu.setAttribute("aria-hidden", "false");
      menu.classList.add("is-open");
      menuOpenButton.setAttribute("aria-expanded", "true");
      menuOpenButton.setAttribute("aria-label", "Закрыть меню");
      body.classList.add("v5-menu-open");

      window.requestAnimationFrame(() => {
        menu.querySelector(".v5-menu__close")?.focus({ preventScroll: true });
      });
    };

    menuOpenButton.addEventListener("click", openMenu);
    menuCloseButtons.forEach((button) => button.addEventListener("click", closeMenu));
    menu.querySelectorAll("a[href]").forEach((link) => {
      link.addEventListener("click", () => {
        const hashTarget = link.hash ? document.querySelector(link.hash) : null;
        closeMenu({ restoreFocus: false });

        if (!hashTarget) {
          return;
        }

        window.requestAnimationFrame(() => {
          const focusTarget = hashTarget.querySelector("h2") || hashTarget;
          focusTarget.setAttribute("tabindex", "-1");
          focusTarget.focus({ preventScroll: true });
          focusTarget.addEventListener("blur", () => focusTarget.removeAttribute("tabindex"), { once: true });
        });
      });
    });

    document.addEventListener("keydown", (event) => {
      if (!menuIsOpen) {
        return;
      }

      if (event.key === "Escape") {
        event.preventDefault();
        closeMenu();
        return;
      }

      if (event.key !== "Tab") {
        return;
      }

      const focusable = [...(menuPanel?.querySelectorAll(focusableSelector) || [])].filter(
        (element) => element instanceof HTMLElement && element.offsetParent !== null,
      );
      if (!focusable.length) {
        event.preventDefault();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });

    window.addEventListener("resize", () => {
      if (menuIsOpen && window.innerWidth >= 900) {
        closeMenu();
      }
    });
  }

  const revealElements = [...document.querySelectorAll("[data-reveal]")];
  if (revealElements.length && !prefersReducedMotion && "IntersectionObserver" in window) {
    revealObserver = new IntersectionObserver(
      (entries, observer) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) {
            return;
          }

          entry.target.classList.remove("v5-reveal-pending");
          entry.target.classList.add("v5-reveal-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8%", threshold: 0.08 },
    );

    revealElements.forEach((element) => {
      if (element.getBoundingClientRect().top > window.innerHeight * 0.88) {
        element.classList.add("v5-reveal-pending");
        revealObserver.observe(element);
      } else {
        element.classList.add("v5-reveal-visible");
      }
    });
  } else {
    revealElements.forEach((element) => element.classList.add("v5-reveal-visible"));
  }

  const shows = parseJson("#v5-show-data");
  const showStage = document.querySelector("[data-show-active]");
  const showTriggers = [...document.querySelectorAll("[data-show-trigger]")];
  const showPicker = document.querySelector("[data-show-picker]");
  const showPickerItems = [...document.querySelectorAll("[data-show-picker-item]")];
  if (shows.length && showStage) {
    const image = showStage.querySelector("[data-show-image]");
    const title = showStage.querySelector("[data-show-title]");
    const price = showStage.querySelector("[data-show-price]");
    const duration = showStage.querySelector("[data-show-duration]");
    const summary = showStage.querySelector("[data-show-summary]");
    const announcement = showStage.querySelector("[data-show-announcement]");
    const showBody = showStage.querySelector(".v5-show-active__body");
    const detailLinks = showStage.querySelectorAll("[data-show-detail]");
    const builderLink = showStage.querySelector("[data-show-builder]");
    let activeShowIndex = 0;
    let activationToken = 0;

    const renderShowPicker = () => {
      const alternatives = shows
        .map((show, index) => ({ show, index }))
        .filter(({ index }) => index !== activeShowIndex);

      showPickerItems.forEach((item, slot) => {
        const option = alternatives[slot];
        item.hidden = !option;
        if (!option) return;
        const { show, index } = option;
        item.dataset.showPickerIndex = String(index);
        item.setAttribute("href", String(show.route || "/show-programs/"));
        const pickerImage = item.querySelector("[data-show-picker-image]");
        const pickerNumber = item.querySelector("[data-show-picker-number]");
        const pickerName = item.querySelector("[data-show-picker-name]");
        const pickerMeta = item.querySelector("[data-show-picker-meta]");
        if (pickerImage) pickerImage.src = String(show.hero || "");
        if (pickerNumber) pickerNumber.textContent = String(index + 1).padStart(2, "0");
        if (pickerName) pickerName.textContent = String(show.name || "Шоу-программа");
        if (pickerMeta) pickerMeta.textContent = [show.duration, show.price].filter(Boolean).join(" · ");
      });

      if (showPicker) showPicker.hidden = alternatives.length === 0;
    };

    const commitShow = (nextIndex) => {
      const show = shows[nextIndex];
      if (!show) return false;

      activeShowIndex = nextIndex;
      if (image) {
        setMediaState(image, "loading");
        image.src = String(show.hero || "");
        image.alt = String(show.name || "Шоу-программа");
        if (image.complete) {
          setMediaState(image, image.naturalWidth > 0 ? "loaded" : "error");
        }
      }
      if (title) title.textContent = String(show.name || "Шоу-программа");
      if (price) price.textContent = String(show.price || "Цена по запросу");
      if (duration) duration.textContent = String(show.duration || "");
      if (summary) summary.textContent = String(show.summary || "");
      if (announcement) {
        announcement.textContent = [show.name, show.duration, show.price].filter(Boolean).join(". ");
      }
      detailLinks.forEach((link) => link.setAttribute("href", String(show.route || "/show-programs/")));
      builderLink?.setAttribute("href", String(show.builder_url || "/party-builder/"));

      showTriggers.forEach((trigger, index) => {
        const isActive = index === nextIndex;
        trigger.classList.toggle("is-active", isActive);
        trigger.setAttribute("aria-pressed", String(isActive));
      });
      renderShowPicker();
      return true;
    };

    const preloadShowImage = (source) => new Promise((resolve) => {
      if (!source) {
        resolve();
        return;
      }
      const nextImage = new Image();
      let settled = false;
      const finish = async () => {
        if (settled) return;
        settled = true;
        try {
          await nextImage.decode?.();
        } catch {}
        resolve();
      };
      nextImage.onload = finish;
      nextImage.onerror = finish;
      nextImage.src = source;
      window.setTimeout(finish, 1400);
    });

    const waitForFade = () => new Promise((resolve) => {
      if (prefersReducedMotion || !showBody) {
        resolve();
        return;
      }
      let settled = false;
      const onTransitionEnd = (event) => {
        if (event.propertyName === "opacity") finish();
      };
      const finish = () => {
        if (settled) return;
        settled = true;
        showBody.removeEventListener("transitionend", onTransitionEnd);
        resolve();
      };
      showBody.addEventListener("transitionend", onTransitionEnd);
      window.setTimeout(finish, 220);
    });

    const activateShow = async (nextIndex) => {
      if (!shows[nextIndex]) return false;
      if (nextIndex === activeShowIndex) {
        activationToken += 1;
        showStage.classList.remove("is-switching");
        showStage.setAttribute("aria-busy", "false");
        return false;
      }

      const token = ++activationToken;
      showStage.setAttribute("aria-busy", "true");
      await preloadShowImage(String(shows[nextIndex].hero || ""));
      if (token !== activationToken) return false;
      showStage.classList.add("is-switching");
      await waitForFade();
      if (token !== activationToken) return false;
      const committed = commitShow(nextIndex);
      await new Promise((resolve) => window.requestAnimationFrame(() => {
        window.requestAnimationFrame(resolve);
      }));
      if (token === activationToken) {
        showStage.classList.remove("is-switching");
        showStage.setAttribute("aria-busy", "false");
      }
      return committed;
    };

    showTriggers.forEach((trigger) => {
      const index = Number.parseInt(trigger.dataset.showTrigger || "", 10);
      if (!Number.isInteger(index)) return;

      trigger.addEventListener("pointerenter", () => {
        if (finePointerQuery.matches) activateShow(index);
      });
      trigger.addEventListener("click", () => {
        const shouldReturnToStage = !finePointerQuery.matches && index !== activeShowIndex;
        activateShow(index).then((committed) => {
          if (committed && shouldReturnToStage) {
            showStage.scrollIntoView({
              behavior: prefersReducedMotion ? "auto" : "smooth",
              block: "start",
            });
          }
        });
      });
    });

    showPickerItems.forEach((item) => {
      item.addEventListener("click", (event) => {
        event.preventDefault();
        const index = Number.parseInt(item.dataset.showPickerIndex || "", 10);
        if (!Number.isInteger(index)) return;
        if (event.detail === 0 && title instanceof HTMLElement) {
          title.focus({ preventScroll: true });
        }
        activateShow(index).then((committed) => {
          if (!committed) return;
          showStage.scrollIntoView({
            behavior: prefersReducedMotion ? "auto" : "smooth",
            block: "start",
          });
        });
      });
    });

    renderShowPicker();
  }

  const characters = parseJson("#v5-character-data");
  const characterRail = document.querySelector("[data-character-rail]");
  const characterStatus = document.querySelector("[data-character-status]");
  const characterSearch = document.querySelector("[data-character-search]");
  const characterFilterButtons = [...document.querySelectorAll("[data-character-filter]")];
  const characterPrevious = document.querySelector("[data-character-prev]");
  const characterNext = document.querySelector("[data-character-next]");
  if (characters.length && characterRail) {
    const initiallyActive = characterFilterButtons.find(
      (button) => button.getAttribute("aria-pressed") === "true",
    );
    let activeFilter = initiallyActive?.dataset.characterFilter || "all";
    let searchTerm = "";
    let railFrame = 0;

    const characterCountLabel = (count) => {
      const lastTwo = count % 100;
      const last = count % 10;
      if (last === 1 && lastTwo !== 11) return `${count} персонаж`;
      if (last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14)) return `${count} персонажа`;
      return `${count} персонажей`;
    };

    const updateRailControls = () => {
      const maxScroll = Math.max(0, characterRail.scrollWidth - characterRail.clientWidth);
      if (characterPrevious) characterPrevious.disabled = characterRail.scrollLeft <= 2;
      if (characterNext) characterNext.disabled = characterRail.scrollLeft >= maxScroll - 2;
      railFrame = 0;
    };

    const buildCharacter = (character, index) => {
      const link = document.createElement("a");
      link.className = "v5-character";
      link.href = String(character.route || "/catalog/");

      const media = document.createElement("span");
      media.className = "v5-character__media";
      media.setAttribute("data-media-frame", "");
      const image = document.createElement("img");
      image.src = String(character.hero || "");
      image.alt = String(character.name || "Персонаж");
      image.width = 480;
      image.height = 600;
      image.loading = "lazy";
      image.decoding = "async";
      image.style.objectFit = character.cover_fit === "contain" ? "contain" : "cover";
      const rawCoverX = Number(character.cover_x);
      const rawCoverY = Number(character.cover_y);
      const coverX = Number.isFinite(rawCoverX) ? Math.min(100, Math.max(0, rawCoverX)) : 50;
      const coverY = Number.isFinite(rawCoverY) ? Math.min(100, Math.max(0, rawCoverY)) : 50;
      image.style.objectPosition = `${coverX}% ${coverY}%`;
      image.setAttribute("data-media-image", "");
      media.append(createMediaPlaceholder(), image);
      bindMediaImage(image);

      const caption = document.createElement("span");
      caption.className = "v5-character__caption";
      const number = document.createElement("b");
      number.textContent = String(index + 1).padStart(2, "0");
      const copy = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = String(character.name || "Персонаж");
      const category = document.createElement("small");
      category.textContent = String(character.primary_category || "Персонаж");
      copy.append(name, category);
      caption.append(number, copy);
      link.append(media, caption);
      return link;
    };

    const renderCharacters = () => {
      const normalizedSearch = searchTerm.trim().toLocaleLowerCase("ru-RU");
      const filtered = characters.filter((character) => {
        const categories = Array.isArray(character.categories) ? character.categories : [];
        const matchesFilter = activeFilter === "all" || categories.includes(activeFilter);
        const matchesSearch = !normalizedSearch
          || String(character.name || "").toLocaleLowerCase("ru-RU").includes(normalizedSearch);
        return matchesFilter && matchesSearch;
      });

      const fragment = document.createDocumentFragment();
      filtered.forEach((character, index) => fragment.append(buildCharacter(character, index)));
      characterRail.replaceChildren(fragment);
      characterRail.classList.toggle("is-empty", filtered.length === 0);
      characterRail.scrollTo({ left: 0, behavior: "auto" });

      if (!filtered.length) {
        const empty = document.createElement("div");
        empty.className = "v5-catalog-empty";
        const heading = document.createElement("h3");
        heading.textContent = "Такого героя пока не нашли";
        const copy = document.createElement("p");
        copy.textContent = "Попробуйте другое имя или выберите соседнюю категорию.";
        empty.append(heading, copy);
        characterRail.replaceChildren(empty);
      }

      if (characterStatus) characterStatus.textContent = characterCountLabel(filtered.length);
      window.requestAnimationFrame(updateRailControls);
    };

    characterFilterButtons.forEach((button) => {
      button.addEventListener("click", () => {
        activeFilter = button.dataset.characterFilter || "all";
        characterFilterButtons.forEach((candidate) => {
          candidate.setAttribute("aria-pressed", String(candidate === button));
        });
        renderCharacters();
      });
    });

    characterSearch?.addEventListener("input", () => {
      searchTerm = characterSearch.value;
      renderCharacters();
    });

    const scrollRail = (direction) => {
      const firstCard = characterRail.querySelector(".v5-character");
      if (!firstCard) return;
      const gap = Number.parseFloat(window.getComputedStyle(characterRail).columnGap) || 0;
      const distance = firstCard.getBoundingClientRect().width + gap;
      characterRail.scrollBy({
        left: direction * distance,
        behavior: prefersReducedMotion ? "auto" : "smooth",
      });
    };

    characterPrevious?.addEventListener("click", () => scrollRail(-1));
    characterNext?.addEventListener("click", () => scrollRail(1));
    characterRail.addEventListener(
      "scroll",
      () => {
        if (!railFrame) railFrame = window.requestAnimationFrame(updateRailControls);
      },
      { passive: true },
    );
    window.addEventListener("resize", updateRailControls);

    renderCharacters();
  }

  const mobileNavigation = document.querySelector("[data-mobile-nav]");
  if (mobileNavigation) {
    const mobileNavigationLinks = [...mobileNavigation.querySelectorAll("[data-mobile-nav-link]")];
    const navigationSections = [
      { key: "home", element: document.querySelector("[data-hero]") },
      { key: "shows", element: document.querySelector("#shows") },
      { key: "characters", element: document.querySelector("#characters") },
      { key: "home", element: document.querySelector(".v5-proof, #how, #contacts, .v5-footer") },
    ].filter(({ element }) => element);
    let navigationFrame = 0;

    const setActiveNavigationItem = (key) => {
      mobileNavigationLinks.forEach((link) => {
        const isActive = link.dataset.mobileNavLink === key;
        link.classList.toggle("is-active", isActive);
        if (isActive) {
          link.setAttribute("aria-current", "location");
        } else {
          link.removeAttribute("aria-current");
        }
      });
    };

    const updateMobileNavigation = () => {
      const marker = window.scrollY + Math.min(window.innerHeight * 0.38, 320);
      let activeKey = "home";
      navigationSections.forEach(({ key, element }) => {
        const sectionTop = element.getBoundingClientRect().top + window.scrollY;
        if (sectionTop <= marker) activeKey = key;
      });
      setActiveNavigationItem(activeKey);
      navigationFrame = 0;
    };

    mobileNavigationLinks.forEach((link) => {
      link.addEventListener("click", () => setActiveNavigationItem(link.dataset.mobileNavLink || "home"));
    });
    window.addEventListener(
      "scroll",
      () => {
        if (!navigationFrame) navigationFrame = window.requestAnimationFrame(updateMobileNavigation);
      },
      { passive: true },
    );
    window.addEventListener("resize", updateMobileNavigation);
    updateMobileNavigation();

    if (window.visualViewport) {
      let viewportBaseline = window.visualViewport.height;
      const updateKeyboardState = () => {
        const activeElement = document.activeElement;
        const formControlIsFocused = activeElement instanceof HTMLElement
          && activeElement.matches("input, textarea, select, [contenteditable='true']");
        const keyboardIsOpen = formControlIsFocused
          && viewportBaseline - window.visualViewport.height > 120;
        body.classList.toggle("v5-keyboard-open", keyboardIsOpen);
        if (!formControlIsFocused) viewportBaseline = window.visualViewport.height;
      };
      window.visualViewport.addEventListener("resize", updateKeyboardState);
      document.addEventListener("focusin", updateKeyboardState);
      document.addEventListener("focusout", () => window.setTimeout(updateKeyboardState, 0));
    }
  }
})();
