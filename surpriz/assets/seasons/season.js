/* Season layer for the public site. core/season_theme.py injects this script
   together with the #surpriz-season JSON only while a season is on.
   - badges on the cards of seasonal heroes, wherever the cards are rendered;
   - «careful» effects: a spider over the hero banner and a glowing pumpkin
     in the footer; phones get the pumpkin only. Effects respect the admin
     switch, prefers-reduced-motion and pause while the tab is hidden. */
(function () {
  "use strict";

  var dataNode = document.getElementById("surpriz-season");
  if (!dataNode) return;
  var season;
  try {
    season = JSON.parse(dataNode.textContent || "{}");
  } catch (error) {
    return;
  }
  if (!season || !season.id) return;

  var root = document.documentElement;
  var sprites = season.sprites || {};
  var seasonal = new Set(season.characters || []);
  var mobile = window.matchMedia("(max-width: 767px)");
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var effectsOn = season.effects && root.getAttribute("data-season-effects") !== "off" && !reducedMotion.matches;

  function el(tag, className, attributes) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    Object.keys(attributes || {}).forEach(function (name) {
      node.setAttribute(name, attributes[name]);
    });
    return node;
  }

  function icon(className) {
    var node = el("i", className, { "aria-hidden": "true" });
    if (sprites.pumpkin) node.style.setProperty("--season-icon", "url(\"" + sprites.pumpkin + "\")");
    else node.textContent = season.emoji;
    return node;
  }

  function sprite(name, className) {
    if (!sprites[name]) return null;
    return el("img", className || "", { src: sprites[name], alt: "", "aria-hidden": "true", decoding: "async", draggable: "false" });
  }

  /* --- badges on seasonal heroes -------------------------------------------- */

  var SLUG_PATTERNS = [/\/character\/([^/?#]+)\/?/, /[?&]character=([^&#]+)/];

  function slugFromHref(href) {
    for (var index = 0; index < SLUG_PATTERNS.length; index += 1) {
      var match = SLUG_PATTERNS[index].exec(href || "");
      if (match) return decodeURIComponent(match[1]);
    }
    return "";
  }

  function badge(compact) {
    var node = el("span", "season-badge" + (compact ? " season-badge--compact" : ""), { "aria-label": season.label });
    node.append(icon("season-badge__icon"), season.label);
    return node;
  }

  function markCard(card) {
    // Only picture cards: the order box on a hero page links to the builder too.
    if (!card || card.hasAttribute("data-season-marked") || !card.querySelector("img")) return;
    card.setAttribute("data-season-marked", "");
    card.classList.add("is-season-card");
    var host = card.querySelector("[class*='media'], picture") || card;
    if (host.tagName === "PICTURE" && host.parentElement) host = host.parentElement;
    host.classList.add("season-badge-host");
    host.appendChild(badge(host.getBoundingClientRect().width < 230));
  }

  function scanCards(scope) {
    if (!seasonal.size) return;
    scope.querySelectorAll("a[href*='character']").forEach(function (link) {
      if (!seasonal.has(slugFromHref(link.getAttribute("href")))) return;
      markCard(link.closest("article, li, .sd-hero-card, [class*='card']:not([class*='__'])"));
    });
    scope.querySelectorAll("input[name='character_slugs']").forEach(function (input) {
      if (seasonal.has(input.value)) markCard(input.closest("label, article, li, [class*='card']:not([class*='__'])"));
    });
  }

  function watchCards() {
    scanCards(document);
    var pending = false;
    new MutationObserver(function () {
      if (pending) return;
      pending = true;
      window.requestAnimationFrame(function () {
        pending = false;
        scanCards(document);
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  function markCharacterPage() {
    var slug = slugFromHref(window.location.pathname);
    if (!slug || !seasonal.has(slug)) return;
    var heading = document.querySelector("main h1");
    if (!heading || heading.previousElementSibling && heading.previousElementSibling.classList.contains("season-pill")) return;
    var pill = el("span", "season-pill");
    pill.append(icon("season-pill__icon"), season.hero_label);
    heading.parentNode.insertBefore(pill, heading);
  }

  /* --- effects ---------------------------------------------------------------- */

  function mountSpider(hero) {
    if (!sprites.spider || mobile.matches) return;
    var spider = el("div", "season-spider");
    var drop = el("span", "season-spider__drop");
    var button = el("button", "", { type: "button", "aria-label": "Паучок — спрятать" });
    button.appendChild(sprite("spider"));
    drop.appendChild(button);
    spider.appendChild(drop);
    hero.appendChild(spider);

    function hide() {
      spider.classList.remove("is-down");
      spider.classList.add("is-up");
      window.setTimeout(function () {
        spider.classList.remove("is-up");
        spider.classList.add("is-down");
      }, 9000);
    }
    button.addEventListener("click", hide);
    spider.addEventListener("mouseenter", hide);
    window.setTimeout(function () { spider.classList.add("is-down"); }, 2600);
  }

  function mountPumpkin() {
    var footerBrand = document.querySelector(".surpriz-site-footer__brand");
    if (footerBrand) {
      var footerPumpkin = sprite("pumpkin", "season-pumpkin season-pumpkin--footer");
      if (footerPumpkin) {
        footerBrand.classList.add("season-badge-host");
        footerBrand.appendChild(footerPumpkin);
      }
    }
  }

  function pauseWhenHidden() {
    document.addEventListener("visibilitychange", function () {
      root.classList.toggle("season-paused", document.hidden);
    });
  }

  function start() {
    markCharacterPage();
    watchCards();
    if (!effectsOn) return;
    var hero = document.querySelector(".hero, .show-hero");
    if (hero) mountSpider(hero);
    mountPumpkin();
    pauseWhenHidden();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
