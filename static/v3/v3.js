(function () {
  "use strict";

  var section = document.getElementById("cinematic");
  var stage = document.getElementById("stage");
  if (!section || !stage) return;

  var world = document.getElementById("world");
  var tint = document.getElementById("tint");
  var copyIntro = document.getElementById("copyIntro");
  var atelierArt = document.getElementById("atelierArt");
  var boxPoster = document.getElementById("boxPoster");
  var boxSequence = document.getElementById("boxSequence");
  var atelierPlatform = document.getElementById("atelierPlatform");
  var loader = document.getElementById("loader");
  var chooseShows = document.getElementById("chooseShows");
  var railWrap = document.getElementById("railWrap");
  var rail = document.getElementById("rail");
  var railTrack = document.getElementById("railTrack");
  var railTitle = document.getElementById("railTitle");
  var railPrev = document.getElementById("railPrev");
  var railNext = document.getElementById("railNext");
  var railStatus = document.getElementById("railStatus");
  var wings = Array.prototype.slice.call(document.querySelectorAll(".atelier-wing"));
  var cards = railTrack ? Array.prototype.slice.call(railTrack.querySelectorAll(".rail-card")) : [];
  var railImages = railTrack ? Array.prototype.slice.call(railTrack.querySelectorAll("img[data-src]")) : [];

  var motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  var shortViewportQuery = window.matchMedia("(max-height: 300px)");
  var coarseQuery = window.matchMedia("(pointer: coarse)");
  var connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
  var reducedMotion = motionQuery.matches || shortViewportQuery.matches;
  var lowPower = false;
  var nativeRail = false;
  var metrics = { start: 0, travel: 1, width: window.innerWidth, height: stage.getBoundingClientRect().height || window.innerHeight };
  var targetProgress = 0;
  var visualProgress = 0;
  var frameId = 0;
  var resizeFrame = 0;
  var lastFrameTime = 0;
  var lastScrollTime = 0;
  var progressVelocity = 0;
  var lastMeasuredWidth = window.innerWidth;
  var lastMeasuredHeight = metrics.height;
  var inView = true;
  var ready = false;
  var entrancePlayed = false;
  var entranceTimer = 0;
  var entranceDelayTimer = 0;
  var entranceFrame = 0;
  var entranceStartedAt = 0;
  var entranceCancelled = false;
  var sequenceImage = null;
  var sequenceContext = null;
  var sequenceCellSize = 0;
  var sequenceLoadId = 0;
  var sequenceColumns = boxSequence ? parseInt(boxSequence.getAttribute("data-sequence-columns"), 10) || 4 : 4;
  var sequenceRows = boxSequence ? parseInt(boxSequence.getAttribute("data-sequence-rows"), 10) || 3 : 3;
  var sequenceFrameCount = boxSequence ? parseInt(boxSequence.getAttribute("data-sequence-frames"), 10) || 11 : 11;
  var sequenceFrameDuration = boxSequence ? parseInt(boxSequence.getAttribute("data-sequence-frame-ms"), 10) || 84 : 84;
  var railHydrated = false;
  var railStep = 1;
  var railMaxOffset = 0;
  var railMaxIndex = 0;
  var railVisibleCount = 1;
  var railIndex = 0;
  var railOffset = 0;
  var railInteractive = null;
  var introInteractive = null;
  var dragging = false;
  var dragStartX = 0;
  var dragStartOffset = 0;
  var dragged = false;
  var railScrollFrame = 0;
  var railLiveTimer = 0;
  var railScrollAnnounceTimer = 0;
  var catalogFocusPending = false;

  var TIMELINE = Object.freeze({
    introExit: [0.04, 0.18],
    artMove: [0.09, 0.3],
    catalog: { hydrateAt: 0.06, enter: [0.24, 0.38], title: [0.27, 0.35], interactiveAt: 0.36 }
  });

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function lerp(from, to, amount) {
    return from + (to - from) * amount;
  }

  function smoothstep(from, to, value) {
    var progress = clamp((value - from) / Math.max(to - from, 0.0001), 0, 1);
    return progress * progress * (3 - 2 * progress);
  }

  function rangeProgress(value, range) {
    return smoothstep(range[0], range[1], value);
  }

  function setStyle(element, property, value) {
    if (element && element.style.getPropertyValue(property) !== value) {
      element.style.setProperty(property, value);
    }
  }

  function setNumber(element, property, value) {
    setStyle(element, property, value.toFixed(4));
  }

  function setPixels(element, property, value) {
    setStyle(element, property, value.toFixed(2) + "px");
  }

  function setVisible(element, visible) {
    if (!element) return;
    var value = visible ? "false" : "true";
    if (element.getAttribute("aria-hidden") !== value) element.setAttribute("aria-hidden", value);
  }

  function now() {
    return window.performance && window.performance.now ? window.performance.now() : Date.now();
  }

  function detectLowPower() {
    var limitedCores = navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4;
    var limitedMemory = navigator.deviceMemory && navigator.deviceMemory <= 4;
    var saveData = connection && connection.saveData;
    return coarseQuery.matches || window.innerWidth < 769 || limitedCores || limitedMemory || saveData;
  }

  function syncEnvironment() {
    reducedMotion = motionQuery.matches || shortViewportQuery.matches;
    lowPower = detectLowPower();
    nativeRail = coarseQuery.matches || window.innerWidth <= 768;
    document.documentElement.classList.toggle("is-low-power", lowPower);
    document.documentElement.classList.toggle("is-reduced", reducedMotion);
    document.documentElement.classList.toggle("is-native-rail", nativeRail || reducedMotion);
  }

  function setRailInteractive(interactive) {
    if (!railWrap || railInteractive === interactive) return;
    railInteractive = interactive;
    railWrap.classList.toggle("is-live", interactive);
    railWrap.setAttribute("aria-hidden", interactive ? "false" : "true");
    if (interactive) railWrap.removeAttribute("inert");
    else railWrap.setAttribute("inert", "");
  }

  function setIntroInteractive(interactive) {
    if (!copyIntro || introInteractive === interactive) return;
    introInteractive = interactive;
    if (interactive) copyIntro.removeAttribute("inert");
    else copyIntro.setAttribute("inert", "");
  }

  function loadRailImage(image) {
    if (!image) return;
    var source = image.getAttribute("data-src");
    if (!source) return;
    image.loading = "eager";
    image.src = source;
    image.removeAttribute("data-src");
  }

  function hydrateRailAround(index) {
    var lastIndex = Math.min(cards.length - 1, Math.max(0, index) + 1);
    cards.slice(0, lastIndex + 1).forEach(function (card) {
      loadRailImage(card.querySelector("img[data-src]"));
    });
  }

  function hydrateRailImages() {
    if (nativeRail) {
      hydrateRailAround(railIndex);
      return;
    }
    if (railHydrated) return;
    railHydrated = true;
    railImages.forEach(loadRailImage);
  }

  function measure() {
    var rect = section.getBoundingClientRect();
    var stageHeight = stage.getBoundingClientRect().height || window.innerHeight;
    metrics.start = window.scrollY + rect.top;
    metrics.height = stageHeight;
    metrics.width = window.innerWidth;
    metrics.travel = Math.max(section.offsetHeight - stageHeight, 1);
    measureRail();
    updateTarget();
  }

  function updateTarget() {
    if (reducedMotion) return;
    var nextProgress = clamp((window.scrollY - metrics.start) / metrics.travel, 0, 1);
    var timestamp = now();
    var elapsed = lastScrollTime ? Math.max(timestamp - lastScrollTime, 1) : 16.67;
    progressVelocity = Math.abs(nextProgress - targetProgress) / elapsed;
    targetProgress = nextProgress;
    lastScrollTime = timestamp;
    if (targetProgress > 0.02) cancelEntrance();
    requestFrame();
  }

  function render(progress) {
    var introExit = rangeProgress(progress, TIMELINE.introExit);
    var artMove = rangeProgress(progress, TIMELINE.artMove);
    var catalog = rangeProgress(progress, TIMELINE.catalog.enter);
    var titleProgress = rangeProgress(progress, TIMELINE.catalog.title);
    var wingTravel = metrics.width * artMove * 0.08;

    setPixels(world, "--world-y", -artMove * 8 + catalog * 4);
    setNumber(world, "--world-o", 1);

    setPixels(atelierArt, "--art-x", metrics.width <= 768 ? 0 : artMove * 10);
    setPixels(atelierArt, "--art-y", artMove * 20 + catalog * 10);
    setNumber(atelierArt, "--art-s", 1 - artMove * (metrics.width <= 768 ? 0.018 : 0.035));
    setNumber(atelierArt, "--art-o", 1 - catalog * 0.96);

    setPixels(atelierPlatform, "--platform-y", -artMove * 5);
    setNumber(atelierPlatform, "--platform-o", 1 - catalog * 0.45);

    wings.forEach(function (wing, index) {
      setPixels(wing, "--wing-x", index === 0 ? -wingTravel : wingTravel);
      setNumber(wing, "--wing-o", 1 - catalog);
    });

    setNumber(tint, "--o", catalog * 0.18);

    setNumber(copyIntro, "--o", 1 - introExit);
    setPixels(copyIntro, "--ty", -introExit * (metrics.width <= 768 ? 10 : 14));
    setVisible(copyIntro, introExit < 0.96);
    setIntroInteractive(introExit < 0.96);

    setNumber(railWrap, "--o", catalog);
    setPixels(railWrap, "--ty", (1 - catalog) * (metrics.width <= 768 ? 12 : 20));
    setNumber(railTitle, "--o", titleProgress);
    setPixels(railTitle, "--ty", (1 - titleProgress) * 10);
    var catalogInteractive = progress >= TIMELINE.catalog.interactiveAt;
    setRailInteractive(catalogInteractive);
    if (catalogInteractive && catalogFocusPending && rail) {
      catalogFocusPending = false;
      window.requestAnimationFrame(function () { rail.focus({ preventScroll: true }); });
    }

    if (progress >= TIMELINE.catalog.hydrateAt) hydrateRailImages();
  }

  function renderReduced() {
    setNumber(copyIntro, "--o", 1);
    setPixels(copyIntro, "--ty", 0);
    setVisible(copyIntro, true);
    setIntroInteractive(true);
    setNumber(atelierArt, "--art-o", 1);
    setPixels(atelierArt, "--art-y", 0);
    setNumber(atelierArt, "--art-s", 1);
    setNumber(atelierPlatform, "--platform-o", 1);
    setPixels(atelierPlatform, "--platform-y", 0);
    setNumber(railWrap, "--o", 1);
    setPixels(railWrap, "--ty", 0);
    setNumber(railTitle, "--o", 1);
    setPixels(railTitle, "--ty", 0);
    setRailInteractive(true);
    hydrateRailImages();
  }

  function frame(timestamp) {
    frameId = 0;
    if (!ready) return;

    if (reducedMotion) {
      renderReduced();
      return;
    }

    var rawDelta = lastFrameTime ? timestamp - lastFrameTime : 16.67;
    var delta = Math.min(Math.max(rawDelta, 1), 50);
    var gap = Math.abs(targetProgress - visualProgress);
    var activeVelocity = timestamp - lastScrollTime < 90 ? progressVelocity : 0;
    lastFrameTime = timestamp;

    if (lowPower || rawDelta > 64 || gap >= 0.1 || activeVelocity >= 0.002) {
      visualProgress = targetProgress;
    } else {
      var tau = gap >= 0.03 || activeVelocity >= 0.0006 ? 32 : 72;
      var alpha = 1 - Math.exp(-delta / tau);
      visualProgress = lerp(visualProgress, targetProgress, alpha);
    }

    if (inView) render(visualProgress);

    if (Math.abs(visualProgress - targetProgress) > 0.00015 && inView) {
      requestFrame();
    } else {
      visualProgress = targetProgress;
      if (inView) render(visualProgress);
      lastFrameTime = 0;
    }
  }

  function requestFrame() {
    if (!frameId) frameId = window.requestAnimationFrame(frame);
  }

  function measureRail() {
    if (!rail || !railTrack || !cards.length) return;
    var firstRect = cards[0].getBoundingClientRect();
    railStep = firstRect.width + 16;
    if (cards.length > 1 && cards[1].offsetLeft > cards[0].offsetLeft) {
      railStep = cards[1].offsetLeft - cards[0].offsetLeft;
    }

    railMaxOffset = Math.max(0, (nativeRail ? rail.scrollWidth : railTrack.scrollWidth) - rail.clientWidth);
    if (nativeRail) {
      railMaxIndex = Math.max(0, Math.ceil((railMaxOffset - 1) / Math.max(railStep, 1)));
      railVisibleCount = Math.max(1, cards.length - railMaxIndex);
    } else {
      railVisibleCount = Math.max(1, Math.min(cards.length, Math.floor((rail.clientWidth + 16) / Math.max(railStep, 1))));
      railMaxIndex = Math.max(0, cards.length - railVisibleCount);
    }
    railIndex = clamp(railIndex, 0, railMaxIndex);
    setRailOffset(Math.min(railIndex * railStep, railMaxOffset), false);
    updateRailStatus(false);
  }

  function updateRailStatus(announce) {
    if (!railStatus) return;
    if (!cards.length) {
      railStatus.textContent = "";
      return;
    }

    var first = Math.min(railIndex + 1, cards.length);
    var last = Math.min(first + railVisibleCount - 1, cards.length);
    var label = first === last ? String(first) : first + "–" + last;
    var statusText = "Шоу " + label + " из " + cards.length;

    if (announce) {
      window.clearTimeout(railLiveTimer);
      railStatus.setAttribute("aria-live", "polite");
      if (railStatus.textContent === statusText) railStatus.textContent = "";
      window.requestAnimationFrame(function () {
        if (railStatus) railStatus.textContent = statusText;
      });
      railLiveTimer = window.setTimeout(function () {
        if (railStatus) railStatus.setAttribute("aria-live", "off");
      }, 700);
    } else {
      railStatus.setAttribute("aria-live", "off");
      railStatus.textContent = statusText;
    }

    if (railPrev) railPrev.disabled = railIndex <= 0;
    if (railNext) railNext.disabled = railIndex >= railMaxIndex;
  }

  function setRailOffset(offset, smooth) {
    railOffset = clamp(offset, 0, railMaxOffset);
    if (nativeRail || reducedMotion) {
      if (rail && Math.abs(rail.scrollLeft - railOffset) > 1) {
        rail.scrollTo({ left: railOffset, behavior: smooth && !reducedMotion ? "smooth" : "auto" });
      }
    } else if (railTrack) {
      railTrack.classList.toggle("is-smooth", Boolean(smooth));
      setStyle(railTrack, "--rail-x", (-railOffset).toFixed(2));
    }
  }

  function setRailIndex(index, announce) {
    railIndex = clamp(Math.round(index), 0, railMaxIndex);
    hydrateRailAround(railIndex);
    setRailOffset(Math.min(railIndex * railStep, railMaxOffset), announce !== false);
    updateRailStatus(announce !== false);
  }

  function finishDrag(pointerId) {
    if (!dragging) return;
    dragging = false;
    rail.classList.remove("is-dragging");
    if (rail.hasPointerCapture && rail.hasPointerCapture(pointerId)) rail.releasePointerCapture(pointerId);
    setRailIndex(Math.round(railOffset / Math.max(railStep, 1)), true);
  }

  function bindRail() {
    if (!rail || !railTrack || !cards.length) return;

    if (railPrev) railPrev.addEventListener("click", function () { setRailIndex(railIndex - 1, true); });
    if (railNext) railNext.addEventListener("click", function () { setRailIndex(railIndex + 1, true); });

    rail.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        setRailIndex(railIndex - 1, true);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        setRailIndex(railIndex + 1, true);
      } else if (event.key === "Home") {
        event.preventDefault();
        setRailIndex(0, true);
      } else if (event.key === "End") {
        event.preventDefault();
        setRailIndex(railMaxIndex, true);
      }
    });

    rail.addEventListener("focusin", function (event) {
      if (nativeRail) return;
      var card = event.target.closest ? event.target.closest(".rail-card") : null;
      var cardIndex = card ? cards.indexOf(card) : -1;
      if (cardIndex < 0) return;
      if (cardIndex < railIndex) setRailIndex(cardIndex, false);
      else if (cardIndex >= railIndex + railVisibleCount) {
        setRailIndex(cardIndex - railVisibleCount + 1, false);
      }
      if (rail.scrollLeft) rail.scrollLeft = 0;
      window.requestAnimationFrame(function () { if (rail) rail.scrollLeft = 0; });
    });

    rail.addEventListener("pointerdown", function (event) {
      if (event.button !== 0 || reducedMotion || nativeRail) return;
      dragging = true;
      dragged = false;
      dragStartX = event.clientX;
      dragStartOffset = railOffset;
      rail.classList.add("is-dragging");
      rail.setPointerCapture(event.pointerId);
    });

    rail.addEventListener("pointermove", function (event) {
      if (!dragging || nativeRail) return;
      var delta = event.clientX - dragStartX;
      if (Math.abs(delta) > 5) dragged = true;
      setRailOffset(dragStartOffset - delta, false);
    });

    rail.addEventListener("pointerup", function (event) { finishDrag(event.pointerId); });
    rail.addEventListener("pointercancel", function (event) { finishDrag(event.pointerId); });
    rail.addEventListener("click", function (event) {
      if (!dragged) return;
      event.preventDefault();
      event.stopPropagation();
      dragged = false;
    }, true);

    rail.addEventListener("scroll", function () {
      if (!nativeRail || railScrollFrame) return;
      railScrollFrame = window.requestAnimationFrame(function () {
        railScrollFrame = 0;
        railOffset = rail.scrollLeft;
        var nextIndex = clamp(Math.round(railOffset / Math.max(railStep, 1)), 0, railMaxIndex);
        if (nextIndex !== railIndex) {
          railIndex = nextIndex;
          hydrateRailAround(railIndex);
          updateRailStatus(false);
        }
        window.clearTimeout(railScrollAnnounceTimer);
        railScrollAnnounceTimer = window.setTimeout(function () { updateRailStatus(true); }, 180);
      });
    }, { passive: true });
  }

  function bindCatalogJump() {
    if (!chooseShows) return;
    chooseShows.addEventListener("click", function (event) {
      event.preventDefault();
      if (reducedMotion) {
        if (railWrap) railWrap.scrollIntoView({ behavior: "auto", block: "start" });
        if (rail) rail.focus({ preventScroll: true });
        return;
      }
      var destination = metrics.start + metrics.travel * (TIMELINE.catalog.interactiveAt + 0.015);
      if (event.detail === 0) {
        window.scrollTo({ top: destination, behavior: "auto" });
        targetProgress = TIMELINE.catalog.interactiveAt + 0.015;
        visualProgress = targetProgress;
        render(visualProgress);
        if (rail) rail.focus({ preventScroll: true });
        return;
      }
      catalogFocusPending = true;
      window.scrollTo({ top: destination, behavior: "smooth" });
    });
  }

  function waitForImage(image) {
    if (!image) return Promise.resolve(false);

    function decodeCurrentSource() {
      var source = image.currentSrc || image.src;
      if (!image.complete || image.naturalWidth <= 0) return Promise.resolve(false);
      if (!image.decode) return Promise.resolve(true);
      return image.decode().then(function () {
        if ((image.currentSrc || image.src) !== source) return waitForImage(image);
        return image.complete && image.naturalWidth > 0;
      }, function () {
        if ((image.currentSrc || image.src) !== source || !image.complete) return waitForImage(image);
        return image.naturalWidth > 0;
      });
    }

    if (image.complete) return decodeCurrentSource();
    return new Promise(function (resolve) {
      image.addEventListener("load", function () { resolve(decodeCurrentSource()); }, { once: true });
      image.addEventListener("error", function () { resolve(false); }, { once: true });
    });
  }

  var SEQUENCE_TIMES = [];
  for (var sequenceIndex = 0; sequenceIndex < sequenceFrameCount; sequenceIndex += 1) {
    SEQUENCE_TIMES.push(sequenceIndex * sequenceFrameDuration);
  }
  var SEQUENCE_DURATION = SEQUENCE_TIMES[SEQUENCE_TIMES.length - 1] + Math.max(120, sequenceFrameDuration * 2);
  var ENTRANCE_DELAY = 360;

  function sequenceSource() {
    if (!boxSequence) return "";
    var mobileSource = boxSequence.getAttribute("data-sequence-mobile-src");
    if ((lowPower || coarseQuery.matches || metrics.width <= 900) && mobileSource) return mobileSource;
    return boxSequence.getAttribute("data-sequence-src") || "";
  }

  function drawSequenceFrame(index, alpha) {
    if (!sequenceContext || !sequenceImage || !sequenceCellSize) return;
    var sourceX = (index % sequenceColumns) * sequenceCellSize;
    var sourceY = Math.floor(index / sequenceColumns) * sequenceCellSize;
    sequenceContext.globalAlpha = alpha == null ? 1 : alpha;
    sequenceContext.drawImage(
      sequenceImage,
      sourceX,
      sourceY,
      sequenceCellSize,
      sequenceCellSize,
      0,
      0,
      sequenceCellSize,
      sequenceCellSize
    );
    sequenceContext.globalAlpha = 1;
  }

  function drawSequencePose(elapsed) {
    if (!sequenceContext || !sequenceCellSize) return;
    sequenceContext.clearRect(0, 0, sequenceCellSize, sequenceCellSize);

    var index = 0;
    while (index < SEQUENCE_TIMES.length - 1 && elapsed >= SEQUENCE_TIMES[index + 1]) index += 1;
    drawSequenceFrame(index, 1);
  }

  function prepareSequenceCanvas() {
    if (!boxSequence || !sequenceImage || sequenceImage.naturalWidth <= 0) return false;
    var cellSize = Math.round(sequenceImage.naturalWidth / sequenceColumns);
    if (!cellSize || Math.round(sequenceImage.naturalHeight / sequenceRows) !== cellSize || sequenceFrameCount !== SEQUENCE_TIMES.length) return false;
    boxSequence.width = cellSize;
    boxSequence.height = cellSize;
    sequenceCellSize = cellSize;
    sequenceContext = boxSequence.getContext("2d", { alpha: true });
    if (!sequenceContext) return false;
    sequenceContext.imageSmoothingEnabled = true;
    sequenceContext.imageSmoothingQuality = "high";
    drawSequencePose(0);
    return true;
  }

  function waitForSequence() {
    var source = sequenceSource();
    if (!source || !boxSequence) return Promise.resolve(false);
    var loadId = ++sequenceLoadId;
    var image = new Image();
    sequenceImage = image;
    image.decoding = "async";

    return new Promise(function (resolve) {
      var settled = false;

      function settle(loaded) {
        if (settled) return;
        settled = true;
        image.onload = null;
        image.onerror = null;
        if (loadId !== sequenceLoadId || entranceCancelled || !loaded) {
          resolve(false);
          return;
        }
        resolve(prepareSequenceCanvas());
      }

      image.onload = function () {
        if (!image.decode) {
          settle(image.naturalWidth > 0);
          return;
        }
        image.decode().then(function () { settle(image.naturalWidth > 0); }, function () {
          settle(image.complete && image.naturalWidth > 0);
        });
      };
      image.onerror = function () { settle(false); };
      image.src = source;
    });
  }

  function releaseSequence() {
    sequenceLoadId += 1;
    if (sequenceImage && !sequenceImage.complete) sequenceImage.src = "";
    if (sequenceContext && sequenceCellSize) sequenceContext.clearRect(0, 0, sequenceCellSize, sequenceCellSize);
    if (boxSequence) {
      boxSequence.hidden = true;
      boxSequence.width = 1;
      boxSequence.height = 1;
    }
    sequenceImage = null;
    sequenceContext = null;
    sequenceCellSize = 0;
  }

  function constrainedConnection() {
    if (!connection) return false;
    var type = connection.effectiveType || "";
    return Boolean(connection.saveData || type === "slow-2g" || type === "2g" || type === "3g");
  }

  function hasSeenEntrance() {
    try { return window.sessionStorage.getItem("surpriz:v3:box-open-v11") === "1"; }
    catch (error) { return false; }
  }

  function markEntranceSeen() {
    try { window.sessionStorage.setItem("surpriz:v3:box-open-v11", "1"); }
    catch (error) { /* Storage can be unavailable in private contexts. */ }
  }

  function canPrepareEntrance() {
    return Boolean(boxSequence && !entrancePlayed && !entranceCancelled && !document.hidden && !reducedMotion && !constrainedConnection() && targetProgress <= 0.02 && !hasSeenEntrance());
  }

  function canContinueEntrance() {
    return Boolean(boxSequence && sequenceContext && !entranceCancelled && !document.hidden && !reducedMotion && targetProgress <= 0.02);
  }

  function finishEntrance() {
    if (entranceFrame) window.cancelAnimationFrame(entranceFrame);
    entranceFrame = 0;
    entranceStartedAt = 0;
    window.clearTimeout(entranceDelayTimer);
    entranceDelayTimer = 0;
    window.clearTimeout(entranceTimer);
    entranceTimer = 0;
    stage.classList.remove("is-entering", "is-box-prepared");
    releaseSequence();
  }

  function cancelEntrance() {
    entranceCancelled = true;
    finishEntrance();
  }

  function animateEntrance(timestamp) {
    entranceFrame = 0;
    if (!canContinueEntrance()) {
      cancelEntrance();
      return;
    }
    if (!entranceStartedAt) entranceStartedAt = timestamp;
    var elapsed = timestamp - entranceStartedAt;
    drawSequencePose(elapsed);
    if (elapsed < SEQUENCE_DURATION) {
      entranceFrame = window.requestAnimationFrame(animateEntrance);
      return;
    }
    drawSequencePose(SEQUENCE_TIMES[SEQUENCE_TIMES.length - 1]);
    finishEntrance();
  }

  function playEntrance() {
    if (!ready || !canPrepareEntrance()) {
      releaseSequence();
      return;
    }
    entrancePlayed = true;
    markEntranceSeen();
    boxSequence.hidden = false;
    drawSequencePose(0);
    stage.classList.add("is-box-prepared");
    entranceDelayTimer = window.setTimeout(function () {
      entranceDelayTimer = 0;
      if (!canContinueEntrance()) {
        cancelEntrance();
        return;
      }
      stage.classList.add("is-entering");
      entranceFrame = window.requestAnimationFrame(animateEntrance);
    }, ENTRANCE_DELAY);
    entranceTimer = window.setTimeout(finishEntrance, ENTRANCE_DELAY + SEQUENCE_DURATION + 500);
  }

  function revealStage() {
    if (ready) return;
    ready = true;
    measure();
    visualProgress = targetProgress;
    if (reducedMotion) renderReduced();
    else render(visualProgress);
    stage.classList.add("is-ready");
    stage.removeAttribute("inert");
    window.setTimeout(function () { if (loader) loader.hidden = true; }, reducedMotion ? 0 : 340);
    requestFrame();
  }

  function handleResize() {
    var nextWidth = window.innerWidth;
    var nextHeight = stage.getBoundingClientRect().height || window.innerHeight;
    var widthChanged = Math.abs(nextWidth - lastMeasuredWidth) >= 2;
    var heightChanged = Math.abs(nextHeight - lastMeasuredHeight) >= 2;
    if (!widthChanged && !heightChanged) return;
    if (widthChanged) cancelEntrance();
    lastMeasuredWidth = nextWidth;
    lastMeasuredHeight = nextHeight;
    if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
    resizeFrame = window.requestAnimationFrame(function () {
      resizeFrame = 0;
      syncEnvironment();
      measure();
    });
  }

  function initialize() {
    syncEnvironment();
    bindRail();
    bindCatalogJump();
    measure();

    var startupComplete = false;
    var sequencePromise = canPrepareEntrance() ? waitForSequence() : Promise.resolve(false);
    var startupFallback = window.setTimeout(function () {
      if (startupComplete) return;
      startupComplete = true;
      cancelEntrance();
      revealStage();
    }, 1600);

    waitForImage(boxPoster).then(function (posterLoaded) {
      if (startupComplete) return;
      if (!posterLoaded) {
        startupComplete = true;
        window.clearTimeout(startupFallback);
        cancelEntrance();
        revealStage();
        return;
      }

      var grace = new Promise(function (resolve) {
        window.setTimeout(function () { resolve(false); }, 1200);
      });
      Promise.race([sequencePromise, grace]).then(function (sequenceLoaded) {
        if (startupComplete) return;
        startupComplete = true;
        window.clearTimeout(startupFallback);
        if (!sequenceLoaded) cancelEntrance();
        revealStage();
        if (sequenceLoaded) playEntrance();
      });
    }, function () {
      if (startupComplete) return;
      startupComplete = true;
      window.clearTimeout(startupFallback);
      cancelEntrance();
      revealStage();
    });

    window.addEventListener("scroll", updateTarget, { passive: true });
    window.addEventListener("resize", handleResize, { passive: true });
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) cancelEntrance();
    });

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        inView = entries[0] ? entries[0].isIntersecting : true;
        stage.classList.toggle("is-active", inView);
        if (inView) {
          updateTarget();
          requestFrame();
        }
      }, { rootMargin: "100px 0px" }).observe(section);
    } else {
      stage.classList.add("is-active");
    }
  }

  function handleMotionChange() {
    cancelEntrance();
    syncEnvironment();
    measure();
    if (reducedMotion) renderReduced();
    else {
      visualProgress = targetProgress;
      render(visualProgress);
    }
    requestFrame();
  }

  if (motionQuery.addEventListener) motionQuery.addEventListener("change", handleMotionChange);
  else if (motionQuery.addListener) motionQuery.addListener(handleMotionChange);
  if (shortViewportQuery.addEventListener) shortViewportQuery.addEventListener("change", handleMotionChange);
  else if (shortViewportQuery.addListener) shortViewportQuery.addListener(handleMotionChange);

  initialize();
})();
