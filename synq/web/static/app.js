/**
 * Staggered reveal for bento cells. Card tilt is CSS-only (see style.css).
 */
(function () {
  const reveal = document.querySelectorAll(
    ".bento-cell[data-reveal], .auth-stat-card[data-reveal]"
  );
  if (!reveal.length) return;

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    reveal.forEach((el) => el.classList.add("is-visible"));
    return;
  }

  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          en.target.classList.add("is-visible");
          io.unobserve(en.target);
        }
      });
    },
    { threshold: 0.06, rootMargin: "0px 0px -32px 0px" }
  );
  reveal.forEach((el, i) => {
    el.style.transitionDelay = `${Math.min(i * 0.05, 0.35)}s`;
    io.observe(el);
  });
})();

/** Password visibility toggles (login / signup / setup). */
(function () {
  document.querySelectorAll(".auth-password-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wrap = btn.closest(".auth-password-wrap");
      const input = wrap && wrap.querySelector("input");
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
})();
