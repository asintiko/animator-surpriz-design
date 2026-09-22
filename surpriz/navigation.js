(() => {
  "use strict";

  const revealPage = () => {
    window.requestAnimationFrame(() => {
      document.body?.classList.add("site-page-ready");
    });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", revealPage, { once: true });
  } else {
    revealPage();
  }
})();

(() => {
  "use strict";

  const menu = document.querySelector("[data-character-menu]");
  if (!menu) return;

  const toggle = menu.querySelector("[data-character-menu-toggle]");
  const panel = menu.querySelector("[data-character-menu-panel]");
  const links = [...panel.querySelectorAll("a[href]")];
  const filterLinks = [...panel.querySelectorAll("[data-character-filter]")];
  const hoverMode = window.matchMedia("(hover: hover) and (pointer: fine)");
  let closeTimer = 0;
  let pointerToggleFocus = false;

  const isOpen = () => toggle.getAttribute("aria-expanded") === "true";

  const open = () => {
    window.clearTimeout(closeTimer);
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    menu.classList.add("is-open");
  };

  const close = ({ returnFocus = false } = {}) => {
    window.clearTimeout(closeTimer);
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    menu.classList.remove("is-open");
    if (returnFocus) toggle.focus({ preventScroll: true });
  };

  const scheduleClose = () => {
    window.clearTimeout(closeTimer);
    closeTimer = window.setTimeout(() => {
      if (!menu.matches(":hover") && !menu.matches(":focus-within")) close();
    }, 140);
  };

  const focusLink = (index) => {
    if (!links.length) return;
    const normalized = (index + links.length) % links.length;
    links[normalized].focus({ preventScroll: true });
  };

  toggle.addEventListener("pointerdown", () => {
    pointerToggleFocus = true;
  });

  toggle.addEventListener("click", () => {
    if (isOpen()) close();
    else open();
    pointerToggleFocus = false;
  });

  toggle.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    open();
    focusLink(0);
  });

  panel.addEventListener("keydown", (event) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const currentIndex = links.indexOf(document.activeElement);
    if (event.key === "Home") return focusLink(0);
    if (event.key === "End") return focusLink(links.length - 1);
    focusLink(currentIndex + (event.key === "ArrowDown" ? 1 : -1));
  });

  menu.addEventListener("pointerenter", () => {
    if (hoverMode.matches) open();
  });
  menu.addEventListener("pointerleave", () => {
    if (hoverMode.matches) scheduleClose();
  });
  menu.addEventListener("focusin", (event) => {
    if (event.target !== toggle || !pointerToggleFocus) open();
  });
  menu.addEventListener("focusout", scheduleClose);

  document.addEventListener("pointerdown", (event) => {
    if (isOpen() && !menu.contains(event.target)) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && isOpen()) close({ returnFocus: true });
  });

  links.forEach((link) => link.addEventListener("click", () => close()));

  const selectedCategory = new URLSearchParams(window.location.search).get("character");
  filterLinks.forEach((link) => {
    if (link.dataset.characterFilter === selectedCategory) link.setAttribute("aria-current", "page");
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth <= 767) close();
  }, { passive: true });
  window.addEventListener("pagehide", () => window.clearTimeout(closeTimer), { once: true });
})();
