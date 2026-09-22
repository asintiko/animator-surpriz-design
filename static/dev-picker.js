(function () {
  // Picker is gated on the server side via admin toggle.
  // If this script runs at all, it means the admin enabled it.
  if (window.__pkLoaded) return;
  window.__pkLoaded = true;

  const css = `
    .__pk-toolbar { position: fixed;
      top: calc(8px + env(safe-area-inset-top, 0px));
      right: calc(8px + env(safe-area-inset-right, 0px));
      z-index: 2147483646; background: #1f1f29; color: #fff; border-radius: 999px;
      padding: 4px; display: flex; gap: 4px; align-items: center;
      box-shadow: 0 8px 24px rgba(0,0,0,.35);
      font: 600 12px/1 system-ui, -apple-system, sans-serif;
      max-width: calc(100vw - 16px); user-select: none; -webkit-user-select: none; }
    .__pk-btn { appearance: none; border: 0; padding: 7px 11px; border-radius: 999px;
      background: #2a2a37; color: #fff; cursor: pointer; min-height: 30px; font: inherit;
      white-space: nowrap; display: inline-flex; align-items: center; gap: 4px; }
    .__pk-btn:hover { background: #3a3a47; }
    .__pk-btn.is-on { background: #f26a20; }
    .__pk-btn[data-act="done"] { background: #16a34a; font-weight: 700; }
    .__pk-btn[data-act="done"][disabled] { background: #2a2a37; opacity: .5; cursor: not-allowed; }
    .__pk-btn[data-act="hide"] { padding: 7px 9px; }
    .__pk-toolbar.__pk-empty .__pk-btn[data-act="done"],
    .__pk-toolbar.__pk-empty .__pk-btn[data-act="clear"] { display: none; }

    .__pk-overlay { position: fixed; pointer-events: none; z-index: 2147483645;
      border: 2px solid #f26a20; background: rgba(242,106,32,.18);
      border-radius: 4px; transition: all 0.06s ease; display: none; }

    .__pk-pin { position: absolute; z-index: 2147483640;
      width: 26px; height: 26px; border-radius: 999px;
      background: #f26a20; color: #fff; border: 2px solid #fff;
      box-shadow: 0 4px 14px rgba(0,0,0,.4);
      display: flex; align-items: center; justify-content: center;
      font: 700 12px/1 system-ui, -apple-system, sans-serif;
      transform: translate(-50%, -50%); cursor: pointer; pointer-events: auto; }
    .__pk-pin:hover { transform: translate(-50%, -50%) scale(1.15); }

    .__pk-modal { position: fixed; inset: 0; z-index: 2147483647;
      background: rgba(0,0,0,.5); display: flex; align-items: flex-start;
      justify-content: center; padding: 20px 12px;
      padding-top: calc(20px + env(safe-area-inset-top, 0px));
      padding-bottom: calc(20px + env(safe-area-inset-bottom, 0px));
      overflow-y: auto; }
    .__pk-card { background: #fff; color: #111; border-radius: 16px; padding: 16px;
      box-shadow: 0 18px 60px rgba(0,0,0,.35);
      font: 500 14px/1.45 system-ui, -apple-system, sans-serif;
      width: 100%; max-width: 540px; }
    .__pk-card h3 { margin: 0 0 12px; font: 700 16px/1.3 system-ui;
      display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .__pk-card .__pk-close-x { background: transparent; border: 0; font-size: 24px;
      color: #888; cursor: pointer; line-height: 1; padding: 0 4px; }

    .__pk-list { margin: 0 0 12px; padding: 0; list-style: none;
      display: flex; flex-direction: column; gap: 10px; }
    .__pk-list li { padding: 10px; border-radius: 10px; background: #f5f5f7;
      display: flex; flex-direction: column; gap: 6px; }
    .__pk-row1 { display: flex; gap: 8px; align-items: center; }
    .__pk-num { flex: 0 0 26px; height: 26px; border-radius: 999px;
      background: #f26a20; color: #fff; display: inline-flex; align-items: center;
      justify-content: center; font: 700 12px/1 system-ui; }
    .__pk-sel { font: 600 11px/1.4 ui-monospace, Menlo, monospace;
      color: #555; word-break: break-all; flex: 1; min-width: 0; }
    .__pk-x { background: transparent; color: #999; border: 0; cursor: pointer;
      padding: 0 4px; font-size: 22px; line-height: 1; flex: 0 0 auto; }
    .__pk-x:hover { color: #dc2626; }
    .__pk-cmt { width: 100%; min-height: 60px; box-sizing: border-box;
      border: 1px solid #ddd; border-radius: 8px; padding: 8px;
      font: 500 14px/1.4 system-ui, -apple-system, sans-serif;
      resize: vertical; }
    .__pk-cmt:focus { outline: none; border-color: #f26a20; }

    .__pk-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
    .__pk-actions button { appearance: none; border: 0; padding: 12px 16px;
      border-radius: 10px; background: #f26a20; color: #fff; font-weight: 700;
      cursor: pointer; font-size: 15px; flex: 1; min-width: 110px; }
    .__pk-actions button.alt { background: #2a2a37; }
    .__pk-actions button[disabled] { opacity: .5; cursor: not-allowed; }

    .__pk-status { padding: 10px 12px; border-radius: 8px;
      background: #f0fdf4; color: #16a34a; font-weight: 600; margin-top: 8px;
      text-align: center; }
    .__pk-status.err { background: #fef2f2; color: #dc2626; }
  `;
  const style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  // ---------- DOM ----------
  const overlay = document.createElement("div");
  overlay.className = "__pk-overlay";
  document.body.appendChild(overlay);

  const pinsLayer = document.createElement("div");
  pinsLayer.style.cssText = "position:absolute;top:0;left:0;width:0;height:0;pointer-events:none;";
  document.body.appendChild(pinsLayer);

  const toolbar = document.createElement("div");
  toolbar.className = "__pk-toolbar __pk-empty";

  const btnPick = document.createElement("button");
  btnPick.className = "__pk-btn"; btnPick.dataset.act = "pick";
  const pickIcon = document.createElement("span"); pickIcon.textContent = "⨯";
  const pickLabel = document.createElement("span"); pickLabel.textContent = " Pick";
  btnPick.appendChild(pickIcon); btnPick.appendChild(pickLabel);

  const btnDone = document.createElement("button");
  btnDone.className = "__pk-btn"; btnDone.dataset.act = "done";
  btnDone.textContent = "✓ Готово (0)";
  btnDone.disabled = true;

  const btnClear = document.createElement("button");
  btnClear.className = "__pk-btn"; btnClear.dataset.act = "clear";
  btnClear.textContent = "🗑";
  btnClear.title = "Очистить пины";

  toolbar.appendChild(btnPick);
  toolbar.appendChild(btnDone);
  toolbar.appendChild(btnClear);
  document.body.appendChild(toolbar);

  // ---------- state ----------
  let active = false;
  /** @type {Array<{id:string,n:number,selector:string,tag:string,text:string,rect:object,docX:number,docY:number,comment:string,ts:string,pinEl:HTMLElement}>} */
  let pins = [];

  // ---------- helpers ----------
  const buildSelector = (el) => {
    if (!el || el === document.body) return "body";
    const path = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && path.length < 5) {
      let part = node.tagName.toLowerCase();
      if (node.id) { part += "#" + node.id; path.unshift(part); break; }
      const cls = (node.className && typeof node.className === "string")
        ? node.className.trim().split(/\s+/).filter((c) => !c.startsWith("__pk-")).slice(0, 3).join(".")
        : "";
      if (cls) part += "." + cls;
      const parent = node.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
        if (same.length > 1) part += `:nth-of-type(${same.indexOf(node) + 1})`;
      }
      path.unshift(part);
      node = node.parentElement;
    }
    return path.join(" > ");
  };

  const refreshUI = () => {
    btnDone.textContent = "✓ Готово (" + pins.length + ")";
    btnDone.disabled = pins.length === 0;
    toolbar.classList.toggle("__pk-empty", pins.length === 0);
    pins.forEach((p, i) => {
      p.n = i + 1;
      if (p.pinEl) p.pinEl.textContent = String(i + 1);
    });
  };

  const removePin = (id) => {
    const idx = pins.findIndex((p) => p.id === id);
    if (idx < 0) return;
    if (pins[idx].pinEl) pins[idx].pinEl.remove();
    pins.splice(idx, 1);
    refreshUI();
  };

  const clearPins = () => {
    pins.forEach((p) => p.pinEl && p.pinEl.remove());
    pins = [];
    refreshUI();
  };

  const createPinEl = (pin) => {
    const el = document.createElement("div");
    el.className = "__pk-pin";
    el.textContent = String(pin.n);
    el.style.left = pin.docX + "px";
    el.style.top = pin.docY + "px";
    el.addEventListener("click", (ev) => {
      ev.preventDefault(); ev.stopPropagation();
      if (confirm("Удалить пин #" + pin.n + "?")) removePin(pin.id);
    });
    return el;
  };

  // ---------- overlay ----------
  const setOverlay = (target) => {
    if (!target) { overlay.style.display = "none"; return; }
    const r = target.getBoundingClientRect();
    overlay.style.display = "block";
    overlay.style.left = r.left + "px";
    overlay.style.top = r.top + "px";
    overlay.style.width = r.width + "px";
    overlay.style.height = r.height + "px";
  };

  const isInternal = (el) =>
    !el || el.closest(".__pk-toolbar, .__pk-modal, .__pk-pin, .__pk-overlay");

  const onMove = (e) => {
    if (!active) return;
    const pt = e.touches ? e.touches[0] : e;
    if (!pt) return;
    const el = document.elementFromPoint(pt.clientX, pt.clientY);
    if (isInternal(el)) return;
    setOverlay(el);
  };

  const onPick = (e) => {
    if (!active) return;
    const pt = e.touches ? e.changedTouches[0] : e;
    if (!pt) return;
    const el = document.elementFromPoint(pt.clientX, pt.clientY);
    if (isInternal(el)) return;
    e.preventDefault();
    e.stopPropagation();

    const r = el.getBoundingClientRect();
    const pin = {
      id: "p_" + Date.now() + "_" + Math.random().toString(36).slice(2, 6),
      n: pins.length + 1,
      selector: buildSelector(el),
      tag: el.tagName.toLowerCase(),
      text: (el.innerText || "").slice(0, 200),
      rect: {
        x: Math.round(r.left + window.scrollX),
        y: Math.round(r.top + window.scrollY),
        w: Math.round(r.width),
        h: Math.round(r.height),
      },
      docX: pt.clientX + window.scrollX,
      docY: pt.clientY + window.scrollY,
      comment: "",
      ts: new Date().toISOString(),
    };
    pin.pinEl = createPinEl(pin);
    pinsLayer.appendChild(pin.pinEl);
    pins.push(pin);
    overlay.style.display = "none";
    refreshUI();
  };

  // ---------- modal ----------
  const closeModal = () => {
    document.querySelectorAll(".__pk-modal").forEach((n) => n.remove());
  };

  const openDoneModal = () => {
    if (pins.length === 0) return;
    closeModal();

    // pause picking while modal open
    const wasActive = active;
    if (active) {
      active = false;
      pickIcon.textContent = "⨯";
      btnPick.classList.remove("is-on");
      overlay.style.display = "none";
    }

    const modal = document.createElement("div");
    modal.className = "__pk-modal";
    modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

    const card = document.createElement("div");
    card.className = "__pk-card";
    modal.appendChild(card);

    const h3 = document.createElement("h3");
    const title = document.createElement("span");
    title.textContent = "Пины (" + pins.length + ") — комментарии";
    const closeX = document.createElement("button");
    closeX.className = "__pk-close-x";
    closeX.textContent = "×";
    closeX.addEventListener("click", () => {
      closeModal();
      if (wasActive) {
        active = true;
        pickIcon.textContent = "●";
        btnPick.classList.add("is-on");
      }
    });
    h3.appendChild(title);
    h3.appendChild(closeX);
    card.appendChild(h3);

    const ul = document.createElement("ul");
    ul.className = "__pk-list";

    const renderList = () => {
      ul.textContent = "";
      pins.forEach((p) => {
        const li = document.createElement("li");

        const row1 = document.createElement("div");
        row1.className = "__pk-row1";
        const num = document.createElement("span");
        num.className = "__pk-num";
        num.textContent = String(p.n);
        const sel = document.createElement("div");
        sel.className = "__pk-sel";
        sel.textContent = (p.tag || "?") + " · " + p.selector;
        const x = document.createElement("button");
        x.className = "__pk-x";
        x.textContent = "×";
        x.title = "Удалить пин";
        x.addEventListener("click", () => {
          removePin(p.id);
          if (pins.length === 0) {
            closeModal();
          } else {
            renderList();
            title.textContent = "Пины (" + pins.length + ") — комментарии";
          }
        });
        row1.appendChild(num);
        row1.appendChild(sel);
        row1.appendChild(x);
        li.appendChild(row1);

        const ta = document.createElement("textarea");
        ta.className = "__pk-cmt";
        ta.placeholder = "Что не так с этим элементом? (можно оставить пустым)";
        ta.value = p.comment || "";
        ta.addEventListener("input", () => { p.comment = ta.value; });
        li.appendChild(ta);

        ul.appendChild(li);
      });
    };
    renderList();
    card.appendChild(ul);

    const status = document.createElement("div");
    status.style.display = "none";
    card.appendChild(status);

    const actions = document.createElement("div");
    actions.className = "__pk-actions";

    const btnCancel = document.createElement("button");
    btnCancel.className = "alt";
    btnCancel.textContent = "Назад";
    btnCancel.addEventListener("click", closeX.click.bind(closeX));

    const btnSend = document.createElement("button");
    btnSend.textContent = "Отправить";
    btnSend.addEventListener("click", async () => {
      btnSend.disabled = true;
      btnCancel.disabled = true;
      btnSend.textContent = "Отправка...";
      const payload = {
        url: window.location.href,
        ts: new Date().toISOString(),
        viewport: { w: window.innerWidth, h: window.innerHeight },
        ua: navigator.userAgent,
        pins: pins.map((p) => ({
          n: p.n, selector: p.selector, tag: p.tag, text: p.text,
          rect: p.rect, comment: p.comment, ts: p.ts,
        })),
      };
      try {
        const res = await fetch("/__picker_select", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        status.style.display = "block";
        status.className = "__pk-status";
        status.textContent = "✓ Отправлено: " + pins.length + " пин(ов)";
        clearPins();
        setTimeout(() => closeModal(), 900);
      } catch (e) {
        status.style.display = "block";
        status.className = "__pk-status err";
        status.textContent = "Ошибка: " + e.message;
        btnSend.disabled = false;
        btnCancel.disabled = false;
        btnSend.textContent = "Отправить";
      }
    });

    actions.appendChild(btnCancel);
    actions.appendChild(btnSend);
    card.appendChild(actions);

    document.body.appendChild(modal);
  };

  // ---------- toolbar handlers ----------
  toolbar.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;

    if (act === "pick") {
      active = !active;
      if (active) {
        pickIcon.textContent = "●";
        btnPick.classList.add("is-on");
      } else {
        pickIcon.textContent = "⨯";
        btnPick.classList.remove("is-on");
        overlay.style.display = "none";
      }
    } else if (act === "done") {
      openDoneModal();
    } else if (act === "clear") {
      if (pins.length > 0 && confirm("Удалить все " + pins.length + " пинов?")) {
        clearPins();
      }
    }
  });

  // ---------- listeners ----------
  document.addEventListener("mousemove", onMove, true);
  document.addEventListener("touchmove", onMove, { passive: true, capture: true });
  document.addEventListener("click", onPick, true);
  document.addEventListener("touchend", onPick, { passive: false, capture: true });

  refreshUI();
})();
