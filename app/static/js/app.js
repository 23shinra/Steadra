document.addEventListener("DOMContentLoaded", () => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content");

  if (window.location.pathname === "/ai") {
    const url = new URL(window.location.href);
    if (url.searchParams.has("thread")) {
      url.searchParams.delete("thread");
      const query = url.searchParams.toString();
      history.replaceState(null, "", url.pathname + (query ? `?${query}` : "") + url.hash);
    }
  }

  const initTabbarLiquid = () => {
    const bar = document.querySelector(".tabbar");
    const glass = bar?.querySelector(".tabbar__glass");
    if (!bar || !glass) return;

    const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const pillRect = (tab) => {
      const br = bar.getBoundingClientRect();
      const tr = tab.getBoundingClientRect();
      return {
        x: tr.left - br.left,
        y: tr.top - br.top,
        w: tr.width,
        h: tr.height,
      };
    };

    const setGlass = (rect, { animate = true } = {}) => {
      if (!animate) glass.style.transition = "none";
      else glass.style.transition = "";
      glass.style.width = `${rect.w}px`;
      glass.style.height = `${rect.h}px`;
      glass.style.transform = `translate3d(${rect.x}px, ${rect.y}px, 0)`;
      if (!animate) {
        void glass.offsetWidth;
        glass.style.transition = "";
      }
    };

    const syncActiveTab = (tab) => {
      bar.querySelectorAll(".tab").forEach((item) => item.classList.remove("is-active"));
      tab?.classList.add("is-active");
    };

    const placeOnActive = ({ animate = false } = {}) => {
      const active = bar.querySelector(".tab.is-active") || bar.querySelector(".tab");
      if (!active) return;
      setGlass(pillRect(active), { animate });
      glass.classList.add("is-ready");
    };

    placeOnActive({ animate: false });
    window.addEventListener("resize", () => placeOnActive({ animate: false }));

    let pendingNav = false;
    let finishTimer = 0;

    const finishTabAnimation = (targetTab, href) => {
      window.clearTimeout(finishTimer);
      glass.classList.remove("is-moving");
      bar.classList.remove("is-tabbar-animating");
      setGlass(pillRect(targetTab), { animate: false });
      syncActiveTab(targetTab);
      pendingNav = false;
      if (href) window.location.href = href;
    };

    bar.addEventListener("click", (event) => {
      const tab = event.target.closest("a.tab");
      if (!tab || !bar.contains(tab)) return;
      if (tab.classList.contains("is-active")) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button) return;
      if (pendingNav) {
        event.preventDefault();
        return;
      }

      const current = bar.querySelector(".tab.is-active") || tab;
      const from = pillRect(current);
      const to = pillRect(tab);
      const href = tab.href;

      if (reduceMotion()) {
        syncActiveTab(tab);
        setGlass(to, { animate: false });
        return;
      }

      event.preventDefault();
      pendingNav = true;
      bar.classList.add("is-tabbar-animating");
      setGlass(from, { animate: false });
      glass.classList.add("is-moving", "is-ready");
      window.requestAnimationFrame(() => {
        setGlass(to, { animate: true });
      });

      const onTransitionEnd = (transitionEvent) => {
        if (transitionEvent.target !== glass) return;
        if (transitionEvent.propertyName !== "transform") return;
        glass.removeEventListener("transitionend", onTransitionEnd);
        finishTabAnimation(tab, href);
      };
      glass.addEventListener("transitionend", onTransitionEnd);

      finishTimer = window.setTimeout(() => {
        glass.removeEventListener("transitionend", onTransitionEnd);
        finishTabAnimation(tab, href);
      }, 520);
    });
  };
  initTabbarLiquid();

  const ensureToastHost = () => {
    let host = document.getElementById("flash-toasts");
    if (!host) {
      host = document.createElement("div");
      host.id = "flash-toasts";
      host.className = "flash-toasts";
      host.setAttribute("aria-live", "polite");
      document.body.appendChild(host);
    }
    return host;
  };

  const dismissFlashToast = (toast, dx = 0) => {
    if (!toast || toast.dataset.leaving === "1") return;
    toast.dataset.leaving = "1";
    const dir = dx === 0 ? (Math.random() > 0.5 ? 1 : -1) : Math.sign(dx) || 1;
    toast.style.transition = "transform .28s cubic-bezier(0.22, 1, 0.36, 1), opacity .28s ease";
    toast.style.transform = `translate3d(${dir * 120}%, 0, 0)`;
    toast.style.opacity = "0";
    window.setTimeout(() => toast.remove(), 280);
  };

  const bindFlashToast = (toast) => {
    if (!(toast instanceof HTMLElement) || toast.dataset.bound === "1") return;
    toast.dataset.bound = "1";
    toast.classList.add("flash-toast");
    window.requestAnimationFrame(() => {
      toast.classList.add("is-visible");
    });

    let startX = 0;
    let startY = 0;
    let dx = 0;
    let dragging = false;
    let axis = null;

    const onStart = (event) => {
      if (toast.dataset.leaving === "1") return;
      const point = event.touches ? event.touches[0] : event;
      startX = point.clientX;
      startY = point.clientY;
      dx = 0;
      dragging = true;
      axis = null;
      toast.style.transition = "none";
    };

    const onMove = (event) => {
      if (!dragging) return;
      const point = event.touches ? event.touches[0] : event;
      const moveX = point.clientX - startX;
      const moveY = point.clientY - startY;
      if (!axis) {
        if (Math.abs(moveX) < 8 && Math.abs(moveY) < 8) return;
        axis = Math.abs(moveX) > Math.abs(moveY) ? "x" : "y";
      }
      if (axis !== "x") return;
      if (event.cancelable) event.preventDefault();
      dx = moveX;
      toast.style.transform = `translate3d(${dx}px, 0, 0)`;
      toast.style.opacity = String(Math.max(0.25, 1 - Math.abs(dx) / 180));
    };

    const onEnd = () => {
      if (!dragging) return;
      dragging = false;
      if (Math.abs(dx) > 72) {
        dismissFlashToast(toast, dx);
        return;
      }
      toast.style.transition = "transform .22s cubic-bezier(0.22, 1, 0.36, 1), opacity .22s ease";
      toast.style.transform = "translate3d(0, 0, 0)";
      toast.style.opacity = "1";
    };

    toast.addEventListener("touchstart", onStart, { passive: true });
    toast.addEventListener("touchmove", onMove, { passive: false });
    toast.addEventListener("touchend", onEnd);
    toast.addEventListener("touchcancel", onEnd);
    toast.addEventListener("pointerdown", (event) => {
      if (event.pointerType === "touch") return;
      onStart(event);
      const move = (ev) => onMove(ev);
      const up = () => {
        onEnd();
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    });

    window.setTimeout(() => dismissFlashToast(toast), 2000);
  };

  const showAppToast = (message, category = "info") => {
    const text = String(message || "").trim();
    if (!text) return;
    const host = ensureToastHost();
    const toast = document.createElement("div");
    toast.className = `flash-toast flash-toast--${category}`;
    toast.dataset.flashToast = "";
    toast.setAttribute("role", "status");
    toast.textContent = text;
    host.appendChild(toast);
    bindFlashToast(toast);
  };
  window.showAppToast = showAppToast;

  document.body.addEventListener("showToast", (event) => {
    const detail = event.detail || {};
    showAppToast(detail.message, detail.category || "info");
  });

  const promoteInlineFlashToasts = (root = document) => {
    root.querySelectorAll("[data-flash-toast]:not(.flash-toast)").forEach((node) => {
      const host = ensureToastHost();
      const toast = document.createElement("div");
      const category = Array.from(node.classList)
        .find((name) => name.startsWith("flash-") && name !== "flash")
        ?.replace("flash-", "") || "info";
      toast.className = `flash-toast flash-toast--${category}`;
      toast.dataset.flashToast = "";
      toast.setAttribute("role", "status");
      toast.textContent = node.textContent?.trim() || "";
      node.remove();
      if (!toast.textContent) return;
      host.appendChild(toast);
      bindFlashToast(toast);
    });
  };

  document.querySelectorAll("[data-flash-toast]").forEach((toast) => {
    if (toast.classList.contains("flash-toast") || toast.closest("#flash-toasts")) {
      bindFlashToast(toast);
      return;
    }
    promoteInlineFlashToasts(toast.parentElement || document);
  });
  promoteInlineFlashToasts();

  document.body.addEventListener("htmx:configRequest", (event) => {
    if (csrf) event.detail.headers["X-CSRFToken"] = csrf;
  });

  // Global busy state for HTMX forms (OTP, step submit, feed, etc.)
  const setFormBusy = (form, busy) => {
    if (!form || form.tagName !== "FORM") return;
    if (form.id === "chat-form" || form.classList.contains("chat-composer")) return;
    form.classList.toggle("is-submitting", busy);
    form.querySelectorAll('button[type="submit"]').forEach((btn) => {
      btn.disabled = busy;
      if (busy) btn.setAttribute("aria-busy", "true");
      else btn.removeAttribute("aria-busy");
    });
  };

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const elt = event.detail.elt;
    const form = elt?.tagName === "FORM" ? elt : elt?.closest?.("form");
    if (form) setFormBusy(form, true);
  });

  const clearBusy = (event) => {
    const elt = event.detail?.elt;
    const form = elt?.tagName === "FORM" ? elt : elt?.closest?.("form");
    if (form) setFormBusy(form, false);
  };
  document.body.addEventListener("htmx:afterRequest", clearBusy);
  document.body.addEventListener("htmx:responseError", clearBusy);
  document.body.addEventListener("htmx:sendError", clearBusy);

  // Non-HTMX forms (onboarding profile, classic POSTs)
  document.body.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.hasAttribute("hx-post") || form.hasAttribute("hx-get") || form.hasAttribute("hx-put")) return;
    if (form.dataset.noBusy === "1") return;
    if (form.classList.contains("is-submitting")) {
      event.preventDefault();
      return;
    }
    setFormBusy(form, true);
  });

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const form = event.detail.elt;
    if (!form?.closest?.("#step-goals") || form.tagName !== "FORM") return;
    const item = form.closest(".step-goals__item");
    if (!item) return;
    if (item.classList.contains("is-busy")) {
      event.preventDefault();
      return;
    }
    const wasDone = item.classList.contains("is-done") && !item.classList.contains("is-unchecking");
    item.classList.add("is-busy");
    item.dataset.prevDone = wasDone ? "1" : "0";
    item.classList.remove("is-anim", "is-unchecking");
    void item.offsetWidth;
    const button = item.querySelector(".step-goals__toggle");
    if (wasDone) {
      item.classList.add("is-unchecking");
      item.classList.remove("is-done");
      if (button) button.setAttribute("aria-pressed", "false");
    } else {
      item.classList.add("is-done", "is-anim");
      if (button) button.setAttribute("aria-pressed", "true");
    }
    const goals = form.closest("#step-goals");
    const wrap = document.getElementById("step-goals-cta-wrap");
    if (goals) {
      goals.dataset.ctaOpen = wrap?.classList.contains("is-open") ? "1" : "0";
      goals.dataset.ctaWillOpen = goals.querySelectorAll(".step-goals__item.is-done").length > 0 ? "1" : "0";
    }
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    const item = form?.closest?.(".step-goals__item");
    if (!item?.closest?.("#step-goals")) return;
    item.classList.remove("is-busy");
    if (event.detail.successful) return;
    const wasDone = item.dataset.prevDone === "1";
    item.classList.remove("is-anim", "is-unchecking");
    item.classList.toggle("is-done", wasDone);
    const button = item.querySelector(".step-goals__toggle");
    if (button) button.setAttribute("aria-pressed", wasDone ? "true" : "false");
  });

  document.body.addEventListener("htmx:oobBeforeSwap", (event) => {
    const target = event.detail?.target;
    if (target?.id !== "step-goals-cta-wrap") return;
    const goals = document.getElementById("step-goals");
    if (!goals) return;
    const wasOpen = goals.dataset.ctaOpen === "1";
    const willOpen = goals.dataset.ctaWillOpen === "1";
    if (wasOpen && !willOpen) {
      event.detail.shouldSwap = false;
      const wrap = target;
      wrap.classList.remove("is-enter");
      wrap.classList.add("is-leave");
      wrap.classList.remove("is-open");
      window.setTimeout(() => {
        wrap.classList.remove("is-leave");
        const slot = wrap.querySelector(".step-goals__cta-slot");
        if (slot) slot.innerHTML = "";
      }, 420);
    }
  });

  document.body.addEventListener("htmx:oobAfterSwap", () => {
    const goals = document.getElementById("step-goals");
    const wrap = document.getElementById("step-goals-cta-wrap");
    if (!goals || !wrap) return;
    const wasOpen = goals.dataset.ctaOpen === "1";
    wrap.classList.remove("is-enter");
    if (wrap.classList.contains("is-open") && !wasOpen) {
      void wrap.offsetWidth;
      wrap.classList.add("is-enter");
    }
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    const xhr = event.detail.xhr;
    const status = xhr?.status;
    // Flask-WTF / OTP errors come back as 422 HTML partials — swap them so the user sees the message.
    if (status === 422) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
      return;
    }
    const elt = event.detail.elt;
    if (!elt?.matches?.("[data-team-invite-form], .team-invite-form")) return;
    if (xhr && status >= 200 && status < 500) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });

  const normalizeKzPhone = (value) => {
    let digits = String(value || "").replace(/\D/g, "");
    if (digits.startsWith("8") && digits.length >= 11) {
      digits = "7" + digits.slice(1);
    }
    return digits.slice(0, 11);
  };

  document.body.addEventListener("input", (event) => {
    const input = event.target.closest("[data-phone-mask='kz']");
    if (!input) return;
    input.value = normalizeKzPhone(input.value);
  });

  document.body.addEventListener("paste", (event) => {
    const input = event.target.closest("[data-phone-mask='kz']");
    if (!input) return;
    window.setTimeout(() => {
      input.value = normalizeKzPhone(input.value);
    }, 0);
  });

  const feedFilterRow = document.querySelector("[data-feed-filters]");
  const applyFeedFilter = (filter) => {
    if (!feedFilterRow) return;
    feedFilterRow.dataset.activeFilter = filter;
    feedFilterRow.querySelectorAll(".chip").forEach((item) => {
      item.classList.toggle("is-active", item.dataset.filter === filter);
    });
    document.querySelectorAll("#feed-list .activity-card").forEach((card) => {
      const match = filter === "all" || card.dataset.kind === filter;
      card.hidden = !match;
    });
  };

  if (feedFilterRow) {
    feedFilterRow.addEventListener("click", (event) => {
      const chip = event.target.closest("[data-filter]");
      if (!chip || !feedFilterRow.contains(chip)) return;
      applyFeedFilter(chip.dataset.filter || "all");
    });
    applyFeedFilter(feedFilterRow.dataset.activeFilter || "all");
  }

  document.body.addEventListener("toggle", (event) => {
    const wrap = event.target.closest(".activity-comments-wrap");
    if (!wrap || !wrap.open) return;
    window.setTimeout(() => wrap.querySelector(".activity-comment-input")?.focus(), 50);
  }, true);

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (feedFilterRow && event.target?.id === "feed-list") {
      applyFeedFilter(feedFilterRow.dataset.activeFilter || "all");
    }
    const likeBtn = event.target.querySelector?.(".activity-like") || event.target.closest?.(".activity-like");
    if (likeBtn) {
      likeBtn.classList.add("is-pop");
      window.setTimeout(() => likeBtn.classList.remove("is-pop"), 450);
    }
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    const form = event.detail.elt;
    if (form?.classList?.contains("activity-comment-form") && event.detail.successful) {
      const commentInput = form.querySelector(".activity-comment-input");
      if (commentInput) commentInput.value = "";
      const wrap = form.closest(".activity-comments-wrap");
      const count = wrap?.querySelectorAll(".activity-comments__item")?.length || 0;
      const countEl = wrap?.querySelector(".activity-comments-toggle__count");
      if (countEl) countEl.textContent = String(count);
    }
    if (form?.classList?.contains("feed-compose") && event.detail.successful) {
      const bodyInput = form.querySelector(".feed-compose__body");
      const titleInput = form.querySelector('input[name="title"]');
      if (bodyInput) bodyInput.value = "";
      if (titleInput) titleInput.value = "";
      window.closeFeedCompose?.();
    }
  });

  document.querySelectorAll(".role-card input[type='radio']").forEach((radio) => {
    radio.addEventListener("change", () => {
      document.querySelectorAll(".role-card").forEach((card) => card.classList.remove("is-selected"));
      radio.closest(".role-card")?.classList.add("is-selected");
    });
  });

  const avatarInput = document.querySelector("input[name='avatar']");
  const avatarPreview = document.querySelector("#avatar-preview .avatar");
  avatarInput?.addEventListener("change", () => {
    const file = avatarInput.files?.[0];
    if (!file || !avatarPreview) return;
    const url = URL.createObjectURL(file);
    avatarPreview.querySelector(".avatar-letter")?.remove();
    let img = avatarPreview.querySelector(".avatar-img");
    if (!img) {
      img = document.createElement("img");
      img.className = "avatar-img";
      img.alt = "";
      avatarPreview.appendChild(img);
    }
    img.src = url;
  });

  const hideChatEmptyPrompt = () => {
    const prompt = document.getElementById("chat-empty-prompt");
    const scroll = document.getElementById("chat-scroll");
    if (prompt) prompt.classList.add("is-hidden");
    scroll?.classList.remove("is-empty");
  };

  const typewriterGreeting = () => {
    const prompt = document.getElementById("chat-empty-prompt");
    const line = prompt?.querySelector("[data-typewriter-greeting]");
    if (!(line instanceof HTMLElement) || line.dataset.typed === "1") return;
    const text = (prompt?.dataset.greeting || line.textContent || "").trim();
    if (!text) return;
    line.dataset.typed = "1";
    if (prefersReducedMotion()) {
      line.textContent = text;
      return;
    }
    line.textContent = "";
    const caret = document.createElement("span");
    caret.className = "chat-caret";
    caret.setAttribute("aria-hidden", "true");
    line.appendChild(caret);
    const cps = text.length > 48 ? 42 : 34;
    const started = performance.now();
    let frame = 0;
    const tick = (now) => {
      frame = window.requestAnimationFrame(tick);
      const count = Math.min(text.length, Math.floor(((now - started) / 1000) * cps));
      line.textContent = text.slice(0, count);
      line.appendChild(caret);
      if (count >= text.length) {
        window.cancelAnimationFrame(frame);
        caret.remove();
        return;
      }
    };
    frame = window.requestAnimationFrame(tick);
  };

  const chatMessages = document.getElementById("chat-messages");
  const chatScroll = document.getElementById("chat-scroll") || chatMessages;
  const chatForm = document.getElementById("chat-form");
  const chatInput = document.getElementById("chat-input");
  const chatPayload = document.getElementById("chat-message-field");
  const chatSend = document.querySelector(".chat-composer__box .chat-send");
  const chatShell = document.querySelector(".chat-composer-shell");
  const TYPING_CLASS = "chat-typing";

  const escapeHtml = (value) =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const scrollChatToBottom = () => {
    if (!chatScroll) return;
    chatScroll.scrollTop = chatScroll.scrollHeight;
  };

  const removeTyping = () => {
    document.getElementById("chat-typing")?.remove();
    chatMessages?.querySelectorAll(`.${TYPING_CLASS}`).forEach((node) => node.remove());
  };

  const showTyping = () => {
    if (!chatMessages) return;
    removeTyping();
    const node = document.createElement("div");
    node.id = "chat-typing";
    node.className = `chat-msg chat-msg-ai ${TYPING_CLASS}`;
    node.innerHTML =
      '<div class="chat-msg__bubble"><span class="typing-dots" aria-label="Печатает"><span></span><span></span><span></span></span></div>';
    chatMessages.appendChild(node);
    scrollChatToBottom();
  };

  const finishChatRequest = () => {
    removeTyping();
    setChatBusy(false);
    chatInput?.focus();
    scrollChatToBottom();
  };

  const prefersReducedMotion = () =>
    window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true;

  typewriterGreeting();

  const formatStreamHtml = (text) => {
    const parts = text.split(/\n\n+/).map((part) => part.trim()).filter(Boolean);
    if (!parts.length) return "";
    return parts
      .map((part) => `<p>${escapeHtml(part).replace(/\n/g, "<br>")}</p>`)
      .join("");
  };

  const animateRoastCards = (root) => {
    const scope = root?.closest?.("#chat-messages") || root || chatMessages;
    scope?.querySelectorAll("[data-roast-card]").forEach((card) => {
      if (!(card instanceof HTMLElement) || card.dataset.roastAnimated === "1") return;
      card.dataset.roastAnimated = "1";
      card.classList.add("is-animated");
      const bar = card.querySelector(".roast-scorebar");
      if (!(bar instanceof HTMLElement)) return;
      const target = Math.max(0, Math.min(100, Number(bar.dataset.score || 0)));
      const valueEl = bar.querySelector(".roast-scorebar__value");
      bar.style.setProperty("--score", "0");
      const reduced = prefersReducedMotion();
      const start = performance.now();
      const duration = reduced ? 0 : 1100;
      const tick = (now) => {
        const t = duration ? Math.min(1, (now - start) / duration) : 1;
        const eased = 1 - Math.pow(1 - t, 3);
        const current = Math.round(target * eased);
        bar.style.setProperty("--score", String(current));
        if (valueEl) valueEl.textContent = `${current}%`;
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(() => requestAnimationFrame(tick));
    });
  };

  const revealDeferredChat = (anchor) => {
    const root = anchor?.closest("#chat-messages") || chatMessages;
    root?.querySelectorAll("[data-reveal-after-type][hidden]").forEach((node) => {
      node.hidden = false;
      node.classList.add("is-revealed");
    });
    animateRoastCards(root);
  };

  let chatStreaming = false;

  const typewriterBubble = (bubble, onDone) => {
    if (!(bubble instanceof HTMLElement) || bubble.dataset.typed === "1") {
      onDone?.();
      return;
    }
    bubble.dataset.typed = "1";
    const finalHtml = bubble.innerHTML;
    const text = (bubble.innerText || "").replace(/\s+\n/g, "\n").trim();
    if (!text || prefersReducedMotion()) {
      bubble.innerHTML = finalHtml;
      revealDeferredChat(bubble);
      onDone?.();
      return;
    }

    chatStreaming = true;
    bubble.classList.add("is-streaming");
    bubble.innerHTML = "";
    const content = document.createElement("div");
    content.className = "chat-stream-text";
    const caret = document.createElement("span");
    caret.className = "chat-caret";
    caret.setAttribute("aria-hidden", "true");
    bubble.appendChild(content);
    bubble.appendChild(caret);

    const cps = text.length > 500 ? 95 : text.length > 220 ? 72 : 58;
    const started = performance.now();
    let frame = 0;

    const tick = (now) => {
      frame = window.requestAnimationFrame(tick);
      const elapsed = (now - started) / 1000;
      const count = Math.min(text.length, Math.floor(elapsed * cps));
      content.innerHTML = formatStreamHtml(text.slice(0, count));
      if (count >= text.length) {
        window.cancelAnimationFrame(frame);
        caret.remove();
        bubble.classList.remove("is-streaming");
        bubble.innerHTML = finalHtml;
        revealDeferredChat(bubble);
        chatStreaming = false;
        scrollChatToBottom();
        onDone?.();
        return;
      }
      if (count % 8 === 0) scrollChatToBottom();
    };
    frame = window.requestAnimationFrame(tick);
  };

  const isChatHtmxEvent = (event) => event.detail.elt?.id === "chat-form";

  const appendUserMessage = (text) => {
    if (!chatMessages || !text) return;
    const node = document.createElement("div");
    node.className = "chat-msg chat-msg-user";
    node.innerHTML = `<div class="chat-msg__bubble">${escapeHtml(text).replace(/\n/g, "<br>")}</div>`;
    chatMessages.appendChild(node);
    scrollChatToBottom();
  };

  const setPayload = (text) => {
    if (chatPayload) chatPayload.value = text;
  };

  const setChatBusy = (busy) => {
    if (chatSend) chatSend.disabled = busy;
    chatForm?.classList.toggle("is-busy", busy);
    chatShell?.classList.toggle("is-busy", busy);
  };

  const getPendingText = () => (chatForm?.dataset.pendingMessage || chatInput?.value.trim() || "").trim();

  const submitChat = (textOverride) => {
    if (!chatForm || !chatInput) return;
    const text = (textOverride || chatInput.value).trim();
    if (!text || chatForm.classList.contains("is-busy")) return;
    chatInput.value = text;
    chatForm.dataset.pendingMessage = text;
    chatForm.requestSubmit();
  };

  const toggleCompactRoast = (card) => {
    if (!(card instanceof HTMLElement)) return;
    const open = card.classList.toggle("is-open");
    const toggle = card.querySelector(".roast-toggle");
    toggle?.setAttribute("aria-expanded", open ? "true" : "false");
  };

  chatMessages?.addEventListener("click", (event) => {
    const altBtn = event.target.closest(".roast-alt-btn");
    if (altBtn) {
      event.preventDefault();
      const idea = altBtn.dataset.idea?.trim();
      if (!idea) return;
      if (chatForm) chatForm.dataset.forceRoast = "1";
      submitChat(idea);
      return;
    }
    const toggle = event.target.closest(".roast-toggle");
    const card = toggle?.closest("[data-roast-expandable]");
    if (!card || !chatMessages.contains(card)) return;
    event.preventDefault();
    toggleCompactRoast(card);
  });

  chatMessages?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const toggle = event.target.closest?.(".roast-toggle");
    const card = toggle?.closest("[data-roast-expandable]");
    if (!card || !chatMessages.contains(card)) return;
    event.preventDefault();
    toggleCompactRoast(card);
  });

  const chatThreadField = document.getElementById("chat-thread-field");

  chatForm?.addEventListener("htmx:configRequest", (event) => {
    if (event.detail.elt !== chatForm) return;
    const text = getPendingText();
    if (!text) return;
    setPayload(text);
    event.detail.parameters.message = text;
    const threadId = chatThreadField?.value;
    if (threadId) event.detail.parameters.thread_id = threadId;
    const token = chatForm.querySelector('input[name="csrf_token"]')?.value;
    if (token) event.detail.parameters.csrf_token = token;
    if (chatForm.dataset.forceRoast === "1") event.detail.parameters.force_roast = "1";
    if (document.getElementById("chat-via-map")?.checked) event.detail.parameters.via_map = "1";
  });

  const chatLayout = document.getElementById("chat-layout");
  const chatSidebarBackdrop = document.getElementById("chat-sidebar-backdrop");
  const chatHistoryBtn = document.getElementById("chat-history-btn");
  const chatRailFab = document.getElementById("chat-rail-fab");
  const SIDEBAR_COLLAPSE_KEY = "kangaroo_chat_sidebar_collapsed";
  const isChatDesktop = () => window.matchMedia("(min-width: 980px)").matches;

  const syncRailFab = () => {
    if (!chatRailFab) return;
    // Keep in DOM for CSS enter/leave animation; hide only off desktop.
    chatRailFab.hidden = !isChatDesktop();
  };

  const setSidebarCollapsed = (collapsed, { animate = true } = {}) => {
    if (!chatLayout) return;
    const next = Boolean(collapsed) && isChatDesktop();
    if (!animate) chatLayout.classList.add("is-sidebar-anim-off");
    chatLayout.classList.toggle("is-sidebar-collapsed", next);
    try {
      localStorage.setItem(SIDEBAR_COLLAPSE_KEY, next ? "1" : "0");
    } catch (_) {
      /* ignore */
    }
    syncRailFab();
    if (!animate) {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => chatLayout.classList.remove("is-sidebar-anim-off"));
      });
    }
  };

  const setSidebarOpen = (open) => {
    chatLayout?.classList.toggle("is-sidebar-open", open);
    chatHistoryBtn?.setAttribute("aria-expanded", open ? "true" : "false");
  };
  const toggleSidebar = () => setSidebarOpen(!chatLayout?.classList.contains("is-sidebar-open"));
  const closeSidebar = () => setSidebarOpen(false);

  // Desktop: history panel open by default; restore collapse preference
  if (isChatDesktop()) {
    chatLayout?.classList.add("is-sidebar-open");
    try {
      if (localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === "1") {
        setSidebarCollapsed(true, { animate: false });
      }
    } catch (_) {
      /* ignore */
    }
  }
  syncRailFab();

  chatHistoryBtn?.setAttribute("aria-expanded", "false");
  chatHistoryBtn?.addEventListener("click", () => {
    if (isChatDesktop() && chatLayout?.classList.contains("is-sidebar-collapsed")) {
      setSidebarCollapsed(false);
      return;
    }
    toggleSidebar();
  });
  document.getElementById("chat-sidebar-close")?.addEventListener("click", closeSidebar);
  document.getElementById("chat-sidebar-collapse")?.addEventListener("click", () => setSidebarCollapsed(true));
  chatSidebarBackdrop?.addEventListener("click", closeSidebar);
  document.getElementById("chat-sidebar-list")?.addEventListener("click", (event) => {
    if (event.target.closest("[data-chat-delete-open], .chat-thread-delete")) return;
    if (event.target.closest(".chat-thread-item")) closeSidebar();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
  });
  window.matchMedia("(min-width: 980px)").addEventListener("change", (event) => {
    if (!event.matches) {
      chatLayout?.classList.remove("is-sidebar-collapsed");
      syncRailFab();
      return;
    }
    chatLayout?.classList.add("is-sidebar-open");
    try {
      setSidebarCollapsed(localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === "1", { animate: false });
    } catch (_) {
      setSidebarCollapsed(false, { animate: false });
    }
  });

  chatForm?.addEventListener("submit", (event) => {
    const text = getPendingText();
    if (!text) {
      event.preventDefault();
      return;
    }
    if (chatForm.classList.contains("is-busy")) {
      event.preventDefault();
      return;
    }
    chatForm.dataset.pendingMessage = text;
    setPayload(text);
    hideChatEmptyPrompt();
    appendUserMessage(text);
    showTyping();
    chatInput.value = "";
    chatInput.style.height = "auto";
    setChatBusy(true);
  });

  document.body.addEventListener("htmx:beforeSwap", (event) => {
    if (!isChatHtmxEvent(event)) return;
    removeTyping();
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail?.target;
    if (target?.id !== "chat-messages") return;
    const bubble = target.querySelector("[data-typewriter]:not([data-typed])");
    if (bubble) {
      typewriterBubble(bubble, () => finishChatRequest());
      return;
    }
    revealDeferredChat(target);
    if (!chatStreaming) finishChatRequest();
  });

  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (!isChatHtmxEvent(event)) return;
    delete chatForm?.dataset.pendingMessage;
    delete chatForm?.dataset.forceRoast;
    setPayload("");
    if (!event.detail.successful) {
      chatStreaming = false;
      finishChatRequest();
      return;
    }
    if (!chatStreaming && !chatMessages?.querySelector("[data-typewriter]:not([data-typed])")) {
      finishChatRequest();
    }
    const mapToggle = document.getElementById("chat-map-toggle");
    if (mapToggle?.classList.contains("is-suggested") || mapToggle?.classList.contains("is-confirm")) {
      mapToggle.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    if (!isChatHtmxEvent(event)) return;
    const xhr = event.detail.xhr;
    const status = xhr?.status || 0;
    const body = xhr?.responseText?.trim() || "";
    const isGatewayHtml = body.startsWith("<") && (status === 504 || status === 502 || status === 503);
    if (chatMessages) {
      if (isGatewayHtml) {
        chatMessages.insertAdjacentHTML(
          "beforeend",
          '<div class="chat-msg chat-msg-system"><div class="chat-msg__bubble">AI не успел ответить вовремя. Подожди минуту и попробуй ещё раз.</div></div>',
        );
      } else if (body) {
        chatMessages.insertAdjacentHTML("beforeend", body);
      }
    }
    finishChatRequest();
  });

  document.body.addEventListener("htmx:sendError", (event) => {
    if (!isChatHtmxEvent(event)) return;
    finishChatRequest();
  });

  scrollChatToBottom();

  const attachFileInput = document.getElementById("chat-attach-file") || document.getElementById("chat-pitch-file");
  const attachWrap = document.getElementById("chat-attach-wrap");
  const attachBtn = document.getElementById("chat-attach-btn");
  const attachMenu = document.getElementById("chat-attach-menu");

  const closeAttachMenu = () => {
    if (!attachMenu || !attachBtn) return;
    attachMenu.hidden = true;
    attachBtn.setAttribute("aria-expanded", "false");
  };

  const openAttachMenu = () => {
    if (!attachMenu || !attachBtn) return;
    attachMenu.hidden = false;
    attachBtn.setAttribute("aria-expanded", "true");
  };

  attachBtn?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (attachMenu?.hidden) openAttachMenu();
    else closeAttachMenu();
  });

  attachMenu?.addEventListener("click", (event) => {
    const item = event.target.closest("[data-attach-kind]");
    if (!item || !attachFileInput) return;
    event.preventDefault();
    event.stopPropagation();
    const accept = item.getAttribute("data-accept") || "";
    attachFileInput.accept = accept;
    attachFileInput.dataset.attachKind = item.getAttribute("data-attach-kind") || "";
    closeAttachMenu();
    attachFileInput.click();
  });

  document.addEventListener("click", (event) => {
    if (!attachWrap || event.target.closest("#chat-attach-wrap")) return;
    closeAttachMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAttachMenu();
  });

  attachFileInput?.addEventListener("change", async () => {
    const file = attachFileInput.files?.[0];
    const url = attachFileInput.dataset.attachUrl || attachFileInput.dataset.pitchUploadUrl;
    if (!file || !url || !chatMessages) {
      attachFileInput.value = "";
      return;
    }
    const token =
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      chatForm?.querySelector('input[name="csrf_token"]')?.value ||
      "";
    attachWrap?.classList.add("is-busy");
    hideChatEmptyPrompt();
    showTyping();
    setChatBusy(true);
    try {
      const body = new FormData();
      body.set("attach_file", file);
      body.set("pitch_file", file);
      if (token) body.set("csrf_token", token);
      const response = await fetch(url, {
        method: "POST",
        body,
        headers: token ? { "X-CSRFToken": token } : {},
        credentials: "same-origin",
      });
      const html = (await response.text()).trim();
      removeTyping();
      if (html) chatMessages.insertAdjacentHTML("beforeend", html);
      scrollChatToBottom();
    } catch (_err) {
      removeTyping();
      chatMessages.insertAdjacentHTML(
        "beforeend",
        '<div class="chat-msg chat-msg-system"><div class="chat-msg__bubble">Не удалось загрузить файл. Попробуй ещё раз.</div></div>',
      );
      scrollChatToBottom();
    } finally {
      attachFileInput.value = "";
      attachWrap?.classList.remove("is-busy");
      setChatBusy(false);
      finishChatRequest();
    }
  });

  const autosizeTextarea = (el) => {
    if (!(el instanceof HTMLTextAreaElement)) return;
    if (el.classList.contains("chat-input") || el.id === "chat-input") return;
    if (!el.classList.contains("ui-autosize") && !el.classList.contains("chat-step-form__input")) return;
    const min = Number(el.dataset.minHeight || (el.classList.contains("chat-step-form__input") ? 40 : 48));
    const max = Number(el.dataset.maxHeight || (el.classList.contains("chat-step-form__input") ? 120 : 240));
    el.style.height = `${min}px`;
    el.style.height = `${Math.min(Math.max(el.scrollHeight, min), max)}px`;
  };

  document.body.addEventListener("input", (event) => {
    autosizeTextarea(event.target);
  });

  const bootAutosize = () => {
    document.querySelectorAll("textarea.ui-autosize, textarea.chat-step-form__input").forEach(autosizeTextarea);
  };
  bootAutosize();
  document.body.addEventListener("htmx:afterSwap", bootAutosize);

  const setStepCardOpen = (card, open) => {
    if (!card) return;
    const body = card.querySelector("[data-step-card-body]");
    const toggle = card.querySelector(".chat-step-tab");
    card.classList.toggle("is-open", open);
    if (body) body.hidden = !open;
    toggle?.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      const report = card.querySelector(".chat-step-form__input");
      if (report) autosizeTextarea(report);
    }
  };

  document.body.addEventListener("click", (event) => {
    const helpBtn = event.target.closest("[data-map-help]");
    if (helpBtn) {
      event.preventDefault();
      event.stopPropagation();
      const wrap = helpBtn.closest(".chat-map-toggle__help");
      if (!wrap) return;
      const open = !wrap.classList.contains("is-open");
      document.querySelectorAll(".chat-map-toggle__help.is-open").forEach((el) => {
        if (el === wrap) return;
        el.classList.remove("is-open");
        el.querySelector("[data-map-help]")?.setAttribute("aria-expanded", "false");
      });
      wrap.classList.toggle("is-open", open);
      helpBtn.setAttribute("aria-expanded", open ? "true" : "false");
      return;
    }
    if (!event.target.closest(".chat-map-toggle__help")) {
      document.querySelectorAll(".chat-map-toggle__help.is-open").forEach((el) => {
        el.classList.remove("is-open");
        el.querySelector("[data-map-help]")?.setAttribute("aria-expanded", "false");
      });
    }

    const toggle = event.target.closest("[data-step-card-toggle]");
    if (toggle) {
      const card = toggle.closest("[data-step-card]");
      if (!card) return;
      event.preventDefault();
      setStepCardOpen(card, !card.classList.contains("is-open"));
      return;
    }
    const openRail = document.querySelector(".chat-step-rail.is-open");
    if (openRail && !event.target.closest(".chat-step-rail")) {
      setStepCardOpen(openRail, false);
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    const target = event.detail?.target;
    if (!target || !["chat-step-card", "chat-too-card"].includes(target.id)) return;
    const rail = document.getElementById(target.id);
    // After submit: open only if server marked the panel open; alerts stay closed and pulse.
    if (rail?.classList.contains("is-open")) {
      setStepCardOpen(rail, true);
    }
  });

  chatInput?.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = `${Math.min(chatInput.scrollHeight, 120)}px`;
  });
  chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitChat();
    }
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  }

  const activeProfileTab = document.querySelector(".profile-tab.is-active");
  activeProfileTab?.scrollIntoView({ inline: "center", block: "nearest", behavior: "auto" });

  const settingsPanel = document.getElementById("profile-settings");
  if (settingsPanel && (window.location.hash === "#profile-settings" || new URLSearchParams(window.location.search).get("tab") === "settings")) {
    window.requestAnimationFrame(() => {
      settingsPanel.scrollIntoView({ block: "start", behavior: "smooth" });
    });
  }

  document.querySelectorAll("[data-lang-select]").forEach((root) => {
    const trigger = root.querySelector(".lang-select__trigger");
    const menu = root.querySelector(".lang-select__menu");
    if (!trigger || !menu) return;

    const options = () => Array.from(menu.querySelectorAll(".lang-select__option"));

    const setOpen = (open) => {
      menu.hidden = !open;
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
      root.classList.toggle("is-open", open);
      if (open) {
        const active = menu.querySelector(".lang-select__option.is-active") || options()[0];
        active?.focus();
      }
    };

    const moveFocus = (delta) => {
      const items = options();
      if (!items.length) return;
      const idx = items.indexOf(document.activeElement);
      const next = items[(idx + delta + items.length) % items.length];
      next?.focus();
    };

    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setOpen(menu.hidden);
    });

    trigger.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setOpen(true);
      }
    });

    menu.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        trigger.focus();
        return;
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveFocus(1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        moveFocus(-1);
      } else if (event.key === "Home") {
        event.preventDefault();
        options()[0]?.focus();
      } else if (event.key === "End") {
        event.preventDefault();
        options().at(-1)?.focus();
      }
    });

    menu.addEventListener("click", (event) => {
      const option = event.target.closest(".lang-select__option");
      if (!option) return;
      const form = option.closest("form");
      if (!form) return;
      event.preventDefault();
      setOpen(false);
      if (typeof form.requestSubmit === "function") {
        form.requestSubmit(option);
      } else {
        form.submit();
      }
    });

    document.addEventListener("click", (event) => {
      if (!root.contains(event.target)) setOpen(false);
    });
  });

  document.querySelectorAll("[data-role-select]").forEach((root) => {
    const trigger = root.querySelector(".role-select__trigger");
    const menu = root.querySelector(".role-select__menu");
    const input = root.querySelector("[data-role-select-input]");
    const labelEl = root.querySelector("[data-role-select-label]");
    const iconEl = root.querySelector("[data-role-select-icon]");
    if (!trigger || !menu || !input) return;

    const setOpen = (open) => {
      menu.hidden = !open;
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
      root.classList.toggle("is-open", open);
    };

    const selectOption = (option) => {
      if (!option) return;
      const id = option.getAttribute("data-role-id");
      const label = option.getAttribute("data-role-label") || "";
      const optionIcon = option.querySelector(".role-select__icon");
      if (id) input.value = id;
      if (labelEl) labelEl.textContent = label;
      if (iconEl && optionIcon) iconEl.innerHTML = optionIcon.innerHTML;
      menu.querySelectorAll(".role-select__option").forEach((btn) => {
        const active = btn === option;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
        const check = btn.querySelector(".role-select__check");
        if (check) check.textContent = active ? "✓" : "";
      });
      setOpen(false);
    };

    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      setOpen(menu.hidden);
    });

    menu.querySelectorAll(".role-select__option").forEach((option) => {
      option.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        selectOption(option);
      });
    });

    document.addEventListener("click", (event) => {
      if (!root.contains(event.target)) setOpen(false);
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setOpen(false);
    });
  });

  document.querySelectorAll(".theme-toggle").forEach((root) => {
    root.querySelectorAll(".theme-toggle__btn").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        const form = btn.closest("form");
        const theme = btn.getAttribute("data-theme-value") || form?.querySelector('input[name="theme"]')?.value;
        if (!form || !theme || root.classList.contains("is-animating")) return;
        if (root.classList.contains(`is-${theme}`) && btn.classList.contains("is-active")) return;

        event.preventDefault();
        root.classList.add("is-animating");
        root.classList.toggle("is-light", theme === "light");
        root.classList.toggle("is-dark", theme === "dark");
        root.querySelectorAll(".theme-toggle__btn").forEach((other) => {
          const active = other === btn;
          other.classList.toggle("is-active", active);
          other.setAttribute("aria-pressed", active ? "true" : "false");
        });

        const html = document.documentElement;
        html.classList.add("theme-animating");
        html.setAttribute("data-theme", theme);
        const themeMeta = document.querySelector('meta[name="theme-color"]');
        if (themeMeta) themeMeta.setAttribute("content", theme === "light" ? "#f5f3eb" : "#050505");

        window.setTimeout(() => {
          form.submit();
        }, 360);
      });
    });
  });

  const phoneModal = document.querySelector("[data-phone-modal]");
  if (phoneModal) {
    const wrap = document.getElementById("phone-change-wrap");
    const initialPhoneFormHtml = wrap ? wrap.innerHTML : "";

    const openPhoneModal = () => {
      if (wrap?.querySelector(".phone-change-success") && initialPhoneFormHtml) {
        wrap.innerHTML = initialPhoneFormHtml;
      }
      if (typeof phoneModal.showModal === "function") phoneModal.showModal();
    };
    const closePhoneModal = () => {
      if (typeof phoneModal.close === "function") phoneModal.close();
    };

    document.querySelectorAll("[data-phone-modal-open]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        openPhoneModal();
      });
    });
    document.querySelectorAll("[data-phone-modal-close]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        closePhoneModal();
      });
    });
    phoneModal.addEventListener("click", (event) => {
      if (event.target === phoneModal) closePhoneModal();
    });
    document.body.addEventListener("phoneChanged", () => {
      window.setTimeout(closePhoneModal, 900);
    });
  }

  const avatarRemoveModal = document.querySelector("[data-avatar-remove-modal]");
  if (avatarRemoveModal) {
    const removeInput = document.getElementById("remove-avatar-input");
    const profileForm = document.getElementById("profile-edit-form");
    const openAvatarRemoveModal = () => {
      if (typeof avatarRemoveModal.showModal === "function") avatarRemoveModal.showModal();
    };
    const closeAvatarRemoveModal = () => {
      if (typeof avatarRemoveModal.close === "function") avatarRemoveModal.close();
    };

    document.querySelectorAll("[data-avatar-remove-open]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        openAvatarRemoveModal();
      });
    });
    document.querySelectorAll("[data-avatar-remove-close]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        closeAvatarRemoveModal();
      });
    });
    avatarRemoveModal.addEventListener("click", (event) => {
      if (event.target === avatarRemoveModal) closeAvatarRemoveModal();
    });
    document.querySelectorAll("[data-avatar-remove-confirm]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        if (removeInput) removeInput.checked = true;
        closeAvatarRemoveModal();
        if (profileForm?.requestSubmit) profileForm.requestSubmit();
        else profileForm?.submit();
      });
    });
  }

  const teamInviteModal = document.querySelector("[data-team-invite-modal]");
  if (teamInviteModal) {
    let pendingInviteForm = null;
    const copyEl = teamInviteModal.querySelector("[data-team-invite-copy]");
    const openTeamInviteModal = (form, trigger) => {
      pendingInviteForm = form;
      const name = trigger?.getAttribute("data-invitee-name") || "участника";
      const startup = trigger?.getAttribute("data-startup-name") || "твой проект";
      if (copyEl) {
        copyEl.textContent = `Пригласить ${name} в команду «${startup}»? Человек получит уведомление и сможет принять или отклонить.`;
      }
      if (typeof teamInviteModal.showModal === "function") teamInviteModal.showModal();
    };
    const closeTeamInviteModal = () => {
      if (typeof teamInviteModal.close === "function") teamInviteModal.close();
      pendingInviteForm = null;
    };

    document.body.addEventListener("click", (event) => {
      const openBtn = event.target.closest("[data-team-invite-open]");
      if (!openBtn) return;
      event.preventDefault();
      const form = openBtn.closest("[data-team-invite-form], .team-invite-form");
      if (form) openTeamInviteModal(form, openBtn);
    });

    document.querySelectorAll("[data-team-invite-close]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        closeTeamInviteModal();
      });
    });
    teamInviteModal.addEventListener("click", (event) => {
      if (event.target === teamInviteModal) closeTeamInviteModal();
    });
    document.querySelectorAll("[data-team-invite-confirm]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        const form = pendingInviteForm;
        closeTeamInviteModal();
        if (!form) return;
        const target = form.getAttribute("hx-target") || form.dataset.hxTarget;
        const url = form.getAttribute("hx-post") || form.getAttribute("action");
        if (window.htmx && url) {
          window.htmx.ajax("POST", url, {
            source: form,
            target: target || "this",
            swap: form.getAttribute("hx-swap") || "innerHTML",
            values: {
              csrf_token: form.querySelector('input[name="csrf_token"]')?.value || "",
              activity_id: form.querySelector('input[name="activity_id"]')?.value || "",
            },
          });
          return;
        }
        const submitBtn = form.querySelector("[data-team-invite-submit]");
        if (submitBtn) submitBtn.click();
        else if (form.requestSubmit) form.requestSubmit();
        else form.submit();
      });
    });

    document.body.addEventListener("htmx:responseError", (event) => {
      const form = event.detail?.elt;
      if (!form?.matches?.("[data-team-invite-form], .team-invite-form")) return;
      showAppToast("Не удалось отправить приглашение. Попробуй ещё раз.", "error");
    });
  }

  const chatDeleteModal = document.querySelector("[data-chat-delete-modal]");
  if (chatDeleteModal) {
    const copyEl = chatDeleteModal.querySelector("[data-chat-delete-copy]");
    const threadField = chatDeleteModal.querySelector("[data-chat-delete-thread-id]");
    const openChatDeleteModal = (threadId, title, hasStartup) => {
      if (threadField) threadField.value = threadId || "";
      if (copyEl) {
        const label = title || "этот проект";
        copyEl.textContent = hasStartup
          ? `Удалить «${label}»? Чат, карта прогресса, файлы и все шаги будут стёрты без восстановления.`
          : `Удалить «${label}»? Чат и прожарка будут стёрты без восстановления. Слот идеи освободится.`;
      }
      if (typeof chatDeleteModal.showModal === "function") chatDeleteModal.showModal();
    };
    const closeChatDeleteModal = () => {
      if (typeof chatDeleteModal.close === "function") chatDeleteModal.close();
    };

    document.body.addEventListener("click", (event) => {
      const openBtn = event.target.closest("[data-chat-delete-open], .chat-thread-delete");
      if (!openBtn) return;
      event.preventDefault();
      event.stopPropagation();
      openChatDeleteModal(
        openBtn.getAttribute("data-thread-id"),
        openBtn.getAttribute("data-thread-title"),
        openBtn.dataset.hasStartup === "1",
      );
    });

    document.querySelectorAll("[data-chat-delete-close]").forEach((btn) => {
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        closeChatDeleteModal();
      });
    });
    chatDeleteModal.addEventListener("click", (event) => {
      if (event.target === chatDeleteModal) closeChatDeleteModal();
    });
  }

  document.body.addEventListener("click", (event) => {
    const cancelBtn = event.target.closest("[data-chat-delete-cancel]");
    if (!cancelBtn) return;
    event.preventDefault();
    const card = cancelBtn.closest(".chat-delete-confirm");
    card?.closest(".chat-msg")?.remove();
    card?.previousElementSibling?.remove();
    const threadId = cancelBtn.getAttribute("data-thread-id");
    const body = new URLSearchParams();
    body.set("csrf_token", csrf || "");
    fetch("/ai/delete/cancel", { method: "POST", body, credentials: "same-origin" }).catch(() => {});
  });

  const syncChatOnlineStatus = () => {
    const el = document.getElementById("chat-online-status");
    if (!el) return;
    const online = navigator.onLine !== false;
    el.classList.toggle("is-online", online);
    el.classList.toggle("is-offline", !online);
    const label = online ? "Сейчас онлайн" : "Сейчас оффлайн";
    el.setAttribute("aria-label", label);
    el.setAttribute("data-tooltip", label);
  };
  syncChatOnlineStatus();
  window.addEventListener("online", syncChatOnlineStatus);
  window.addEventListener("offline", syncChatOnlineStatus);

  // PWA install prompt + banner dismiss slide-off
  // NOTE: .card { display:block } overrides bare [hidden] — keep .card[hidden] { display:none !important }
  const dismissBannerSlide = (banner, storageKey) => {
    if (!banner || banner.classList.contains("is-dismissing")) return;
    if (storageKey) {
      try {
        localStorage.setItem(storageKey, "1");
      } catch (_) {
        /* private mode */
      }
    }
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      banner.hidden = true;
      banner.classList.remove("is-dismissing");
      banner.removeEventListener("transitionend", onEnd);
    };
    const onEnd = (event) => {
      if (event.target !== banner) return;
      finish();
    };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      finish();
      return;
    }
    banner.classList.add("is-dismissing");
    banner.addEventListener("transitionend", onEnd);
    window.setTimeout(finish, 420);
  };

  let deferredInstall = null;
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    deferredInstall = event;
    const banner = document.getElementById("pwa-install");
    if (!banner) return;
    try {
      if (localStorage.getItem("kangaroo_install_dismissed") === "1") return;
    } catch (_) {
      /* continue */
    }
    banner.hidden = false;
  });
  document.getElementById("pwa-install-btn")?.addEventListener("click", async () => {
    if (!deferredInstall) return;
    deferredInstall.prompt();
    await deferredInstall.userChoice.catch(() => null);
    deferredInstall = null;
    dismissBannerSlide(document.getElementById("pwa-install"), "kangaroo_install_dismissed");
  });
  document.addEventListener("click", (event) => {
    const btn = event.target.closest?.("#push-dismiss-btn, #pwa-install-dismiss");
    if (!btn) return;
    event.preventDefault();
    if (btn.id === "push-dismiss-btn") {
      dismissBannerSlide(document.getElementById("push-optin"), "kangaroo_push_asked");
      return;
    }
    dismissBannerSlide(document.getElementById("pwa-install"), "kangaroo_install_dismissed");
  });
  window.kangarooDismissBanner = dismissBannerSlide;
});
