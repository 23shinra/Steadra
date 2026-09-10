document.addEventListener("DOMContentLoaded", () => {
  const burger = document.getElementById("lp-burger");
  const menu = document.getElementById("lp-menu");

  const closeMenu = () => {
    if (!menu || !burger) return;
    burger.classList.remove("is-open");
    burger.setAttribute("aria-expanded", "false");
    menu.classList.remove("is-open");
    window.setTimeout(() => {
      if (!burger.classList.contains("is-open")) menu.hidden = true;
    }, 280);
  };

  const openMenu = () => {
    if (!menu || !burger) return;
    menu.hidden = false;
    requestAnimationFrame(() => {
      burger.classList.add("is-open");
      burger.setAttribute("aria-expanded", "true");
      menu.classList.add("is-open");
    });
  };

  burger?.addEventListener("click", () => {
    if (burger.classList.contains("is-open")) closeMenu();
    else openMenu();
  });

  menu?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => closeMenu());
  });

  const reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-in");
          io.unobserve(entry.target);
        });
      },
      { threshold: 0.16, rootMargin: "0px 0px -8% 0px" }
    );
    reveals.forEach((el, index) => {
      el.style.transitionDelay = `${Math.min(index * 0.04, 0.24)}s`;
      io.observe(el);
    });
  } else {
    reveals.forEach((el) => el.classList.add("is-in"));
  }
});
