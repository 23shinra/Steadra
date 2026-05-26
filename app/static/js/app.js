document.addEventListener("DOMContentLoaded", () => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content");
  document.body.addEventListener("htmx:configRequest", (event) => {
    if (csrf) event.detail.headers["X-CSRFToken"] = csrf;
  });

  document.body.addEventListener("input", (event) => {
    const input = event.target.closest("[data-phone-mask='kz']");
    if (!input) return;

    input.value = input.value.replace(/\D/g, "").slice(0, 11);
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
      form.querySelector(".activity-comment-input")?.value = "";
      const wrap = form.closest(".activity-comments-wrap");
      const count = wrap?.querySelectorAll(".activity-comments__item")?.length || 0;
      const countEl = wrap?.querySelector(".activity-comments-toggle__count");
      if (countEl) countEl.textContent = String(count);
    }
    if (form?.classList?.contains("feed-compose") && event.detail.successful) {
      form.querySelector(".feed-compose__body")?.value = "";
      form.querySelector('input[name="title"]')?.value = "";
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

  const chatMessages = document.getElementById("chat-messages");
  const chatForm = document.getElementById("chat-form");
  const chatInput = chatForm?.querySelector(".chat-input");
  const chatPayload = document.getElementById("chat-message-field");
  const chatSend = chatForm?.querySelector(".chat-send");
  const TYPING_CLASS = "chat-typing";

  const escapeHtml = (value) =>
    value
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const scrollChatToBottom = () => {
    if (!chatMessages) return;
    chatMessages.scrollTop = chatMessages.scrollHeight;
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

  chatMessages?.addEventListener("click", (event) => {
    const altBtn = event.target.closest(".roast-alt-btn");
    if (!altBtn) return;
    event.preventDefault();
    const idea = altBtn.dataset.idea?.trim();
    if (!idea) return;
    if (chatForm) chatForm.dataset.forceRoast = "1";
    submitChat(idea);
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
  const setSidebarOpen = (open) => {
    chatLayout?.classList.toggle("is-sidebar-open", open);
    chatHistoryBtn?.setAttribute("aria-expanded", open ? "true" : "false");
  };
  const toggleSidebar = () => setSidebarOpen(!chatLayout?.classList.contains("is-sidebar-open"));
  const closeSidebar = () => setSidebarOpen(false);

  chatHistoryBtn?.setAttribute("aria-expanded", "false");
  chatHistoryBtn?.addEventListener("click", toggleSidebar);
  document.getElementById("chat-sidebar-close")?.addEventListener("click", closeSidebar);
  chatSidebarBackdrop?.addEventListener("click", closeSidebar);
  document.getElementById("chat-sidebar-list")?.addEventListener("click", (event) => {
    if (event.target.closest(".chat-thread-item")) closeSidebar();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
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

  document.body.addEventListener("htmx:afterRequest", (event) => {
    if (!isChatHtmxEvent(event)) return;
    delete chatForm?.dataset.pendingMessage;
    delete chatForm?.dataset.forceRoast;
    setPayload("");
    finishChatRequest();
    const mapToggle = document.getElementById("chat-map-toggle");
    if (mapToggle?.classList.contains("is-suggested") || mapToggle?.classList.contains("is-confirm")) {
      mapToggle.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    if (!isChatHtmxEvent(event)) return;
    const body = event.detail.xhr?.responseText?.trim();
    if (body && chatMessages) chatMessages.insertAdjacentHTML("beforeend", body);
    finishChatRequest();
  });

  document.body.addEventListener("htmx:sendError", (event) => {
    if (!isChatHtmxEvent(event)) return;
    finishChatRequest();
  });

  scrollChatToBottom();

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
});
