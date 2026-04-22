(() => {
  // CSRF для HTMX (Flask-WTF)
  const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content");
  document.body.addEventListener("htmx:configRequest", (evt) => {
    if (!csrf) return;
    evt.detail.headers["X-CSRFToken"] = csrf;
  });

  // Держим активную вкладку внизу синхронно с URL (HTMX меняет только контент)
  const setActiveTabFromPath = (path) => {
    const m = String(path || "").match(/\/ui\/([a-z]+)/i);
    const tab = (m?.[1] || "feed").toLowerCase();
    document.querySelectorAll(".tabbar .tab").forEach((a) => {
      const href = a.getAttribute("href") || "";
      const t = tab === "ai" ? "chat" : tab;
      const isActive = href.toLowerCase().includes(`/ui/${t}`);
      a.classList.toggle("is-active", isActive);
    });
  };
  setActiveTabFromPath(window.location.pathname);
  document.body.addEventListener("htmx:pushedIntoHistory", (evt) => {
    setActiveTabFromPath(evt.detail?.path || window.location.pathname);
  });
  document.body.addEventListener("htmx:afterOnLoad", (evt) => {
    setActiveTabFromPath(evt.detail?.pathInfo?.requestPath || window.location.pathname);
  });

  // Телефон: префикс +7 и простая маска
  const formatRuPhone = (value) => {
    const digits = String(value || "").replace(/\D/g, "");
    let d = digits;
    if (!d) return "+7 ";
    if (d[0] === "8") d = "7" + d.slice(1);
    if (d[0] !== "7") d = "7" + d;
    d = d.slice(0, 11);

    const a = d.slice(1, 4);
    const b = d.slice(4, 7);
    const c = d.slice(7, 9);
    const e = d.slice(9, 11);

    let out = "+7";
    if (a) out += ` (${a}`;
    if (a && a.length === 3) out += ")";
    if (b) out += ` ${b}`;
    if (c) out += `-${c}`;
    if (e) out += `-${e}`;
    if (!a) out += " ";
    return out;
  };

  const bindPhoneMask = (root = document) => {
    const input = root.querySelector?.("input.js-phone");
    if (!input || input.dataset.maskBound === "1") return;
    input.dataset.maskBound = "1";

    const ensurePrefix = () => {
      if (!input.value) input.value = "+7 ";
      if (!input.value.startsWith("+7")) input.value = formatRuPhone(input.value);
    };

    input.addEventListener("focus", () => {
      ensurePrefix();
      // поставить каретку в конец
      try {
        input.setSelectionRange(input.value.length, input.value.length);
      } catch {}
    });

    input.addEventListener("input", () => {
      const prev = input.value;
      input.value = formatRuPhone(prev);
    });

    ensurePrefix();
  };

  bindPhoneMask(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => bindPhoneMask(evt.target));

  // Roadmap: детали этапа + быстрые действия (страница чата)
  const initRoadmapChat = (root = document) => {
    const details = root.querySelector?.("#step-details");
    if (details && details.dataset.bound === "1") return;
    if (details) details.dataset.bound = "1";

    const setDetails = (btn) => {
      if (!btn || !details) return;
      details.querySelector(".details__title").textContent = btn.dataset.title || "Этап";
      details.querySelector(".details__note").textContent = btn.dataset.note || "";
      details.querySelector(".details__body").textContent = btn.dataset.detail || "";
      root.querySelectorAll(".js-step").forEach((b) => b.classList.remove("is-selected"));
      btn.classList.add("is-selected");

      // Обновить краткий заголовок roadmap (если есть)
      const titleEl = root.querySelector?.(".js-roadmap-activeTitle");
      if (titleEl) titleEl.textContent = btn.dataset.title || "Этап";
    };

    root.querySelectorAll?.(".js-step")?.forEach((btn) => {
      btn.addEventListener("mouseenter", () => setDetails(btn));
      btn.addEventListener("focus", () => setDetails(btn));
      btn.addEventListener("click", () => setDetails(btn));
    });

    const active = root.querySelector?.(".js-step.step--active") || root.querySelector?.(".js-step");
    if (active) setDetails(active);

    // Счётчик прогресса (завершённые + активный) + визуальный progress bar
    const progressEl = root.querySelector?.(".js-roadmap-progress");
    const totalSteps = root.querySelectorAll?.(".js-step")?.length || 0;
    const doneSteps = root.querySelectorAll?.(".js-step.step--completed")?.length || 0;
    const hasActiveStep = root.querySelector?.(".js-step.step--active") ? 1 : 0;
    const currentStep = Math.min(totalSteps, doneSteps + hasActiveStep);
    const totalForRatio = totalSteps || 10;
    if (progressEl) {
      progressEl.textContent = `${currentStep}/${totalForRatio}`;
    }
    const progressBarFill = root.querySelector?.(".js-roadmap-progressBar > span");
    if (progressBarFill) {
      const pct = Math.round((currentStep / totalForRatio) * 100);
      progressBarFill.style.setProperty("--p", `${pct}%`);
    }

    root.querySelectorAll?.(".js-quick")?.forEach((b) => {
      b.addEventListener("click", () => {
        const q = b.dataset.q || "";
        const input = root.querySelector?.(".js-chat-input");
        if (!input) return;
        input.value = q;
        input.focus();
      });
    });
  };

  initRoadmapChat(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initRoadmapChat(evt.target));

  // Чат: локальная отправка + макет ответа AI (без бэкенда)
  const initChatComposer = (root = document) => {
    const form = root.querySelector?.(".js-chat-composer");
    const list = root.querySelector?.("#ai-messages");
    const input = root.querySelector?.(".js-chat-input");
    if (!form || !list || !input || form.dataset.bound === "1") return;
    form.dataset.bound = "1";

    // Snap scroll: instant jump to bottom. We rely on message fade-in
    // (CSS keyframe) for perceived smoothness. Smooth-scroll would stack
    // animations when multiple messages arrive within <1s.
    const scrollToBottom = () => {
      list.scrollTop = list.scrollHeight;
    };

    const appendMsg = (who, text) => {
      const wrap = document.createElement("div");
      wrap.className = `msg msg--${who}`;
      const bubble = document.createElement("div");
      bubble.className = "msg__bubble";
      bubble.textContent = text;
      wrap.appendChild(bubble);
      list.appendChild(wrap);
      scrollToBottom();
    };

    const showTyping = () => {
      const wrap = document.createElement("div");
      wrap.className = "msg msg--ai js-typing";
      wrap.innerHTML =
        '<div class="msg__bubble msg__bubble--typing"><span></span><span></span><span></span></div>';
      list.appendChild(wrap);
      scrollToBottom();
      return wrap;
    };
    const hideTyping = () => {
      list.querySelectorAll(".js-typing").forEach((n) => n.remove());
    };

    const mockReply = (q) => {
      const t = String(q || "").toLowerCase();
      if (t.includes("7") && t.includes("дней")) {
        return "План на 7 дней: 1) 5 интервью + фиксация инсайтов. 2) Оффер (3 версии) + выбор 1. 3) Лендинг (1 экран) + форма. 4) 2 канала (email/LinkedIn) + 20 лидов. 5) 3 демо-звонка. 6) 1 платный пилот. 7) Итоги + следующий спринт.";
      }
      if (t.includes("ошибк")) {
        return "Частые ошибки: интервью превращают в питч, нет фиксации инсайтов, слишком широкий ICP, запускают каналы без оффера, нет быстрых итераций (1–2 дня).";
      }
      if (t.includes("закрыть") || t.includes("этап")) {
        return "Чтобы закрыть этап: зафиксируй критерий done, собери 5–7 интервью, сформулируй ICP в 1 абзац, и проверь оффер на 3–5 реальных разговоров.";
      }
      return "Топ-3 шага: 1) 5 интервью по ICP. 2) Оффер в 1 строку + proof. 3) Запуск 2 каналов с короткими итерациями и измерением CPL/CR.";
    };

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = String(input.value || "").trim();
      if (!text) return;
      appendMsg("user", text);
      input.value = "";

      showTyping();
      const delay = 700 + Math.random() * 500;
      window.setTimeout(() => {
        hideTyping();
        appendMsg("ai", mockReply(text));
      }, delay);
    });
  };

  initChatComposer(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initChatComposer(evt.target));

  // Roadmap: свернуть/развернуть, чтобы чат был ближе
  const initRoadmapCollapse = (root = document) => {
    const wrap = root.querySelector?.(".js-roadmap");
    const toggle = root.querySelector?.(".js-roadmap-toggle");
    if (!wrap || !toggle || toggle.dataset.bound === "1") return;
    toggle.dataset.bound = "1";

    const set = (collapsed) => {
      wrap.classList.toggle("is-collapsed", collapsed);
      wrap.dataset.collapsed = collapsed ? "1" : "0";
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      const grid = wrap.querySelector?.(".roadmap__grid");
      if (grid) grid.setAttribute("aria-hidden", collapsed ? "true" : "false");
    };

    set(wrap.dataset.collapsed !== "0");
    toggle.addEventListener("click", () => set(!(wrap.dataset.collapsed === "1")));
  };

  initRoadmapCollapse(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initRoadmapCollapse(evt.target));

  // Лента: фильтры + сортировка (мок на клиенте)
  const initFeedTimeline = (root = document) => {
    const wrap = root.querySelector?.(".js-feed");
    if (!wrap || wrap.dataset.bound === "1") return;
    wrap.dataset.bound = "1";

    const empty = root.querySelector?.(".js-feed-empty");
    const filterButtons = root.querySelectorAll?.(".js-feed-filter") || [];
    const sortButtons = root.querySelectorAll?.(".js-feed-sort") || [];
    const sortToggle = root.querySelector?.(".js-feed-sort-toggle");
    const sortPanel = root.querySelector?.(".feedSortMenu__panel");
    const sortLabel = root.querySelector?.(".js-feed-sort-label");

    const items = () => Array.from(wrap.querySelectorAll(".js-feed-item"));

    const setActivePill = (value) => {
      filterButtons.forEach((b) => b.classList.toggle("is-active", b.dataset.filter === value));
    };
    const setActiveSort = (value) => {
      sortButtons.forEach((b) => b.classList.toggle("is-active", b.dataset.sort === value));
    };
    const setSortLabel = (value) => {
      if (!sortLabel) return;
      sortLabel.textContent = value === "top" ? "Топ по очкам" : "Сначала новые";
    };
    const setSortOpen = (open) => {
      if (!sortToggle || !sortPanel) return;
      sortToggle.setAttribute("aria-expanded", open ? "true" : "false");
      sortPanel.hidden = !open;
    };
    const closeSortMenu = () => {
      setSortOpen(false);
      try {
        sortToggle?.blur?.();
        document.activeElement?.blur?.();
      } catch {}
    };

    // FLIP: record first positions → run mutation → record last → animate invert.
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const flip = (mutate) => {
      if (reduceMotion || typeof Element.prototype.animate !== "function") {
        mutate();
        return;
      }
      const all = items();
      const first = new Map();
      all.forEach((n) => {
        first.set(n, n.getBoundingClientRect());
      });

      mutate();

      const last = new Map();
      all.forEach((n) => {
        last.set(n, n.getBoundingClientRect());
      });

      all.forEach((n) => {
        if (n.hidden) return;
        const f = first.get(n);
        const l = last.get(n);
        if (!f || !l) return;
        const dx = f.left - l.left;
        const dy = f.top - l.top;
        if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
        n.animate(
          [
            { transform: `translate(${dx}px, ${dy}px)` },
            { transform: "translate(0, 0)" },
          ],
          {
            duration: 360,
            easing: "cubic-bezier(.2,.8,.2,1)",
            fill: "both",
          }
        );
      });
    };

    const applyFilter = (value) => {
      flip(() => {
        wrap.dataset.filter = value;
        setActivePill(value);

        let shown = 0;
        items().forEach((it) => {
          const type = (it.dataset.type || "").toLowerCase();
          const tags = (it.dataset.tags || "").toLowerCase();
          const ok =
            value === "all" ||
            type === value ||
            (value === "interview" && tags.includes("interview")) ||
            (value === "mvp" && tags.includes("mvp"));
          it.hidden = !ok;
          if (ok) shown += 1;
        });

        if (empty) empty.hidden = shown !== 0;
      });
    };

    const applySort = (value) => {
      flip(() => {
        wrap.dataset.sort = value;
        setActiveSort(value);
        setSortLabel(value);
        const list = items();
        const visible = list.filter((n) => !n.hidden);

        const getXp = (n) => Number(n.dataset.xp || 0);
        const getTs = (n) => Number(n.dataset.ts || 0);

        visible.sort((a, b) => {
          if (value === "top") return getXp(b) - getXp(a) || getTs(b) - getTs(a);
          return getTs(b) - getTs(a) || getXp(b) - getXp(a);
        });

        visible.forEach((n) => wrap.appendChild(n));
      });
    };

    filterButtons.forEach((b) => {
      b.addEventListener("click", () => {
        applyFilter(b.dataset.filter || "all");
        const activeSort = wrap.dataset.sort || "latest";
        applySort(activeSort);
      });
    });

    sortButtons.forEach((b) => {
      b.addEventListener("click", () => {
        applySort(b.dataset.sort || "latest");
        closeSortMenu();
      });
    });

    sortToggle?.addEventListener("click", () => {
      const isOpen = sortToggle.getAttribute("aria-expanded") === "true";
      setSortOpen(!isOpen);
    });
    document.addEventListener("click", (e) => {
      if (!sortToggle || !sortPanel) return;
      const t = e.target;
      if (sortToggle.contains(t) || sortPanel.contains(t)) return;
      closeSortMenu();
    });

    // initial
    applyFilter(wrap.dataset.filter || "all");
    applySort(wrap.dataset.sort || "latest");
    closeSortMenu();
  };

  initFeedTimeline(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initFeedTimeline(evt.target));

  // System reveal on scroll (IntersectionObserver + stagger)
  const initReveal = (root = document) => {
    const scope = root.querySelector?.("#app-content") || root;

    const isExcluded = (el) =>
      !!(
        el.closest?.(".feedSortMenu") ||
        el.closest?.(".feedSortMenu__panel") ||
        el.closest?.(".tabbar") ||
        el.closest?.(".topbar")
      );

    // Candidate blocks (auto) + any explicit wrappers (data-reveal)
    const selector =
      "[data-reveal], .section__title, .card, .timelineItem, .leaderRow, .pod, .step, .skill";
    const els = Array.from(scope.querySelectorAll(selector)).filter((el) => !isExcluded(el));

    // mark + assign stagger delays within common list containers
    const groupSelectors = [".cards", ".bento", ".leaderRows", ".podium", ".roadmap__list", ".badgeGrid", ".aiReco__grid"];

    const computeIndex = (el) => {
      for (const gs of groupSelectors) {
        const wrap = el.closest?.(gs);
        if (!wrap) continue;
        const items = Array.from(wrap.children).filter((c) => c.nodeType === 1);
        const idx = items.indexOf(el);
        if (idx >= 0) return idx;
      }
      return -1;
    };

    els.forEach((el) => {
      if (el.dataset.revealBound === "1") return;
      el.dataset.revealBound = "1";
      el.classList.add("reveal");

      // direction / duration / once
      el.dataset.revealDir = el.dataset.revealDir || "up";
      if (!el.dataset.revealOnce) el.dataset.revealOnce = "1";

      // stagger unless author specified delay
      const hasDelay = el.style?.getPropertyValue?.("--reveal-delay");
      if (!hasDelay) {
        const idx = computeIndex(el);
        if (idx >= 0) el.style.setProperty("--reveal-delay", `${Math.min(idx, 12) * 60}ms`);
      }
    });

    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    if (reduceMotion) {
      els.forEach((el) => el.classList.add("is-in"));
      return;
    }

    const io =
      initReveal._io ||
      (initReveal._io = new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            const el = e.target;
            if (!e.isIntersecting) return;
            el.classList.add("is-in");
            const once = el.dataset.revealOnce !== "0";
            if (once) initReveal._io.unobserve(el);
          });
        },
        { threshold: 0.14, rootMargin: "0px 0px -10% 0px" }
      ));

    els.forEach((el) => {
      if (el.classList.contains("is-in")) return;
      io.observe(el);
    });
  };

  initReveal(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initReveal(evt.target));

  // Counter-up: анимированный счёт чисел при попадании в viewport
  const initCounters = (root = document) => {
    const scope = root.querySelector?.("#app-content") || root;
    const els = Array.from(scope.querySelectorAll?.("[data-count-to]") || []);
    if (!els.length) return;

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

    const animateCount = (el) => {
      if (el.dataset.counted === "1") return;
      el.dataset.counted = "1";
      const to = Number(el.dataset.countTo || 0);
      const prefix = el.dataset.countPrefix || "";
      const suffix = el.dataset.countSuffix || "";
      if (reduce) {
        el.textContent = prefix + to + suffix;
        return;
      }
      const dur = 900;
      const start = performance.now();
      const step = (t) => {
        const k = Math.min(1, (t - start) / dur);
        const eased = 1 - Math.pow(1 - k, 3);
        const val = Math.round(to * eased);
        el.textContent = prefix + val + suffix;
        if (k < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };

    const io =
      initCounters._io ||
      (initCounters._io = new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            if (e.isIntersecting) {
              animateCount(e.target);
              initCounters._io.unobserve(e.target);
            }
          });
        },
        { threshold: 0.4 }
      ));

    els.forEach((el) => {
      if (el.dataset.counted === "1") return;
      io.observe(el);
    });
  };

  initCounters(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initCounters(evt.target));

  // Progress rings: toggle .is-animating → .is-revealed for a CSS-driven reveal.
  // Values (--ring-c, --ring-offset) are inline on the element, so the ring is
  // visible even if JS fails. JS only animates from hidden to target.
  const initRings = (root = document) => {
    const scope = root.querySelector?.("#app-content") || root;
    const rings = Array.from(scope.querySelectorAll?.(".ring[data-ring-pct]") || []);
    if (!rings.length) return;

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

    rings.forEach((ring) => {
      if (ring.dataset.ringBound === "1") return;
      ring.dataset.ringBound = "1";

      // Compute circumference if not already provided inline (defensive).
      const fill = ring.querySelector(".ring__fill");
      const track = ring.querySelector(".ring__track");
      if (fill && track) {
        const r = Number(fill.getAttribute("r") || 42);
        const c = 2 * Math.PI * r;
        const pct = Math.max(0, Math.min(100, Number(ring.dataset.ringPct || 0)));
        const offset = c * (1 - pct / 100);
        ring.style.setProperty("--ring-c", c.toFixed(2));
        ring.style.setProperty("--ring-offset", offset.toFixed(2));
      }

      if (reduce) return; // CSS static state already correct

      // Prepare hidden state, then reveal on intersection.
      ring.classList.add("is-animating");

      const reveal = () => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => ring.classList.add("is-revealed"));
        });
      };

      const io =
        initRings._io ||
        (initRings._io = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (!entry.isIntersecting) return;
              const r = entry.target;
              if (r.dataset.ringRevealed === "1") return;
              r.dataset.ringRevealed = "1";
              r.classList.add("is-revealed");
              initRings._io.unobserve(r);
            });
          },
          { threshold: 0.2 }
        ));

      // If already in viewport at bind time, reveal immediately.
      const rect = ring.getBoundingClientRect();
      const inView =
        rect.top < (window.innerHeight || 0) && rect.bottom > 0;
      if (inView) {
        ring.dataset.ringRevealed = "1";
        reveal();
      } else {
        io.observe(ring);
      }
    });
  };

  initRings(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initRings(evt.target));

  // Page transitions + skeleton morph for tab swaps into #app-content
  const appContent = document.getElementById("app-content");
  if (appContent) {
    const isAppSwap = (evt) =>
      evt?.detail?.target?.id === "app-content" ||
      evt?.target?.id === "app-content";

    const skeletonHTML = `
      <div class="skeleton-list js-skeleton" aria-hidden="true">
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
        <div class="skeleton-card"></div>
      </div>
    `;

    document.body.addEventListener("htmx:beforeRequest", (evt) => {
      if (!isAppSwap(evt)) return;
      appContent.classList.add("is-leaving");
    });

    document.body.addEventListener("htmx:beforeSwap", (evt) => {
      if (!isAppSwap(evt)) return;
      // If no response yet (shouldn't happen on beforeSwap) — show skeleton
      if (!evt.detail.serverResponse) {
        appContent.innerHTML = skeletonHTML;
      }
    });

    document.body.addEventListener("htmx:afterSwap", (evt) => {
      if (!isAppSwap(evt)) return;
      // Remove any leftover skeletons
      appContent.querySelectorAll(".js-skeleton").forEach((n) => n.remove());
      requestAnimationFrame(() => {
        appContent.classList.remove("is-leaving");
      });
      window.scrollTo({ top: 0, behavior: "auto" });
    });

    document.body.addEventListener("htmx:responseError", () => {
      appContent.classList.remove("is-leaving");
    });
  }

  // Startup subtabs active state
  const setActiveSubtab = (el) => {
    const wrap = el?.closest?.(".subtabs");
    if (!wrap) return;
    wrap.querySelectorAll(".subtab").forEach((a) => a.classList.remove("is-active"));
    el.classList.add("is-active");
  };
  document.body.addEventListener("click", (e) => {
    const a = e.target?.closest?.(".subtabs .subtab");
    if (a) setActiveSubtab(a);
  });

  // PWA: service worker
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/pwa/service-worker.js").catch(() => {});
    });
  }

  // Глобально: закрывать открытые поповеры при навигации
  const closePopovers = () => {
    document.querySelectorAll?.(".js-feed-sort-toggle")?.forEach((btn) => btn.setAttribute("aria-expanded", "false"));
    document.querySelectorAll?.(".feedSortMenu__panel")?.forEach((p) => (p.hidden = true));
  };
  document.body.addEventListener("htmx:beforeSwap", closePopovers);
  document.body.addEventListener("htmx:pushedIntoHistory", closePopovers);
  document.body.addEventListener("htmx:afterOnLoad", closePopovers);
  window.addEventListener("hashchange", closePopovers);
  window.addEventListener("popstate", closePopovers);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePopovers();
  });

  // Global: sticky topbar — only background opacity changes on scroll
  // (cheap, GPU-friendly). No layout/size changes, no jitter.
  const initStickyHeader = () => {
    const header = document.querySelector?.(".topbar");
    if (!header || header.dataset.stickyBound === "1") return;
    header.dataset.stickyBound = "1";

    const THRESH = 8;
    let raf = 0;
    let scrolled = false;

    const update = () => {
      raf = 0;
      const y = window.scrollY || 0;
      const shouldBeScrolled = y > THRESH;
      if (shouldBeScrolled !== scrolled) {
        scrolled = shouldBeScrolled;
        header.classList.toggle("is-scrolled", scrolled);
      }
    };

    const onScroll = () => {
      if (raf) return;
      raf = window.requestAnimationFrame(update);
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    update();
  };

  initStickyHeader();

  // ============================================================
  // Mobile gestures: Pull-to-refresh (feed) + Swipe-between-tabs
  // ============================================================

  const reduceMotionG = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

  // ---- Pull-to-refresh on feed timeline ----
  const initPullToRefresh = (root = document) => {
    const feed = root.querySelector?.(".js-feed.feedTimeline");
    if (!feed || feed.dataset.ptrBound === "1") return;
    feed.dataset.ptrBound = "1";

    // Inject a PTR indicator just before the feed
    const ptr = document.createElement("div");
    ptr.className = "ptr";
    ptr.innerHTML = '<div class="ptr__spinner" aria-hidden="true"></div>';
    feed.parentNode?.insertBefore(ptr, feed);

    const MAX = 96;
    const TRIGGER = 64;
    let startY = 0;
    let dy = 0;
    let pulling = false;
    let loading = false;

    const reset = () => {
      ptr.classList.remove("is-active");
      ptr.style.height = "";
      feed.style.transform = "";
      feed.style.transition = "transform 220ms cubic-bezier(.2,.8,.2,1)";
      dy = 0;
      pulling = false;
      setTimeout(() => {
        feed.style.transition = "";
      }, 240);
    };

    feed.addEventListener(
      "touchstart",
      (e) => {
        if (loading) return;
        if ((window.scrollY || 0) > 0) return;
        startY = e.touches[0].clientY;
        pulling = true;
        feed.style.transition = "";
      },
      { passive: true }
    );

    feed.addEventListener(
      "touchmove",
      (e) => {
        if (!pulling || loading) return;
        dy = e.touches[0].clientY - startY;
        if (dy <= 0) return;
        const pull = Math.min(MAX, Math.pow(dy, 0.85));
        ptr.classList.add("is-active");
        ptr.style.height = `${pull}px`;
        feed.style.transform = `translateY(${pull * 0.4}px)`;
      },
      { passive: true }
    );

    feed.addEventListener(
      "touchend",
      () => {
        if (!pulling) return;
        if (dy >= TRIGGER && !loading) {
          loading = true;
          ptr.classList.add("is-loading");
          ptr.style.height = "56px";
          feed.style.transform = "translateY(22px)";
          window.setTimeout(() => {
            if (window.htmx) {
              window.htmx.ajax("GET", "/ui/feed", {
                target: "#app-content",
                swap: "innerHTML",
              });
            }
            ptr.classList.remove("is-loading");
            loading = false;
            reset();
          }, 650);
        } else {
          reset();
        }
      },
      { passive: true }
    );

    feed.addEventListener("touchcancel", reset, { passive: true });
  };

  initPullToRefresh(document);
  document.body.addEventListener("htmx:afterSwap", (evt) => initPullToRefresh(evt.target));

  // ---- Swipe-between-tabs on #app-content ----
  const initSwipeTabs = () => {
    const content = document.getElementById("app-content");
    if (!content || content.dataset.swipeBound === "1") return;
    content.dataset.swipeBound = "1";

    const TAB_ORDER = ["feed", "leaderboard", "chat", "startup", "profile"];
    const getActiveIdx = () => {
      const active = document.querySelector(".tabbar .tab.is-active");
      if (!active) return -1;
      const href = active.getAttribute("href") || "";
      const match = href.match(/\/ui\/(\w+)/);
      return match ? TAB_ORDER.indexOf(match[1]) : -1;
    };
    const goToTab = (idx) => {
      if (idx < 0 || idx >= TAB_ORDER.length) return;
      const all = document.querySelectorAll(".tabbar .tab");
      const target = all[idx];
      if (!target) return;
      target.click();
    };

    let sx = 0;
    let sy = 0;
    let tracking = false;

    content.addEventListener(
      "touchstart",
      (e) => {
        if (e.touches.length !== 1) return;
        // Ignore starts on horizontally scrollable strips
        const t = e.target;
        if (t?.closest?.(".pillsRow, .feedFilters, .subtabs, .chat__messages")) return;
        sx = e.touches[0].clientX;
        sy = e.touches[0].clientY;
        tracking = true;
      },
      { passive: true }
    );

    content.addEventListener(
      "touchend",
      (e) => {
        if (!tracking) return;
        tracking = false;
        const changed = e.changedTouches?.[0];
        if (!changed) return;
        const dx = changed.clientX - sx;
        const dy = changed.clientY - sy;
        if (Math.abs(dx) < 80) return;
        if (Math.abs(dy) > 48) return;
        const idx = getActiveIdx();
        if (idx < 0) return;
        if (dx < 0) goToTab(idx + 1);
        else goToTab(idx - 1);
      },
      { passive: true }
    );
  };

  if (!reduceMotionG) initSwipeTabs();
})();

