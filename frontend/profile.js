// Profile page logic (served from /profile.js).
// Note: this is used by the Next.js `/profile/` page shell.

const ORCAFIND_CONFIG = window.__ORCAFIND_CONFIG || {};
const SUPABASE_URL = ORCAFIND_CONFIG.supabaseUrl || window.__ORCAFIND_SUPABASE_URL || "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = ORCAFIND_CONFIG.supabaseAnonKey || window.__ORCAFIND_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

const API_BASE_URL = ORCAFIND_CONFIG.apiBaseUrl || window.__ORCAFIND_API_BASE_URL
  || (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://127.0.0.1:8000"
    : "https://api.orcafind.com");

if (!window.supabase?.createClient) {
  // Fail gracefully if the CDN is blocked.
  // The page will show the signed-out state by default.
  console.warn("Supabase JS not available on /profile/.");
} else {
  const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function getInitials(value) {
    const v = String(value || "").trim();
    if (!v) return "O";
    const parts = v.split(/[.\s@_-]+/).map((p) => p.trim()).filter(Boolean);
    return parts.slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "O";
  }

  function getDisplayName(user) {
    const meta = user?.user_metadata || {};
    const name = meta.full_name || meta.name || meta.display_name;
    if (typeof name === "string" && name.trim()) return name.trim();
    const email = user?.email || "";
    if (typeof email === "string" && email.includes("@")) return email.split("@")[0];
    return "Workspace user";
  }

  function setAvatar(displayName) {
    const el = document.getElementById("profileAvatar");
    if (!el) return;
    el.textContent = getInitials(displayName);
  }

  let toastSeed = 0;
  function showToast(title, message, type = "default") {
    const stack = document.getElementById("toastStack");
    if (!stack) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.dataset.toastId = `toast-${Date.now()}-${toastSeed++}`;
    toast.innerHTML = `<strong>${escapeHTML(title)}</strong><p>${escapeHTML(message || "")}</p>`;
    stack.appendChild(toast);
    window.setTimeout(() => toast.remove(), 3600);
  }

  function escapeHTML(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function withTimeout(promise, ms = 4500) {
    return Promise.race([
      promise,
      new Promise((resolve) => window.setTimeout(() => resolve(null), ms)),
    ]);
  }

  async function fetchEntitlements(accessToken) {
    if (!accessToken) return null;
    try {
      const res = await withTimeout(fetch(`${API_BASE_URL}/entitlements`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${accessToken}` },
      }));
      if (!res || !res.ok) return null;
      const data = await res.json();
      writeCachedEntitlements(data);
      return data;
    } catch (_err) {
      return null;
    }
  }

  function readCachedEntitlements() {
    try {
      const cached = JSON.parse(window.localStorage.getItem("orcafind_entitlements_cache") || "null");
      if (cached?.entitlements && typeof cached?.at === "number") {
        const fresh = Date.now() - cached.at < 7 * 24 * 60 * 60 * 1000;
        return fresh ? cached.entitlements : null;
      }
    } catch (_err) {}
    return null;
  }

  function writeCachedEntitlements(entitlements) {
    try {
      if (!entitlements) return;
      window.localStorage.setItem("orcafind_entitlements_cache", JSON.stringify({ at: Date.now(), entitlements }));
    } catch (_err) {}
  }

  function _getSupabaseProjectRef() {
    try {
      const url = new URL(SUPABASE_URL);
      const host = url.hostname || "";
      return host.split(".")[0] || "";
    } catch (_err) {
      return "";
    }
  }

  function _readStoredSessionSnapshot() {
    try {
      const ref = _getSupabaseProjectRef();
      const preferredKey = ref ? `sb-${ref}-auth-token` : "";
      const keys = Object.keys(window.localStorage || {});
      const ordered = [];
      if (preferredKey && keys.includes(preferredKey)) ordered.push(preferredKey);
      keys.forEach((k) => {
        if (k === preferredKey) return;
        if (k.startsWith("sb-") && k.endsWith("-auth-token")) ordered.push(k);
      });

      for (const key of ordered) {
        const raw = window.localStorage.getItem(key);
        if (!raw) continue;
        const parsed = JSON.parse(raw);
        const access_token = parsed?.access_token;
        const refresh_token = parsed?.refresh_token;
        if (typeof access_token === "string" && typeof refresh_token === "string") {
          return { access_token, refresh_token, user: parsed?.user || null };
        }
      }
    } catch (_err) {}
    return null;
  }

  function _readStoredSessionTokens() {
    const snapshot = _readStoredSessionSnapshot();
    if (!snapshot) return null;
    return {
      access_token: snapshot.access_token,
      refresh_token: snapshot.refresh_token,
    };
  }

  function renderStoredProfileImmediately() {
    const snapshot = _readStoredSessionSnapshot();
    if (!snapshot?.user) return false;
    applySignedInUI({
      user: snapshot.user,
      entitlements: readCachedEntitlements() || { plan: "free" },
    });
    return true;
  }

  function applySignedOutUI() {
    setText("profileHeading", "Profile");
    setText("profileName", "Workspace user");
    setText("profileEmail", "Sign in to view your account details.");
    setAvatar("OrcaFind");
    setText("profilePlanPill", "Plan: Free");
    setText("workspaceStatus", "Signed out");
    setText("workspaceStatusHint", "Sign in to unlock protected endpoints.");
    setText("workspaceRole", "Standard");
    setText("workspaceRoleHint", "Admin access appears here when enabled.");
    const authCta = document.getElementById("authCta");
    if (authCta) {
      authCta.textContent = "Sign In";
      authCta.setAttribute("href", "/auth/?mode=signin&next=/profile/");
      authCta.classList.remove("btn-ghost");
      authCta.classList.add("btn-primary");
    }
    const signedOutNotice = document.getElementById("signedOutNotice");
    if (signedOutNotice) signedOutNotice.style.display = "block";
    const signedInActions = document.getElementById("signedInActions");
    if (signedInActions) signedInActions.style.display = "none";

    const billingSignedOut = document.getElementById("billingSignedOut");
    if (billingSignedOut) billingSignedOut.style.display = "block";
    const billingSignedIn = document.getElementById("billingSignedIn");
    if (billingSignedIn) billingSignedIn.style.display = "none";
  }

  function _formatDateFromUnixSeconds(value) {
    const seconds = Number(value || 0);
    if (!Number.isFinite(seconds) || seconds <= 0) return "—";
    try {
      const d = new Date(seconds * 1000);
      return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
    } catch (_err) {
      return "—";
    }
  }

  function renderBilling(entitlements) {
    const billingSignedOut = document.getElementById("billingSignedOut");
    const billingSignedIn = document.getElementById("billingSignedIn");
    if (billingSignedOut) billingSignedOut.style.display = "none";
    if (billingSignedIn) billingSignedIn.style.display = "block";

    const subscription = entitlements?.subscription || null;
    const plan = String(entitlements?.plan || "free").toLowerCase();

    const status = subscription?.status ? String(subscription.status) : (plan === "free" ? "No subscription" : "Active");
    const cancelAtEnd = Boolean(subscription?.cancel_at_cycle_end);
    const periodEnd = subscription?.current_period_end;
    const normalizedStatus = String(status || "").trim().toLowerCase();
    const isActiveSubscription = Boolean(subscription) && (normalizedStatus === "active" || normalizedStatus === "trialing");

    setText("billingStatus", status);
    setText(
      "billingStatusHint",
      !subscription
        ? "Upgrade to manage your plan and billing settings."
        : cancelAtEnd
          ? "Your subscription will cancel at the end of the current period."
          : isActiveSubscription
            ? "Manage your plan and billing settings."
            : "This subscription is inactive. Re-subscribe to change plans."
    );

    const renews = _formatDateFromUnixSeconds(periodEnd);
    setText("billingRenews", renews);
    setText("billingRenewsHint", periodEnd ? "Current billing period end date." : "Upgrade to get renewal dates and invoices.");

    const planSelect = document.getElementById("billingPlanSelect");
    if (planSelect) {
      // Default to current plan if it matches.
      if (plan === "starter" || plan === "pro" || plan === "business") {
        planSelect.value = plan;
      } else {
        planSelect.value = "pro";
      }
      planSelect.disabled = !isActiveSubscription;
    }

    const planBtn = document.getElementById("billingPlanBtn");
    if (planBtn) planBtn.disabled = !isActiveSubscription;

    const cancelBtn = document.getElementById("billingCancelBtn");
    if (cancelBtn) {
      cancelBtn.disabled = !isActiveSubscription;
      cancelBtn.textContent = cancelAtEnd ? "Keep subscription" : "Cancel at period end";
    }

    const inactiveHint = document.getElementById("billingInactiveHint");
    if (inactiveHint) {
      inactiveHint.style.display = subscription && !isActiveSubscription ? "block" : "none";
    }
  }

  function applySignedInUI({ user, entitlements }) {
    const displayName = getDisplayName(user);
    setText("profileHeading", `Hi, ${displayName}!`);
    setAvatar(displayName);
    setText("profileName", displayName);
    setText("profileEmail", user?.email || "Signed in");

    const isPremium = Boolean(entitlements?.is_premium);
    const isAdmin = Boolean(entitlements?.is_admin);
    const plan = entitlements?.plan || (isPremium ? "pro" : "free");
    const planLabel = String(plan).toUpperCase();
    setText("profilePlanPill", `Plan: ${planLabel}`);

    setText("workspaceStatus", "Authenticated");
    setText("workspaceStatusHint", "Your session is active and protected endpoints are enabled.");
    setText("workspaceRole", isAdmin ? "Admin" : "Standard");
    setText("workspaceRoleHint", isAdmin ? "Admin access is enabled for testing." : "Upgrade to Pro to unlock premium features.");

    setText("statText", "Enabled");

    if (isPremium) {
      setText("statImages", "Unlocked");
      setText("statImagesHint", "AI images are available in the studio.");
    } else {
      setText("statImages", "Pro only");
      setText("statImagesHint", "Upgrade to Pro to unlock AI images.");
    }

    const remaining = entitlements?.limits?.image_generations_remaining;
    if (typeof remaining === "number") {
      const hint = document.getElementById("statImagesHint");
      if (hint && isPremium) {
        hint.textContent = `${remaining} image generation${remaining === 1 ? "" : "s"} remaining for your current period.`;
      }
    }

    const authCta = document.getElementById("authCta");
    if (authCta) {
      authCta.textContent = "Studio";
      authCta.setAttribute("href", "/studio/");
      authCta.classList.remove("btn-primary");
      authCta.classList.add("btn-ghost");
    }

    const signedOutNotice = document.getElementById("signedOutNotice");
    if (signedOutNotice) signedOutNotice.style.display = "none";
    const signedInActions = document.getElementById("signedInActions");
    if (signedInActions) signedInActions.style.display = "grid";

    renderBilling(entitlements || { plan: "free" });
  }

  let lastRenderedAccessToken = "";
  let entitlementsSyncInFlight = null;

  async function syncEntitlementsForSession(session) {
    if (!session?.access_token) return null;
    if (entitlementsSyncInFlight) return entitlementsSyncInFlight;
    entitlementsSyncInFlight = fetchEntitlements(session.access_token)
      .then((entitlements) => {
        applySignedInUI({
          user: session.user,
          entitlements: entitlements || readCachedEntitlements() || { plan: "free" },
        });
        return entitlements;
      })
      .finally(() => {
        entitlementsSyncInFlight = null;
      });
    return entitlementsSyncInFlight;
  }

  async function hydrate({ allowSignedOut = true, quick = false } = {}) {
    async function tryGetSession() {
      try {
        const { data } = await supabaseClient.auth.getSession();
        return data?.session || null;
      } catch (_err) {
        return null;
      }
    }

    let session = await tryGetSession();

    if (!session?.user && !quick) {
      try {
        await supabaseClient.auth.refreshSession();
      } catch (_err) {}
      session = await tryGetSession();
    }

    if (!session?.user) {
      const tokens = _readStoredSessionTokens();
      if (tokens) {
        try {
          await supabaseClient.auth.setSession(tokens);
        } catch (_err) {}
        session = await tryGetSession();
      }
    }

    const attempts = quick ? 1 : 3;
    for (let attempt = 0; attempt < attempts && !session?.user; attempt += 1) {
      await new Promise((r) => window.setTimeout(r, 120 + attempt * 100));
      session = await tryGetSession();
    }

    if (!session?.user) {
      if (allowSignedOut) applySignedOutUI();
      return;
    }

    lastRenderedAccessToken = session.access_token || "";
    applySignedInUI({
      user: session.user,
      entitlements: readCachedEntitlements() || { plan: "free" },
    });
    syncEntitlementsForSession(session);
  }

  async function profileSignOut() {
    try {
      await supabaseClient.auth.signOut();
      showToast("Signed out", "You have been logged out of OrcaFind.", "success");
    } catch (_err) {
      showToast("Sign out failed", "Please try again.", "error");
    } finally {
      applySignedOutUI();
    }
  }

  window.profileSignOut = profileSignOut;

  async function _getAccessToken() {
    try {
      const { data } = await supabaseClient.auth.getSession();
      return data?.session?.access_token || "";
    } catch (_err) {
      return "";
    }
  }

  async function billingChangePlan() {
    const accessToken = await _getAccessToken();
    if (!accessToken) {
      showToast("Sign in required", "Please sign in again to manage billing.", "error");
      applySignedOutUI();
      return;
    }

    const select = document.getElementById("billingPlanSelect");
    const btn = document.getElementById("billingPlanBtn");
    const plan = String(select?.value || "pro").toLowerCase();
    if (btn) btn.disabled = true;

    try {
      const res = await fetch(`${API_BASE_URL}/billing/dodo/subscription/change`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ plan }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data?.detail?.message || data?.detail || data?.message || "Unable to change plan.";
        const normalized = String(msg || "").toLowerCase();
        if (normalized.includes("inactive subscriptions") || normalized.includes("inactive_subscription")) {
          showToast("Subscription inactive", "This subscription can't be changed. Open pricing to start a new subscription.", "error");
          return;
        }
        showToast("Billing update failed", String(msg), "error");
        return;
      }
      const entitlements = data?.entitlements || null;
      if (entitlements) writeCachedEntitlements(entitlements);
      showToast("Plan updated", "Your subscription plan has been updated.", "success");
      renderBilling(entitlements || readCachedEntitlements() || { plan });
      if (entitlements) {
        const planLabel = String(entitlements.plan || plan).toUpperCase();
        setText("profilePlanPill", `Plan: ${planLabel}`);
      }
    } catch (_err) {
      showToast("Billing update failed", "Please try again.", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function billingToggleCancel() {
    const accessToken = await _getAccessToken();
    if (!accessToken) {
      showToast("Sign in required", "Please sign in again to manage billing.", "error");
      applySignedOutUI();
      return;
    }

    const btn = document.getElementById("billingCancelBtn");
    if (btn) btn.disabled = true;

    try {
      const entitlements = readCachedEntitlements() || { plan: "free" };
      const subscription = entitlements?.subscription || null;
      const nextCancel = !Boolean(subscription?.cancel_at_cycle_end);

      const res = await fetch(`${API_BASE_URL}/billing/dodo/subscription/cancel`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ cancel_at_cycle_end: nextCancel }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data?.detail?.message || data?.detail || data?.message || "Unable to update cancellation.";
        showToast("Billing update failed", String(msg), "error");
        return;
      }
      const updated = data?.entitlements || null;
      if (updated) writeCachedEntitlements(updated);
      showToast("Updated", nextCancel ? "Subscription will cancel at period end." : "Subscription will continue.", "success");
      renderBilling(updated || readCachedEntitlements() || entitlements);
    } catch (_err) {
      showToast("Billing update failed", "Please try again.", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  window.billingChangePlan = billingChangePlan;
  window.billingToggleCancel = billingToggleCancel;

  document.addEventListener("DOMContentLoaded", () => {
    const renderedFromStorage = renderStoredProfileImmediately();
    const debugEnabled = new URLSearchParams(window.location.search).get("debug") === "1";
    if (debugEnabled) {
      const panel = document.createElement("pre");
      panel.style.cssText = "white-space:pre-wrap; word-break:break-word; padding:14px; border-radius:16px; border:1px solid rgba(111,132,163,.18); background:rgba(255,255,255,.85); margin:16px auto; max-width:1120px; width:calc(100% - 32px);";
      if (document.documentElement.dataset.theme === "dark") {
        panel.style.background = "rgba(6,10,18,.78)";
        panel.style.borderColor = "rgba(255,255,255,.10)";
      }
      panel.textContent = "Profile debug enabled…";
      document.body.appendChild(panel);

      (async () => {
        const ref = _getSupabaseProjectRef();
        const keys = Object.keys(window.localStorage || {}).filter((k) => k.startsWith("sb-") && k.endsWith("-auth-token"));
        const tokens = _readStoredSessionTokens();
        let session = null;
        try {
          const { data } = await supabaseClient.auth.getSession();
          session = data?.session || null;
        } catch (_err) {}

        panel.textContent = [
          `host: ${window.location.host}`,
          `path: ${window.location.pathname}`,
          `supabase_ref: ${ref || "(unknown)"}`,
          `storage_keys: ${keys.length ? keys.join(", ") : "(none)"}`,
          `tokens_found: ${tokens ? "yes" : "no"}`,
          `getSession_user: ${session?.user?.email || "(none)"}`,
        ].join("\n");
      })();
    }

    hydrate({ allowSignedOut: !renderedFromStorage, quick: renderedFromStorage });
    supabaseClient.auth.onAuthStateChange((event, session) => {
      if (event === "SIGNED_OUT") {
        lastRenderedAccessToken = "";
        applySignedOutUI();
        return;
      }

      if ((event === "SIGNED_IN" || event === "INITIAL_SESSION") && session?.user) {
        if (session.access_token === lastRenderedAccessToken) return;
        lastRenderedAccessToken = session.access_token || "";
        applySignedInUI({
          user: session.user,
          entitlements: readCachedEntitlements() || { plan: "free" },
        });
        syncEntitlementsForSession(session);
        return;
      }

      if (event === "INITIAL_SESSION" && !session?.user && !renderedFromStorage) {
        hydrate({ allowSignedOut: false, quick: true }).then(() => {
          supabaseClient.auth.getSession().then(({ data }) => {
            if (!data?.session?.user) applySignedOutUI();
          }).catch(() => applySignedOutUI());
        });
      }
    });
  });
}
