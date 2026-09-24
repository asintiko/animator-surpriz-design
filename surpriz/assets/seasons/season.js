/* Season layer for the public site. core/season_theme.py injects this script
   together with the #surpriz-season JSON only while a season is on.
   - ribbon under the header (dismissible for the session);
   - badges on the cards of seasonal heroes, wherever the cards are rendered;
   - «careful» effects: a few bats and a spider over the hero banner and
     glowing pumpkins. At most six animated elements; phones get bats and
     pumpkins only. Effects respect the admin switch, prefers-reduced-motion
     and pause while the tab is hidden. */
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
  var ribbonKey = "surpriz-season-ribbon-" + season.id;
  var animations = [];

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

  /* --- ribbon -------------------------------------------------------------- */

  function mountRibbon(header) {
    try {
      if (window.sessionStorage.getItem(ribbonKey) === "closed") return;
    } catch (error) { /* storage can be blocked; the ribbon just stays */ }

    var ribbon = el("div", "season-ribbon", { role: "note" });
    var title = el("strong");
    title.textContent = (season.emoji ? season.emoji + " " : "") + season.ribbon_title;
    var text = el("span");
    text.textContent = season.ribbon_text;
    var link = el("a", "", { href: "/catalog/?character=season-" + season.id });
    link.textContent = season.catalog_label + " →";
    var close = el("button", "season-ribbon__close", { type: "button", "aria-label": "Скрыть" });
    close.textContent = "×";
    close.addEventListener("click", function () {
      ribbon.hidden = true;
      root.classList.remove("has-season-ribbon");
      try { window.sessionStorage.setItem(ribbonKey, "closed"); } catch (error) { /* ignore */ }
    });
    ribbon.append(title, text, link, close);
    header.appendChild(ribbon);
    // The page shifts down by the ribbon height, so nothing hides under it.
    function measure() {
      root.style.setProperty("--season-ribbon-h", ribbon.offsetHeight + "px");
    }
    measure();
    root.classList.add("has-season-ribbon");
    window.addEventListener("resize", measure, { passive: true });

    // The ribbon floats over the page top; it tucks away as soon as the visitor scrolls.
    var ticking = false;
    function sync() {
      ticking = false;
      ribbon.classList.toggle("is-tucked", window.scrollY > 24);
    }
    window.addEventListener("scroll", function () {
      if (!ticking) {
        ticking = true;
        window.requestAnimationFrame(sync);
      }
    }, { passive: true });
    sync();
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

  function flightPath(width, height, fromLeft, lift) {
    var startX = fromLeft ? -90 : width + 90;
    var endX = fromLeft ? width + 90 : -90;
    var y = height * lift;
    var flip = fromLeft ? 1 : -1;
    function scale(value) { return " scale(" + value * flip + "," + value + ")"; }
    return [
      { transform: "translate(" + startX + "px," + y + "px)" + scale(.7) },
      { transform: "translate(" + (startX + (endX - startX) * .3) + "px," + (y - height * .16) + "px)" + scale(.95), offset: .3 },
      { transform: "translate(" + (startX + (endX - startX) * .62) + "px," + (y + height * .06) + "px)" + scale(1), offset: .62 },
      { transform: "translate(" + endX + "px," + (y - height * .22) + "px)" + scale(.8) }
    ];
  }

  function launchBats(hero) {
    if (!sprites.bat || !sprites["bat-glide"]) return;
    var layer = el("div", "season-fx", { "aria-hidden": "true" });
    var count = mobile.matches ? 2 : 3;
    var bats = [];
    for (var index = 0; index < count; index += 1) {
      var bat = el("span", "season-bat");
      bat.append(sprite("bat"), sprite("bat-glide"));
      bat.style.opacity = "0";
      layer.appendChild(bat);
      bats.push(bat);
    }
    hero.classList.add("season-badge-host");
    hero.appendChild(layer);

    var flights = 0;
    function fly() {
      flights += 1;
      var width = layer.clientWidth;
      var height = layer.clientHeight;
      bats.forEach(function (bat, index) {
        var fromLeft = (index + flights) % 2 === 0;
        var animation = bat.animate(flightPath(width, height, fromLeft, .18 + index * .14), {
          delay: index * 900,
          duration: (mobile.matches ? 5200 : 7600) + index * 1300,
          easing: "cubic-bezier(.45, .05, .55, .95)",
          fill: "both"
        });
        bat.style.opacity = "1";
        animations.push(animation);
        animation.onfinish = function () {
          bat.style.opacity = "0";
          animations.splice(animations.indexOf(animation), 1);
        };
      });
      if (flights < 2) window.setTimeout(fly, 14000);
    }
    window.setTimeout(fly, 1200);
  }

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

  function mountPumpkins() {
    var footerBrand = document.querySelector(".surpriz-site-footer__brand");
    if (footerBrand) {
      var footerPumpkin = sprite("pumpkin", "season-pumpkin season-pumpkin--footer");
      if (footerPumpkin) {
        footerBrand.classList.add("season-badge-host");
        footerBrand.appendChild(footerPumpkin);
      }
    }
    var fab = document.querySelector(".mobile-dock__create");
    if (fab && mobile.matches) {
      var dockPumpkin = sprite("pumpkin", "season-pumpkin season-pumpkin--dock");
      if (dockPumpkin) fab.appendChild(dockPumpkin);
    }
  }

  function pauseWhenHidden() {
    document.addEventListener("visibilitychange", function () {
      animations.forEach(function (animation) {
        if (document.hidden) animation.pause();
        else animation.play();
      });
      root.classList.toggle("season-paused", document.hidden);
    });
  }

  function start() {
    var header = document.querySelector("body > .header, header.header");
    if (header && season.ribbon_title) mountRibbon(header);
    markCharacterPage();
    watchCards();
    if (!effectsOn) return;
    var hero = document.querySelector(".hero, .show-hero");
    if (hero && typeof hero.animate === "function") launchBats(hero);
    if (hero) mountSpider(hero);
    mountPumpkins();
    pauseWhenHidden();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
