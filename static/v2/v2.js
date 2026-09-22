/* Surpriz v2 — vanilla JS. Всё опционально и безопасно при отсутствии элементов. */
(function () {
  "use strict";

  var REDUCED = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  /* ---------- Шапка: состояние при скролле ---------- */
  function initHeaderScroll() {
    var header = document.querySelector("[data-v2-header]");
    if (!header) return;
    var onScroll = function () {
      header.classList.toggle("v2-header--scrolled", window.scrollY > 8);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
  }

  /* ---------- Бургер и мобильное меню ---------- */
  function initMobileMenu() {
    var burger = document.querySelector("[data-v2-burger]");
    var menu = document.querySelector("[data-v2-mmenu]");
    if (!burger || !menu) return;

    var open = function () {
      menu.classList.add("is-open");
      burger.classList.add("is-active");
      burger.setAttribute("aria-expanded", "true");
      burger.setAttribute("aria-label", "Закрыть меню");
      menu.setAttribute("aria-hidden", "false");
      menu.removeAttribute("inert");
      document.body.style.overflow = "hidden";
      var firstLink = menu.querySelector("a[href], button:not([disabled])");
      if (firstLink) firstLink.focus();
    };
    var close = function (restoreFocus) {
      menu.classList.remove("is-open");
      burger.classList.remove("is-active");
      burger.setAttribute("aria-expanded", "false");
      burger.setAttribute("aria-label", "Открыть меню");
      menu.setAttribute("aria-hidden", "true");
      menu.setAttribute("inert", "");
      document.body.style.overflow = "";
      if (restoreFocus) burger.focus();
    };
    var toggle = function () {
      if (menu.classList.contains("is-open")) { close(true); } else { open(); }
    };

    burger.addEventListener("click", toggle);
    document.addEventListener("keydown", function (event) {
      if (!menu.classList.contains("is-open")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        close(true);
        return;
      }
      if (event.key !== "Tab") return;
      var focusable = [burger].concat(Array.prototype.slice.call(menu.querySelectorAll(
        "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
      )));
      if (!focusable.length) return;
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
    menu.addEventListener("click", function (event) {
      var link = event.target.closest ? event.target.closest("a") : null;
      if (link) close(false);
    });
    window.__v2CloseMenu = close;
  }

  /* ---------- Reveal-анимации ---------- */
  function initReveal() {
    var items = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));
    if (!items.length) return;
    items.forEach(function (el) {
      var delay = parseFloat(el.getAttribute("data-reveal-delay") || "0");
      if (delay > 0) el.style.transitionDelay = delay + "ms";
    });
    if (REDUCED || !("IntersectionObserver" in window)) {
      items.forEach(function (el) { el.classList.add("is-in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-in");
          /* Чистим инлайновую задержку после появления, чтобы hover-эффекты
             (lift, scale) не срабатывали с запозданием. */
          var el = entry.target;
          var delay = parseFloat(el.getAttribute("data-reveal-delay") || "0");
          window.setTimeout(function () { el.style.transitionDelay = ""; }, 750 + delay);
          io.unobserve(el);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    items.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Счётчики [data-count] ---------- */
  function formatNumber(n) {
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  function initCounters() {
    var counters = Array.prototype.slice.call(document.querySelectorAll("[data-count]"));
    if (!counters.length) return;
    var animate = function (el) {
      var target = parseFloat(el.getAttribute("data-count") || "0");
      var suffix = el.getAttribute("data-count-suffix") || "";
      var duration = parseFloat(el.getAttribute("data-count-duration") || "1200");
      if (REDUCED || duration <= 0) {
        el.textContent = formatNumber(target) + suffix;
        return;
      }
      var start = null;
      var step = function (ts) {
        if (!start) start = ts;
        var p = Math.min(1, (ts - start) / duration);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = formatNumber(target * eased) + suffix;
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };
    if (!("IntersectionObserver" in window)) {
      counters.forEach(animate);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          animate(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.4 });
    counters.forEach(function (el) { io.observe(el); });
  }

  /* ---------- Аккордеон [data-accordion] ---------- */
  function initAccordions() {
    var roots = Array.prototype.slice.call(document.querySelectorAll("[data-accordion]"));
    roots.forEach(function (root) {
      var items = Array.prototype.slice.call(root.querySelectorAll("[data-accordion-item]"));
      var setPanel = function (item, open, animate) {
        var panel = item.querySelector("[data-accordion-panel]");
        var btn = item.querySelector("[data-accordion-btn]");
        item.classList.toggle("is-open", open);
        if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (!panel) return;
        window.clearTimeout(panel.__accordionHideTimer);
        panel.setAttribute("aria-hidden", open ? "false" : "true");
        if (open) {
          panel.hidden = false;
          if (animate) {
            panel.style.maxHeight = "0px";
            window.requestAnimationFrame(function () {
              if (item.classList.contains("is-open")) panel.style.maxHeight = panel.scrollHeight + "px";
            });
          } else {
            panel.style.maxHeight = panel.scrollHeight + "px";
          }
        } else {
          panel.style.maxHeight = "0px";
          if (animate) {
            panel.__accordionHideTimer = window.setTimeout(function () {
              if (!item.classList.contains("is-open")) panel.hidden = true;
            }, 400);
          } else {
            panel.hidden = true;
          }
        }
      };
      items.forEach(function (item) {
        var btn = item.querySelector("[data-accordion-btn]");
        if (!btn) return;
        setPanel(item, item.classList.contains("is-open"), false);
        btn.addEventListener("click", function () {
          var willOpen = !item.classList.contains("is-open");
          items.forEach(function (other) {
            if (other !== item && other.classList.contains("is-open")) setPanel(other, false, true);
          });
          setPanel(item, willOpen, true);
        });
      });
    });
  }

  /* ---------- Конфетти-канвас <canvas data-confetti> ---------- */
  function initConfetti() {
    var canvases = Array.prototype.slice.call(document.querySelectorAll("canvas[data-confetti]"));
    if (!canvases.length) return;

    var COLORS = ["#FFC53D", "#FF8A3D", "#FF6B6B", "#18B8C9", "#8B5CF6", "#BEEFF4"];
    var SHAPES = ["circle", "triangle", "star"];

    canvases.forEach(function (canvas) {
      var ctx = canvas.getContext("2d");
      if (!ctx) return;
      var pieces = [];
      var w = 0;
      var h = 0;
      var dpr = Math.min(2, window.devicePixelRatio || 1);
      var visible = true;
      var rafId = null;

      var rand = function (min, max) { return min + Math.random() * (max - min); };

      var resize = function () {
        var rect = canvas.getBoundingClientRect();
        w = Math.max(1, rect.width);
        h = Math.max(1, rect.height);
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      };

      var spawn = function (initial) {
        return {
          x: rand(0, w),
          y: initial ? rand(-h, 0) : rand(-40, -8),
          size: rand(3.5, 7),
          speed: rand(0.18, 0.5),
          swayAmp: rand(0.25, 0.7),
          swaySpeed: rand(0.006, 0.014),
          phase: rand(0, Math.PI * 2),
          rot: rand(0, Math.PI * 2),
          rotSpeed: rand(-0.012, 0.012),
          color: COLORS[(Math.random() * COLORS.length) | 0],
          shape: SHAPES[(Math.random() * SHAPES.length) | 0],
          alpha: rand(0.45, 0.7)
        };
      };

      var drawStar = function (cx, cy, r) {
        ctx.beginPath();
        for (var i = 0; i < 8; i++) {
          var radius = i % 2 === 0 ? r : r * 0.42;
          var angle = (Math.PI / 4) * i - Math.PI / 2;
          var px = cx + Math.cos(angle) * radius;
          var py = cy + Math.sin(angle) * radius;
          if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.fill();
      };

      var draw = function (p) {
        ctx.save();
        ctx.globalAlpha = p.alpha;
        ctx.fillStyle = p.color;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        if (p.shape === "circle") {
          ctx.beginPath();
          ctx.arc(0, 0, p.size / 2, 0, Math.PI * 2);
          ctx.fill();
        } else if (p.shape === "triangle") {
          ctx.beginPath();
          ctx.moveTo(0, -p.size / 2);
          ctx.lineTo(p.size / 2, p.size / 2);
          ctx.lineTo(-p.size / 2, p.size / 2);
          ctx.closePath();
          ctx.fill();
        } else {
          drawStar(0, 0, p.size * 0.8);
        }
        ctx.restore();
      };

      var tick = function (ts) {
        ctx.clearRect(0, 0, w, h);
        for (var i = 0; i < pieces.length; i++) {
          var p = pieces[i];
          p.y += p.speed;
          p.x += Math.sin(ts * p.swaySpeed + p.phase) * p.swayAmp * 0.3;
          p.rot += p.rotSpeed;
          if (p.y > h + 16) pieces[i] = p = spawn(false);
          draw(p);
        }
        rafId = requestAnimationFrame(tick);
      };

      var start = function () {
        if (rafId === null && visible && !document.hidden) rafId = requestAnimationFrame(tick);
      };
      var stop = function () {
        if (rafId !== null) { cancelAnimationFrame(rafId); rafId = null; }
      };

      resize();
      var count = Math.max(14, Math.min(25, Math.round(w / 56)));
      for (var i = 0; i < count; i++) pieces.push(spawn(true));

      if (REDUCED) {
        /* Статичный кадр без анимации */
        ctx.clearRect(0, 0, w, h);
        pieces.forEach(function (p) { p.y = rand(0, h); draw(p); });
        return;
      }

      window.addEventListener("resize", function () { resize(); }, { passive: true });
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) stop(); else start();
      });
      if ("IntersectionObserver" in window) {
        new IntersectionObserver(function (entries) {
          visible = entries[0] ? entries[0].isIntersecting : true;
          if (visible) start(); else stop();
        }, { threshold: 0.02 }).observe(canvas);
      }
      start();
    });
  }

  /* ---------- Подсказки акций [data-promo-hint] ---------- */
  function initPromoHints() {
    var roots = Array.prototype.slice.call(document.querySelectorAll("[data-promo-hint]"));
    if (!roots.length) return;
    var HOVERABLE = window.matchMedia && window.matchMedia("(hover: hover)").matches;

    function setOpen(root, open) {
      var trigger = root.querySelector("[data-promo-hint-trigger]");
      var popover = root.querySelector("[data-promo-hint-popover]");
      if (!trigger || !popover) return;
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
      popover.hidden = !open;
    }

    function closeAll(except) {
      roots.forEach(function (root) {
        if (root !== except) {
          root.__promoPinned = false;
          setOpen(root, false);
        }
      });
    }

    document.addEventListener("click", function (event) {
      var trigger = event.target.closest ? event.target.closest("[data-promo-hint-trigger]") : null;
      if (trigger) {
        var root = trigger.closest("[data-promo-hint]");
        if (!root) return;
        /* Клик «пинит» подсказку: повторный клик по тому же триггеру закрывает,
           клик после hover-открытия — закрепляет, а не скрывает. */
        var willPin = !root.__promoPinned;
        closeAll(root);
        root.__promoPinned = willPin;
        setOpen(root, willPin);
        return;
      }
      if (!(event.target.closest && event.target.closest("[data-promo-hint]"))) closeAll(null);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") closeAll(null);
    });

    if (HOVERABLE) {
      roots.forEach(function (root) {
        root.addEventListener("mouseenter", function () {
          if (!root.__promoPinned) setOpen(root, true);
        });
        root.addEventListener("mouseleave", function () {
          if (!root.__promoPinned) setOpen(root, false);
        });
      });
    }
  }

  /* ---------- Плавный скролл к якорям ---------- */
  function initSmoothScroll() {
    document.addEventListener("click", function (event) {
      var link = event.target.closest ? event.target.closest('a[href^="#"]') : null;
      if (!link) return;
      var hash = link.getAttribute("href");
      if (!hash || hash === "#") return;
      var target = document.getElementById(hash.slice(1));
      if (!target) return;
      event.preventDefault();
      if (window.__v2CloseMenu) window.__v2CloseMenu();
      target.scrollIntoView({ behavior: REDUCED ? "auto" : "smooth", block: "start" });
      if (history.replaceState) history.replaceState(null, "", hash);
    });
  }

  /* ---------- Бесшовная бегущая строка ---------- */
  function initMarquee() {
    var tracks = Array.prototype.slice.call(document.querySelectorAll(".v2-marquee__track"));
    tracks.forEach(function (track) {
      if (track.getAttribute("data-marquee-ready") === "1") return;
      var sourceItems = Array.prototype.slice.call(track.children);
      var cloneGroup = document.createElement("span");
      cloneGroup.setAttribute("aria-hidden", "true");
      cloneGroup.setAttribute("inert", "");
      cloneGroup.style.display = "contents";
      sourceItems.forEach(function (item) { cloneGroup.appendChild(item.cloneNode(true)); });
      Array.prototype.forEach.call(cloneGroup.querySelectorAll("a, button, input, select, textarea, [tabindex]"), function (element) {
        element.setAttribute("tabindex", "-1");
      });
      track.appendChild(cloneGroup);
      track.setAttribute("data-marquee-ready", "1");
    });
  }

  ready(function () {
    initHeaderScroll();
    initMobileMenu();
    initReveal();
    initCounters();
    initAccordions();
    initSmoothScroll();
    initPromoHints();
    initMarquee();
  });
})();
