const SUPABASE_URL = "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

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

  if (!headerAuth || !headerProfile) return;

  if (user?.email) {
    headerAuth.classList.add("is-hidden");
    headerProfile.classList.add("is-visible");
    const displayName = getDisplayName(user);
    setText("homeHeaderName", displayName);
    setText("homeHeaderEmail", user.email);
    setAvatar("homeHeaderAvatar", displayName);
    return;
  }

  headerAuth.classList.remove("is-hidden");
  headerProfile.classList.remove("is-visible");
  setText("homeHeaderName", "Workspace");
  setText("homeHeaderEmail", "Signed in");
  setAvatar("homeHeaderAvatar", "OrcaFind");
}

document.addEventListener("DOMContentLoaded", () => {
  supabaseClient.auth.getSession().then(({ data }) => updateHeaderForUser(data?.session?.user));

  supabaseClient.auth.onAuthStateChange((_event, session) => {
    updateHeaderForUser(session?.user);
  });
});

