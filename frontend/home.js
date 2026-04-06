const SUPABASE_URL = window.__ORCAFIND_SUPABASE_URL || "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = window.__ORCAFIND_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

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

  if (!headerAuth || !headerProfile) return;

  if (user?.email) {
    headerAuth.classList.add("is-hidden");
    headerProfile.classList.add("is-visible");
    const displayName = getDisplayName(user);
    setText("homeHeaderName", displayName);
    setText("homeHeaderEmail", user.email);
    setAvatar("homeHeaderAvatar", displayName);

    if (sideAuth) sideAuth.classList.add("is-hidden");
    if (sideProfile) sideProfile.style.display = "flex";
    if (sideProfileLink) sideProfileLink.style.display = "inline-flex";
    if (sideSignOut) sideSignOut.style.display = "inline-flex";
    setText("homeSideName", displayName);
    setText("homeSideEmail", user.email);
    setAvatar("homeSideAvatar", displayName);
    return;
  }

  headerAuth.classList.remove("is-hidden");
  headerProfile.classList.remove("is-visible");
  setText("homeHeaderName", "Workspace");
  setText("homeHeaderEmail", "Signed in");
  setAvatar("homeHeaderAvatar", "OrcaFind");

  if (sideAuth) sideAuth.classList.remove("is-hidden");
  if (sideProfile) sideProfile.style.display = "none";
  if (sideProfileLink) sideProfileLink.style.display = "none";
  if (sideSignOut) sideSignOut.style.display = "none";
  setText("homeSideName", "Workspace");
  setText("homeSideEmail", "Signed in");
  setAvatar("homeSideAvatar", "OrcaFind");
}

function openHomeSidebar(target) {
  const panel = document.getElementById("homeSidebar");
  const backdrop = document.getElementById("homeSidebarBackdrop");
  if (panel) {
    panel.classList.add("is-open");
    panel.setAttribute("aria-hidden", "false");
  }
  if (backdrop) backdrop.classList.add("is-open");

  if (target === "account") {
    window.setTimeout(() => {
      const signOut = document.getElementById("homeSideSignOut");
      const profile = document.getElementById("homeSideProfile");
      (signOut || profile || panel)?.scrollIntoView?.({ block: "end", behavior: "smooth" });
    }, 30);
  }
}

function closeHomeSidebar() {
  const panel = document.getElementById("homeSidebar");
  const backdrop = document.getElementById("homeSidebarBackdrop");
  if (panel) {
    panel.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
  }
  if (backdrop) backdrop.classList.remove("is-open");
}

async function homeLogout() {
  try {
    await supabaseClient.auth.signOut();
  } finally {
    closeHomeSidebar();
    window.location.href = "/";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  supabaseClient.auth.getSession().then(({ data }) => updateHeaderForUser(data?.session?.user));

  supabaseClient.auth.onAuthStateChange((_event, session) => {
    updateHeaderForUser(session?.user);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeHomeSidebar();
    }
  });
});
