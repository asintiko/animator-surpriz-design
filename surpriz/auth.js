(() => {
  "use strict";

  const modal = document.querySelector("[data-auth-modal]");
  if (!modal) return;

  const authParams = new URLSearchParams(window.location.search);
  const requestedAuthMode = authParams.get("auth");
  const authNextUrl = authParams.get("next") || window.location.pathname || "/surpriz/";

  const openButtons = [...document.querySelectorAll("[data-auth-open]")];
  const closeButtons = [...modal.querySelectorAll("[data-auth-close]")];
  const sendStep = modal.querySelector('[data-auth-step="send"]');
  const verifyStep = modal.querySelector('[data-auth-step="verify"]');
  const sendForm = modal.querySelector("[data-auth-send-form]");
  const verifyForm = modal.querySelector("[data-auth-verify-form]");
  const modeSwitch = modal.querySelector("[data-auth-mode-switch]");
  const nameField = modal.querySelector("[data-auth-name-field]");
  const nameInput = sendForm.elements.full_name;
  const phoneInput = modal.querySelector("[data-auth-phone]");
  const consentInput = modal.querySelector("[data-auth-consent]");
  const consentWrap = modal.querySelector("[data-auth-consent-wrap]");
  const status = modal.querySelector("[data-auth-status]");
  const title = modal.querySelector("[data-auth-title]");
  const subtitle = modal.querySelector("[data-auth-subtitle]");
  const sendLabel = modal.querySelector("[data-auth-send-label]");
  const verifyLabel = modal.querySelector("[data-auth-verify-label]");
  const phoneDisplay = modal.querySelector("[data-auth-phone-display]");
  const codeWrap = modal.querySelector("[data-auth-code]");
  const codeInputs = [...modal.querySelectorAll("[data-auth-code-digit]")];
  const backButton = modal.querySelector("[data-auth-back]");
  const resendButton = modal.querySelector("[data-auth-resend]");

  const state = {
    authenticated: false,
    cooldownTimer: null,
    fullName: "",
    mode: "register",
    opener: null,
    phone: "",
    requestId: "",
    nextUrl: authNextUrl,
  };
  const backgroundState = new Map();

  const authRequest = async (path, options = {}) => {
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
      ...options,
    });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : {};
    if (!response.ok) {
      const error = new Error(payload.message || "Сервис авторизации временно недоступен.");
      error.payload = payload;
      throw error;
    }
    return payload;
  };

  const setStatus = (message = "", type = "error") => {
    status.hidden = !message;
    status.textContent = message;
    status.classList.toggle("is-error", Boolean(message) && type === "error");
    status.classList.toggle("is-success", Boolean(message) && type === "success");
  };

  const setBusy = (form, busy) => {
    const button = form.querySelector('button[type="submit"]');
    button.disabled = busy;
    form.setAttribute("aria-busy", String(busy));
  };

  const localPhoneDigits = (value) => {
    let digits = String(value || "").replace(/\D/g, "");
    if (digits.startsWith("998")) digits = digits.slice(3);
    if (digits.length === 10 && digits.startsWith("0")) digits = digits.slice(1);
    return digits.slice(0, 9);
  };

  const formatPhone = (value) => {
    const digits = localPhoneDigits(value);
    if (!digits) return "";
    let formatted = "+998";
    if (digits.length) formatted += ` (${digits.slice(0, 2)}`;
    if (digits.length >= 2) formatted += ")";
    if (digits.length > 2) formatted += ` ${digits.slice(2, 5)}`;
    if (digits.length > 5) formatted += `-${digits.slice(5, 7)}`;
    if (digits.length > 7) formatted += `-${digits.slice(7, 9)}`;
    return formatted;
  };

  const setMode = (mode) => {
    state.mode = mode === "login" ? "login" : "register";
    const isLogin = state.mode === "login";
    nameField.hidden = isLogin;
    nameInput.required = !isLogin;
    title.textContent = isLogin ? "Вход" : "Регистрация";
    subtitle.textContent = isLogin ? "Вернитесь в свой аккаунт Surpriz" : "Быстрый вход и запись на праздник";
    sendLabel.textContent = isLogin ? "Войти по коду из Telegram" : "Получить код в Telegram";
    verifyLabel.textContent = isLogin ? "Войти в аккаунт" : "Завершить регистрацию";
    modeSwitch.textContent = isLogin ? "Нет аккаунта? Зарегистрироваться" : "Уже есть аккаунт? Войти";
    setStatus();
  };

  const showSendStep = () => {
    sendStep.hidden = false;
    verifyStep.hidden = true;
    codeInputs.forEach((input) => { input.value = ""; });
    codeWrap.classList.remove("is-invalid");
    setStatus();
  };

  const showVerifyStep = (displayPhone) => {
    sendStep.hidden = true;
    verifyStep.hidden = false;
    title.textContent = "Подтверждение";
    subtitle.textContent = "Последний шаг — код из Telegram";
    phoneDisplay.textContent = displayPhone || formatPhone(state.phone);
    setStatus("Код отправлен. Обычно он приходит в течение нескольких секунд.", "success");
    window.setTimeout(() => codeInputs[0].focus(), 60);
  };

  const startCooldown = (seconds) => {
    if (state.cooldownTimer) window.clearInterval(state.cooldownTimer);
    let remaining = Math.max(0, Number(seconds) || 0);

    const render = () => {
      resendButton.disabled = remaining > 0;
      resendButton.textContent = remaining > 0 ? `Повторить через ${remaining} сек.` : "Отправить код повторно";
    };

    render();
    state.cooldownTimer = window.setInterval(() => {
      remaining -= 1;
      render();
      if (remaining <= 0) {
        window.clearInterval(state.cooldownTimer);
        state.cooldownTimer = null;
      }
    }, 1000);
  };

  const updateAccountButton = (customer = {}) => {
    const displayName = String(customer.display_name || customer.full_name || "Личный кабинет").trim();
    const headerButton = document.querySelector(".header__register");
    const headerLabel = headerButton?.querySelector("[data-auth-label]");
    if (headerLabel) headerLabel.textContent = displayName;
    if (headerButton) {
      headerButton.classList.add("is-authenticated");
      headerButton.setAttribute("aria-label", displayName);
    }

    state.authenticated = true;
    openButtons.forEach((button) => {
      button.dataset.authenticated = "true";
      button.setAttribute("href", "/account/");
    });
  };

  const loadSession = async () => {
    try {
      const payload = await authRequest("/api/auth/session");
      if (payload.authenticated && payload.customer) updateAccountButton(payload.customer);
    } catch (_) {
      // Static preview has no backend; the same-origin endpoint is available in the Flask app.
    }
  };

  const setBackgroundDisabled = (disabled) => {
    [...document.body.children]
      .filter((element) => element !== modal && element.tagName !== "SCRIPT")
      .forEach((element) => {
        if (disabled) {
          if (!backgroundState.has(element)) {
            backgroundState.set(element, {
              ariaHidden: element.getAttribute("aria-hidden"),
              inert: element.hasAttribute("inert"),
            });
          }
          element.setAttribute("inert", "");
          element.setAttribute("aria-hidden", "true");
          return;
        }

        const previousState = backgroundState.get(element);
        if (!previousState?.inert) element.removeAttribute("inert");
        if (previousState?.ariaHidden === null) element.removeAttribute("aria-hidden");
        else if (previousState?.ariaHidden !== undefined) element.setAttribute("aria-hidden", previousState.ariaHidden);
        backgroundState.delete(element);
      });
  };

  const openModal = (opener) => {
    if (state.authenticated) return;
    state.opener = opener || document.activeElement;
    setMode("register");
    showSendStep();
    modal.hidden = false;
    document.body.classList.add("auth-modal-open");
    nameInput.focus({ preventScroll: true });
    setBackgroundDisabled(true);
  };

  const closeModal = () => {
    setBackgroundDisabled(false);
    modal.hidden = true;
    document.body.classList.remove("auth-modal-open");
    setStatus();
    state.opener?.focus?.();
  };

  const validateSendForm = () => {
    const fullName = nameInput.value.trim();
    const phoneIsValid = localPhoneDigits(phoneInput.value).length === 9;
    const nameIsValid = state.mode === "login" || (fullName.length >= 2 && fullName.length <= 80);
    const consentIsValid = consentInput.checked;

    nameField.classList.toggle("is-invalid", !nameIsValid);
    phoneInput.closest(".auth-field").classList.toggle("is-invalid", !phoneIsValid);
    consentWrap.classList.toggle("is-invalid", !consentIsValid);

    if (!nameIsValid) {
      setStatus("Укажите имя, чтобы мы могли обращаться к вам.");
      nameInput.focus();
      return false;
    }
    if (!phoneIsValid) {
      setStatus("Введите корректный номер Узбекистана.");
      phoneInput.focus();
      return false;
    }
    if (!consentIsValid) {
      setStatus("Подтвердите согласие на обработку персональных данных.");
      consentInput.focus();
      return false;
    }
    return true;
  };

  const sendTelegramCode = async ({ allowLoginFallback = true } = {}) => {
    state.fullName = nameInput.value.trim();
    state.phone = formatPhone(phoneInput.value);

    try {
      const payload = await authRequest("/api/auth/send-telegram-code", {
        body: JSON.stringify({
          full_name: state.mode === "register" ? state.fullName : "",
          next: state.nextUrl,
          phone: state.phone,
          purpose: state.mode,
        }),
        method: "POST",
      });
      state.requestId = payload.request_id;
      state.phone = payload.phone_e164 || state.phone;
      showVerifyStep(payload.phone_display);
      startCooldown(payload.cooldown || 60);
    } catch (error) {
      const alreadyRegistered = state.mode === "register" && (
        error.payload?.error_code === "account_exists" || /уже зарегистрирован/i.test(error.message)
      );
      if (alreadyRegistered && allowLoginFallback) {
        setMode("login");
        await sendTelegramCode({ allowLoginFallback: false });
        return;
      }
      setStatus(error.message);
      throw error;
    }
  };

  openButtons.forEach((button) => {
    button.addEventListener("click", (event) => {
      if (button.dataset.authenticated === "true") return;
      event.preventDefault();
      openModal(button);
    });
  });

  closeButtons.forEach((button) => button.addEventListener("click", closeModal));
  modeSwitch.addEventListener("click", () => setMode(state.mode === "register" ? "login" : "register"));
  backButton.addEventListener("click", () => {
    setMode(state.mode);
    showSendStep();
    phoneInput.focus();
  });

  phoneInput.addEventListener("input", () => {
    phoneInput.value = formatPhone(phoneInput.value);
    phoneInput.closest(".auth-field").classList.remove("is-invalid");
  });
  nameInput.addEventListener("input", () => nameField.classList.remove("is-invalid"));
  consentInput.addEventListener("change", () => consentWrap.classList.remove("is-invalid"));

  sendForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setStatus();
    if (!validateSendForm()) return;
    setBusy(sendForm, true);
    try {
      await sendTelegramCode();
    } catch (_) {
      // The visible status message is set by sendTelegramCode.
    } finally {
      setBusy(sendForm, false);
    }
  });

  codeInputs.forEach((input, index) => {
    input.addEventListener("input", () => {
      const digits = input.value.replace(/\D/g, "");
      if (digits.length > 1) {
        digits.slice(0, codeInputs.length - index).split("").forEach((digit, offset) => {
          codeInputs[index + offset].value = digit;
        });
        codeInputs[Math.min(index + digits.length, codeInputs.length) - 1].focus();
        codeWrap.classList.remove("is-invalid");
        return;
      } else {
        input.value = digits.slice(-1);
      }
      codeWrap.classList.remove("is-invalid");
      if (input.value && codeInputs[index + 1]) codeInputs[index + 1].focus();
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Backspace" && !input.value && codeInputs[index - 1]) codeInputs[index - 1].focus();
    });
    input.addEventListener("paste", (event) => {
      const digits = event.clipboardData?.getData("text").replace(/\D/g, "").slice(0, 6) || "";
      if (!digits) return;
      event.preventDefault();
      digits.split("").forEach((digit, digitIndex) => {
        if (codeInputs[digitIndex]) codeInputs[digitIndex].value = digit;
      });
      codeInputs[Math.min(digits.length, 6) - 1].focus();
    });
  });

  verifyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setStatus();
    const code = codeInputs.map((input) => input.value).join("");
    if (!/^\d{6}$/.test(code)) {
      codeWrap.classList.add("is-invalid");
      setStatus("Введите все шесть цифр из сообщения Telegram.");
      codeInputs.find((input) => !input.value)?.focus();
      return;
    }

    setBusy(verifyForm, true);
    try {
      const payload = await authRequest("/api/auth/verify-telegram-code", {
        body: JSON.stringify({ code, phone: state.phone, request_id: state.requestId }),
        method: "POST",
      });
      if (!payload.verified) throw new Error(payload.message || "Код не подтверждён.");
      updateAccountButton(payload.customer || { display_name: state.fullName || "Личный кабинет" });
      setStatus("Готово! Аккаунт подтверждён.", "success");
      window.setTimeout(() => {
        closeModal();
        if (typeof payload.redirect_url === "string" && payload.redirect_url) window.location.assign(payload.redirect_url);
      }, 700);
    } catch (error) {
      codeWrap.classList.add("is-invalid");
      setStatus(error.message);
    } finally {
      setBusy(verifyForm, false);
    }
  });

  resendButton.addEventListener("click", async () => {
    resendButton.disabled = true;
    setStatus();
    try {
      await sendTelegramCode({ allowLoginFallback: false });
    } catch (_) {
      resendButton.disabled = false;
    }
  });

  modal.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeModal();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = [...modal.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"])')]
      .filter((element) => !element.closest("[hidden]") && element.offsetParent !== null);
    if (!focusable.length) return;
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

  loadSession().finally(() => {
    if (state.authenticated || !["register", "login"].includes(requestedAuthMode)) return;
    openModal(openButtons[0] || document.body);
    setMode(requestedAuthMode);
    const cleanUrl = new URL(window.location.href);
    cleanUrl.searchParams.delete("auth");
    window.history.replaceState({}, "", cleanUrl);
  });
})();
