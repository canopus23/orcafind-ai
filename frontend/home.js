const ORCAFIND_CONFIG = window.__ORCAFIND_CONFIG || {};
const SUPABASE_URL = ORCAFIND_CONFIG.supabaseUrl || window.__ORCAFIND_SUPABASE_URL || "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = ORCAFIND_CONFIG.supabaseAnonKey || window.__ORCAFIND_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setAvatar(id, displayName) {
  const el = document.getElementById(id);
  if (!el) return;
  const initial = (displayName || "O").trim().charAt(0).toUpperCase() || "O";
  el.textContent = initial;
}

function getDisplayName(user) {
  const meta = user?.user_metadata || {};
  const name = meta.full_name || meta.name || meta.display_name;
  if (typeof name === "string" && name.trim()) return name.trim();
  const email = user?.email || "";
  if (typeof email === "string" && email.includes("@")) return email.split("@")[0];
  return "Workspace";
}

function updateHeaderForUser(user) {
  const headerAuth = document.getElementById("homeHeaderAuth");
  const headerProfile = document.getElementById("homeHeaderProfile");
  const sideAuth = document.getElementById("homeSideAuth");
  const sideProfile = document.getElementById("homeSideProfile");
  const sideProfileLink = document.getElementById("homeSideProfileLink");
  const sideSignOut = document.getElementById("homeSideSignOut");
  const footerSignIn = document.getElementById("footerAccountSignIn");
  const footerSignOut = document.getElementById("footerAccountSignOut");

  if (!headerAuth || !headerProfile) return;

  if (user?.email) {
    headerAuth.classList.add("is-hidden");
    headerProfile.classList.add("is-visible");
    const displayName = getDisplayName(user);
    setText("homeHeaderGreeting", `Hi, ${displayName}!`);
    setAvatar("homeHeaderAvatar", displayName);

    if (sideAuth) sideAuth.classList.add("is-hidden");
    if (sideProfile) sideProfile.style.display = "flex";
    if (sideProfileLink) sideProfileLink.style.display = "inline-flex";
    if (sideSignOut) sideSignOut.style.display = "inline-flex";
    setText("homeSideName", displayName);
    setText("homeSideEmail", user.email);
    setAvatar("homeSideAvatar", displayName);

    if (footerSignIn) footerSignIn.style.display = "none";
    if (footerSignOut) footerSignOut.style.display = "inline-flex";
    return;
  }

  headerAuth.classList.remove("is-hidden");
  headerProfile.classList.remove("is-visible");
  setText("homeHeaderGreeting", "Hi!");
  setAvatar("homeHeaderAvatar", "OrcaFind");

  if (sideAuth) sideAuth.classList.remove("is-hidden");
  if (sideProfile) sideProfile.style.display = "none";
  if (sideProfileLink) sideProfileLink.style.display = "none";
  if (sideSignOut) sideSignOut.style.display = "none";
  setText("homeSideName", "Workspace");
  setText("homeSideEmail", "Signed in");
  setAvatar("homeSideAvatar", "OrcaFind");

  if (footerSignIn) footerSignIn.style.display = "inline-flex";
  if (footerSignOut) footerSignOut.style.display = "none";
}

function openHomeSidebar(target) {
  const panel = document.getElementById("homeSidebar");
  const backdrop = document.getElementById("homeSidebarBackdrop");
  const activeEl = document.activeElement;
  if (activeEl && activeEl instanceof HTMLElement) {
    window.__orcafindHomeSidebarLastFocus = activeEl;
  }
  if (panel) {
    panel.classList.add("is-open");
    panel.setAttribute("aria-hidden", "false");
    setHomeSidebarFocusEnabled(panel, true);
  }
  if (backdrop) backdrop.classList.add("is-open");

  if (target === "account") {
    window.setTimeout(() => {
      const signOut = document.getElementById("homeSideSignOut");
      const profile = document.getElementById("homeSideProfile");
      (signOut || profile || panel)?.scrollIntoView?.({ block: "end", behavior: "smooth" });
    }, 30);
  }

  window.setTimeout(() => {
    const closeButton = panel?.querySelector('button[aria-label="Close menu"]');
    closeButton?.focus?.({ preventScroll: true });
  }, 0);
}

function closeHomeSidebar() {
  const panel = document.getElementById("homeSidebar");
  const backdrop = document.getElementById("homeSidebarBackdrop");
  if (panel) {
    panel.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
    setHomeSidebarFocusEnabled(panel, false);
  }
  if (backdrop) backdrop.classList.remove("is-open");

  const lastFocus = window.__orcafindHomeSidebarLastFocus;
  if (lastFocus && lastFocus instanceof HTMLElement) {
    window.__orcafindHomeSidebarLastFocus = null;
    try {
      lastFocus.focus({ preventScroll: true });
    } catch (_err) {}
  }
}

function setHomeSidebarFocusEnabled(panel, enabled) {
  if (!panel) return;

  try {
    panel.inert = !enabled;
  } catch (_err) {}

  const focusables = Array.from(
    panel.querySelectorAll(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]'
    )
  );

  focusables.forEach((el) => {
    if (!(el instanceof HTMLElement)) return;
    if (enabled) {
      if (!Object.prototype.hasOwnProperty.call(el.dataset, "prevTabindex")) return;
      const prev = el.dataset.prevTabindex;
      delete el.dataset.prevTabindex;
      if (prev === "") el.removeAttribute("tabindex");
      else el.setAttribute("tabindex", prev);
      return;
    }

    if (!Object.prototype.hasOwnProperty.call(el.dataset, "prevTabindex")) {
      el.dataset.prevTabindex = el.getAttribute("tabindex") ?? "";
    }
    el.setAttribute("tabindex", "-1");
  });
}

async function homeLogout() {
  try {
    await supabaseClient.auth.signOut();
  } finally {
    closeHomeSidebar();
    window.location.href = "/";
  }
}

function initHowItWorksRail() {
  const rail = document.getElementById("howSteps");
  const indicator = document.getElementById("howIndicator");
  const progress = document.getElementById("howProgress");
  const panelsRoot = document.getElementById("howPanels");
  if (!rail || !indicator || !progress || !panelsRoot) return;

  const buttons = Array.from(rail.querySelectorAll("[data-how-tab]"));
  const panels = Array.from(panelsRoot.querySelectorAll("[data-how-panel]"));
  if (!buttons.length || !panels.length) return;

  const order = buttons.map((btn) => btn.dataset.howTab).filter(Boolean);
  const ROTATE_MS = 7200;
  let rotateTimer = null;
  let current = buttons.find((b) => b.getAttribute("aria-selected") === "true")?.dataset.howTab || order[0];
  let lastInteractionAt = 0;

  function updateIndicator() {
    const active = buttons.find((b) => b.dataset.howTab === current);
    if (!active) return;
    // If the highlight is hidden (mobile), skip indicator positioning.
    if (window.getComputedStyle(indicator).display === "none") return;
    const y = Math.max(0, active.offsetTop - 10);
    rail.style.setProperty("--how-y", `${y}px`);
    rail.style.setProperty("--how-h", `${Math.max(52, active.offsetHeight)}px`);
    active.scrollIntoView({ block: "nearest" });
  }

  function restartProgress() {
    progress.classList.remove("is-running");
    void progress.offsetWidth;
    progress.style.setProperty("--how-duration", `${ROTATE_MS}ms`);
    progress.classList.add("is-running");
  }

  function setActive(next, { focus = false, user = false } = {}) {
    if (!next || next === current) return;
    current = next;
    if (user) lastInteractionAt = Date.now();

    buttons.forEach((btn) => {
      const selected = btn.dataset.howTab === current;
      btn.setAttribute("aria-selected", selected ? "true" : "false");
      btn.tabIndex = selected ? 0 : -1;
      if (selected && focus) btn.focus();
    });

    panels.forEach((panel) => {
      const active = panel.dataset.howPanel === current;
      panel.classList.toggle("is-active", active);
      panel.setAttribute("aria-hidden", active ? "false" : "true");
      if (active) {
        panel.classList.remove("is-entering");
        void panel.offsetWidth;
        panel.classList.add("is-entering");
        window.setTimeout(() => panel.classList.remove("is-entering"), 420);
      }
    });

    updateIndicator();
    restartProgress();
  }

  function selectInitial() {
    const initial = order.includes(current) ? current : order[0];
    current = initial;
    buttons.forEach((btn) => {
      const selected = btn.dataset.howTab === current;
      btn.setAttribute("aria-selected", selected ? "true" : "false");
      btn.tabIndex = selected ? 0 : -1;
    });
    panels.forEach((panel) => {
      const active = panel.dataset.howPanel === current;
      panel.classList.toggle("is-active", active);
      panel.setAttribute("aria-hidden", active ? "false" : "true");
    });
    updateIndicator();
    restartProgress();
  }

  function rotate() {
    const now = Date.now();
    if (now - lastInteractionAt < 12000) return;
    const idx = Math.max(0, order.indexOf(current));
    const next = order[(idx + 1) % order.length];
    setActive(next, { user: false });
  }

  buttons.forEach((btn) => {
    btn.addEventListener("click", () => setActive(btn.dataset.howTab, { user: true }));
    btn.addEventListener("keydown", (event) => {
      const idx = order.indexOf(current);
      if (event.key === "ArrowDown" || event.key === "ArrowRight") {
        event.preventDefault();
        setActive(order[(idx + 1) % order.length], { focus: true, user: true });
      }
      if (event.key === "ArrowUp" || event.key === "ArrowLeft") {
        event.preventDefault();
        setActive(order[(idx - 1 + order.length) % order.length], { focus: true, user: true });
      }
      if (event.key === "Home") {
        event.preventDefault();
        setActive(order[0], { focus: true, user: true });
      }
      if (event.key === "End") {
        event.preventDefault();
        setActive(order[order.length - 1], { focus: true, user: true });
      }
    });
  });

  window.addEventListener("resize", () => updateIndicator());
  rail.addEventListener("scroll", () => updateIndicator(), { passive: true });

  selectInitial();
  rotateTimer = window.setInterval(rotate, ROTATE_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (rotateTimer) window.clearInterval(rotateTimer);
      rotateTimer = null;
      progress.classList.remove("is-running");
    } else if (!rotateTimer) {
      updateIndicator();
      restartProgress();
      rotateTimer = window.setInterval(rotate, ROTATE_MS);
    }
  });
}

function initRevealAnimations() {
  const nodes = Array.from(document.querySelectorAll(".reveal"));
  if (!nodes.length) return;

  // If reduced motion is preferred, show everything immediately.
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    nodes.forEach((n) => n.classList.add("is-visible"));
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("is-visible");
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.14, rootMargin: "0px 0px -10% 0px" });

  nodes.forEach((n) => observer.observe(n));
}

function initCountUpMetrics() {
  const nodes = Array.from(document.querySelectorAll("[data-countup]"));
  if (!nodes.length) return;

  const prefersReduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReduced) return;

  function animateNode(node) {
    const raw = node.getAttribute("data-countup");
    const suffix = node.getAttribute("data-suffix") || "";
    const target = Number(raw);
    if (!Number.isFinite(target)) return;

    const start = 0;
    const duration = 900;
    const t0 = performance.now();
    node.dataset.counted = "true";

    function tick(now) {
      const p = Math.min(1, (now - t0) / duration);
      // Ease out.
      const eased = 1 - Math.pow(1 - p, 3);
      const value = Math.round(start + (target - start) * eased);
      node.textContent = `${value}${suffix}`;
      if (p < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const node = entry.target;
      if (node.dataset.counted === "true") return;
      animateNode(node);
      observer.unobserve(node);
    });
  }, { threshold: 0.35 });

  nodes.forEach((n) => observer.observe(n));
}

function initActiveNav() {
  const links = Array.from(document.querySelectorAll(".nav-link"));
  const entries = links
    .map((link) => {
      const href = (link.getAttribute("href") || "").trim();
      if (!href.startsWith("#")) return null;
      const target = document.querySelector(href);
      if (!target) return null;
      return { link, target };
    })
    .filter(Boolean);

  if (!entries.length) return;

  const observer = new IntersectionObserver((items) => {
    items.forEach((item) => {
      if (!item.isIntersecting) return;
      entries.forEach(({ link, target }) => {
        link.classList.toggle("is-active", target === item.target);
      });
    });
  }, { threshold: 0.45, rootMargin: "-20% 0px -35% 0px" });

  entries.forEach(({ target }) => observer.observe(target));
}

document.addEventListener("DOMContentLoaded", () => {
  supabaseClient.auth.getSession().then(({ data }) => updateHeaderForUser(data?.session?.user));

  supabaseClient.auth.onAuthStateChange((_event, session) => {
    updateHeaderForUser(session?.user);
  });

  closeHomeSidebar();

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeHomeSidebar();
    }
  });

  initHowItWorksRail();
  initRevealAnimations();
  initCountUpMetrics();
  initActiveNav();
});
