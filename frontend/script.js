const SUPABASE_URL = "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
let authMode = "signin";
let heroRotationIndex = 0;
let heroRotationTimer;
let toastTimerSeed = 0;

const heroSnapshots = [
  {
    primaryValue: "11.4x",
    primaryLabel: "More social output from one source draft",
    secondaryValue: "4 min",
    secondaryLabel: "Average time from idea to repurposed assets",
    feedOneLabel: "What teams put in",
    feedOneBody: "Product announcements, founder notes, podcast transcripts, feature launches, customer stories.",
    feedTwoLabel: "What OrcaFind ships out",
    feedTwoBody: "Sharper hooks, more platform-native pacing, clearer CTA structure, and reusable messaging patterns."
  },
  {
    primaryValue: "83%",
    primaryLabel: "Reduction in time spent rewriting for each platform",
    secondaryValue: "2 channels",
    secondaryLabel: "Converted from one working draft by default",
    feedOneLabel: "What operators struggle with",
    feedOneBody: "Turning a strong product update into short-form content without losing clarity, nuance, or momentum.",
    feedTwoLabel: "What the workflow improves",
    feedTwoBody: "It turns one source narrative into clean distribution assets that feel native to each channel."
  },
  {
    primaryValue: "24/7",
    primaryLabel: "Always-ready content system for lean teams",
    secondaryValue: "1 click",
    secondaryLabel: "From workspace to first generated draft",
    feedOneLabel: "What founders need",
    feedOneBody: "A faster way to keep shipping content even when marketing capacity is thin and launch cycles move quickly.",
    feedTwoLabel: "What OrcaFind unlocks",
    feedTwoBody: "A structured studio with faster starts, clearer messaging, and less friction between idea and distribution."
  }
];

function getInitials(value) {
  if (!value) return "O";

  const parts = value
    .split(/[.\s@_-]+/)
    .map((part) => part.trim())
    .filter(Boolean);

  return parts.slice(0, 2).map((part) => part[0].toUpperCase()).join("") || "O";
}

function getDisplayName(user) {
  const metadataName = user?.user_metadata?.full_name || user?.user_metadata?.name;
  if (metadataName) return metadataName;
  if (user?.email) return user.email.split("@")[0];
  return "Workspace user";
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function setAvatar(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = getInitials(value);
  }
}

function setHTML(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.innerHTML = value;
  }
}

function showToast(title, message, type = "default") {
  const stack = document.getElementById("toastStack");
  if (!stack) {
    return;
  }

  const toast = document.createElement("div");
  const toastId = `toast-${Date.now()}-${toastTimerSeed++}`;
  toast.className = `toast ${type}`;
  toast.id = toastId;
  toast.innerHTML = `<strong>${title}</strong><p>${message}</p>`;
  stack.appendChild(toast);

  window.setTimeout(() => {
    const node = document.getElementById(toastId);
    if (node) {
      node.remove();
    }
  }, 3200);
}

function setButtonLoading(id, isLoading, idleLabel, loadingLabel) {
  const button = document.getElementById(id);
  if (!button) {
    return;
  }

  button.classList.toggle("is-loading", isLoading);
  button.disabled = isLoading;
  button.textContent = isLoading ? loadingLabel : idleLabel;
}

function setAuthMode(mode) {
  authMode = mode === "signup" ? "signup" : "signin";

  const signInModeBtn = document.getElementById("signInModeBtn");
  const signUpModeBtn = document.getElementById("signUpModeBtn");

  if (signInModeBtn) {
    signInModeBtn.classList.toggle("is-active", authMode === "signin");
  }
  if (signUpModeBtn) {
    signUpModeBtn.classList.toggle("is-active", authMode === "signup");
  }

  setText("authModalTitle", authMode === "signin" ? "Welcome back" : "Create your OrcaFind account");
  setText(
    "authModalDescription",
    authMode === "signin"
      ? "Sign in to access your OrcaFind workspace and protected generation flow."
      : "Create an account to start generating platform-ready content from one clean workspace."
  );
  setText(
    "authModeCopy",
    authMode === "signin"
      ? "Sign in with your existing account, or use Google if you want the fastest path into the studio."
      : "Sign up with email, or continue with Google if you want to start immediately."
  );
  setText("primaryAuthAction", authMode === "signin" ? "Sign In" : "Create Account");
}

function openAuthModal(mode = "signin") {
  const modal = document.getElementById("authModal");
  const emailInput = document.getElementById("email");
  if (modal) {
    setAuthMode(mode);
    modal.classList.add("is-visible");
    modal.setAttribute("aria-hidden", "false");
    window.setTimeout(() => {
      emailInput?.focus();
    }, 30);
  }
}

function closeAuthModal() {
  const modal = document.getElementById("authModal");
  if (modal) {
    modal.classList.remove("is-visible");
    modal.setAttribute("aria-hidden", "true");
  }
}

function handleModalBackdrop(event) {
  if (event.target?.id === "authModal") {
    closeAuthModal();
  }
}

function openProfileModal() {
  const modal = document.getElementById("profileModal");
  if (modal) {
    modal.classList.add("is-visible");
    modal.setAttribute("aria-hidden", "false");
  }
}

function closeProfileModal() {
  const modal = document.getElementById("profileModal");
  if (modal) {
    modal.classList.remove("is-visible");
    modal.setAttribute("aria-hidden", "true");
  }
}

function handleProfileBackdrop(event) {
  if (event.target?.id === "profileModal") {
    closeProfileModal();
  }
}

function setHeroSnapshot(snapshot) {
  const ids = [
    "metricPrimaryValue",
    "metricPrimaryLabel",
    "metricSecondaryValue",
    "metricSecondaryLabel",
    "feedOneLabel",
    "feedOneBody",
    "feedTwoLabel",
    "feedTwoBody"
  ];

  ids.forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      element.classList.add("is-swapping");
    }
  });

  window.setTimeout(() => {
    setText("metricPrimaryValue", snapshot.primaryValue);
    setText("metricPrimaryLabel", snapshot.primaryLabel);
    setText("metricSecondaryValue", snapshot.secondaryValue);
    setText("metricSecondaryLabel", snapshot.secondaryLabel);
    setText("feedOneLabel", snapshot.feedOneLabel);
    setText("feedOneBody", snapshot.feedOneBody);
    setText("feedTwoLabel", snapshot.feedTwoLabel);
    setText("feedTwoBody", snapshot.feedTwoBody);

    ids.forEach((id) => {
      const element = document.getElementById(id);
      if (element) {
        element.classList.remove("is-swapping");
      }
    });
  }, 180);
}

function startHeroRotation() {
  if (heroRotationTimer) {
    window.clearInterval(heroRotationTimer);
  }

  heroRotationTimer = window.setInterval(() => {
    heroRotationIndex = (heroRotationIndex + 1) % heroSnapshots.length;
    setHeroSnapshot(heroSnapshots[heroRotationIndex]);
  }, 4200);
}

function updateComposerMetrics() {
  const input = document.getElementById("inputText");
  const progress = document.getElementById("textProgress");
  const count = document.getElementById("charCount");
  const readiness = document.getElementById("readinessLabel");
  const health = document.getElementById("textHealthLabel");
  const frame = document.getElementById("workspaceFrame");

  if (!input || !progress || !count || !readiness || !health || !frame) {
    return;
  }

  const length = input.value.trim().length;
  const progressWidth = Math.min(100, Math.max(8, Math.round((length / 900) * 100)));

  count.textContent = `${length} character${length === 1 ? "" : "s"}`;
  progress.style.width = `${progressWidth}%`;
  frame.classList.toggle("is-active", document.activeElement === input || length > 0);

  if (length === 0) {
    health.textContent = "Ready for a sharp repurpose";
    readiness.textContent = "Waiting for input";
    return;
  }

  if (length < 140) {
    health.textContent = "Needs a bit more context";
    readiness.textContent = "Short draft";
    return;
  }

  if (length < 480) {
    health.textContent = "Strong enough for concise output";
    readiness.textContent = "Good signal";
    return;
  }

  health.textContent = "Rich source material detected";
  readiness.textContent = "High-output ready";
}

function initComposerMetrics() {
  const input = document.getElementById("inputText");
  const frame = document.getElementById("workspaceFrame");

  if (!input || !frame) {
    return;
  }

  input.addEventListener("input", updateComposerMetrics);
  input.addEventListener("focus", updateComposerMetrics);
  input.addEventListener("blur", updateComposerMetrics);
  updateComposerMetrics();
}

function updateStudioOutputTags() {
  const xStyle = document.getElementById("xStyle");
  const format = document.getElementById("contentFormat");
  const outputTag = document.getElementById("outputTag");
  const formatTag = document.getElementById("formatTag");

  if (!xStyle || !format || !outputTag || !formatTag) {
    return;
  }

  const xStyleValue = xStyle.value === "single" ? "single post" : "thread";
  const formatValue = format.value || "professional";

  outputTag.textContent = `Output: X ${xStyleValue} + LinkedIn`;
  formatTag.textContent = `Format: ${formatValue.replace("-", " ")}`;
}

function initStudioControls() {
  const xStyle = document.getElementById("xStyle");
  const format = document.getElementById("contentFormat");

  if (xStyle) {
    xStyle.addEventListener("change", updateStudioOutputTags);
  }
  if (format) {
    format.addEventListener("change", updateStudioOutputTags);
  }

  updateStudioOutputTags();
}

function initRevealAnimations() {
  const revealElements = document.querySelectorAll(".reveal");
  if (!revealElements.length) {
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.16 });

  revealElements.forEach((element) => observer.observe(element));
}

function initActiveNav() {
  const links = Array.from(document.querySelectorAll(".nav-link"));
  const sections = links
    .map((link) => {
      const target = document.querySelector(link.getAttribute("href"));
      return target ? { link, target } : null;
    })
    .filter(Boolean);

  if (!sections.length) {
    return;
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) {
        return;
      }

      sections.forEach(({ link, target }) => {
        link.classList.toggle("is-active", target === entry.target);
      });
    });
  }, {
    threshold: 0.45,
    rootMargin: "-20% 0px -35% 0px"
  });

  sections.forEach(({ target }) => observer.observe(target));
}

async function submitAuthAction() {
  if (authMode === "signup") {
    await handleSignup();
    return;
  }

  await handleLogin();
}

/* ---------- AUTH STATE LISTENER ---------- */

// Listen for the redirect from Google or manual login and update the UI
supabaseClient.auth.onAuthStateChange((event, session) => {
  if ((event === 'SIGNED_IN' || event === 'INITIAL_SESSION') && session?.user) {
    updateUIForUser(session.user);
  } else if (event === 'SIGNED_OUT') {
    resetUI();
  } else if (event === 'INITIAL_SESSION' && !session?.user) {
    resetUI();
  }
});

function updateUIForUser(user) {
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const signedOutWrapper = document.getElementById("accountSignedOutWrapper");
  const signedInHint = document.getElementById("accountSignedInHint");
  const headerProfile = document.getElementById("headerProfile");
  const headerAuth = document.getElementById("headerAuth");
  const displayName = getDisplayName(user);
  const email = user?.email || "Signed in";

  if (emailInput) {
    emailInput.value = email;
    emailInput.disabled = false;
  }
  if (passwordInput) {
    passwordInput.value = "";
  }
  if (signedOutWrapper) {
    signedOutWrapper.classList.add("is-hidden");
  }
  if (signedInHint) {
    signedInHint.classList.remove("is-hidden");
  }
  if (headerProfile) {
    headerProfile.classList.add("is-visible");
  }
  if (headerAuth) {
    headerAuth.classList.add("is-hidden");
  }

  setText("accountStatusTitle", "Workspace status");
  setText("accountStatusChip", "Authenticated");
  setText("accountStatusBody", "Your session is active and the protected generation workflow is ready to use.");
  setText("profileName", displayName);
  setText("profileEmail", email);
  setText("headerProfileName", displayName);
  setText("headerProfileEmail", email);
  setAvatar("profileAvatar", displayName);
  setAvatar("headerAvatar", displayName);
  closeAuthModal();
  closeProfileModal();

  console.log("User is authenticated:", email);
}

function resetUI() {
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const signedOutWrapper = document.getElementById("accountSignedOutWrapper");
  const signedInHint = document.getElementById("accountSignedInHint");
  const headerProfile = document.getElementById("headerProfile");
  const headerAuth = document.getElementById("headerAuth");

  if (emailInput) {
    emailInput.value = "";
    emailInput.disabled = false;
  }
  if (passwordInput) {
    passwordInput.value = "";
  }
  if (signedOutWrapper) {
    signedOutWrapper.classList.remove("is-hidden");
  }
  if (signedInHint) {
    signedInHint.classList.add("is-hidden");
  }
  if (headerProfile) {
    headerProfile.classList.remove("is-visible");
  }
  if (headerAuth) {
    headerAuth.classList.remove("is-hidden");
  }

  setText("accountStatusTitle", "Workspace access");
  setText("accountStatusChip", "Authentication enabled");
  setText("accountStatusBody", "Use your OrcaFind account to unlock protected generation endpoints and keep your content workflow secure.");
  setText("profileName", "Workspace user");
  setText("profileEmail", "Signed in and ready to generate content.");
  setText("headerProfileName", "Workspace user");
  setText("headerProfileEmail", "Sign in to access the studio");
  setAvatar("profileAvatar", "OrcaFind");
  setAvatar("headerAvatar", "OrcaFind");
  closeAuthModal();
  closeProfileModal();
  setAuthMode("signin");
}

/* ---------- AUTH ACTIONS ---------- */

async function handleSignup() {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  setButtonLoading("primaryAuthAction", true, "Create Account", "Creating account...");
  const { error } = await supabaseClient.auth.signUp({ email, password });
  setButtonLoading("primaryAuthAction", false, authMode === "signup" ? "Create Account" : "Sign In", "Creating account...");
  if (error) {
    showToast("Signup failed", error.message, "error");
  } else {
    showToast("Check your inbox", "Your account was created. Confirm your email to continue.", "success");
  }
}

async function handleLogin() {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  setButtonLoading("primaryAuthAction", true, "Sign In", "Signing in...");
  const { error } = await supabaseClient.auth.signInWithPassword({ email, password });
  setButtonLoading("primaryAuthAction", false, authMode === "signup" ? "Create Account" : "Sign In", "Signing in...");
  if (error) {
    showToast("Login failed", error.message, "error");
  } else {
    showToast("Signed in", "Your workspace is ready.", "success");
  }
}

async function logout() {
  await supabaseClient.auth.signOut();
  closeProfileModal();
  showToast("Signed out", "You have been logged out of OrcaFind.", "success");
}

async function loginWithGoogle() {
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: window.location.origin
    }
  });

  if (error) {
    showToast("Google sign-in failed", error.message, "error");
  }
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAuthModal();
    closeProfileModal();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  initRevealAnimations();
  initActiveNav();
  initComposerMetrics();
  initStudioControls();
  setHeroSnapshot(heroSnapshots[heroRotationIndex]);
  startHeroRotation();

  const headerProfile = document.getElementById("headerProfile");
  if (headerProfile) {
    headerProfile.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openProfileModal();
      }
    });
  }
});

/* ---------- GENERATE ---------- */

async function generate() {
  const text = document.getElementById("inputText").value;
  const button = document.getElementById("generateBtn");
  const output = document.getElementById("output");
  const xStyle = document.getElementById("xStyle")?.value || "thread";
  const contentFormat = document.getElementById("contentFormat")?.value || "professional";

  // Re-fetch session specifically at time of click to get the access_token
  const { data: { session }, error: sessionError } = await supabaseClient.auth.getSession();

  if (!session) {
    openAuthModal("signin");
    showToast("Authentication required", "Sign in to access protected content generation.", "error");
    return;
  }

  if (!text.trim()) {
    showToast("Missing content", "Paste some source content before generating posts.", "error");
    return;
  }

  button.innerText = "Processing...";
  button.disabled = true;

  setHTML(
    "output",
    `
      <div class="platform-card">
        <div class="platform-header">
          <span>Generation Engine</span>
          <span class="platform-badge">Processing</span>
        </div>
        <div class="box">Crafting hooks, tightening positioning, and shaping platform-native drafts from your source content.</div>
      </div>

      <div class="platform-card">
        <div class="platform-header">
          <span>Distribution Flow</span>
          <span class="platform-badge">In progress</span>
        </div>
        <div class="box">Preparing short-form output for X and a more structured narrative version for LinkedIn.</div>
      </div>
    `
  );

  try {
    const response = await fetch("https://api.orcafind.com/repurpose/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}` // Send the JWT to the backend
      },
      body: JSON.stringify({ text, x_style: xStyle, format: contentFormat })
    });

    const data = await response.json();

    if (!response.ok) {
      setHTML(
        "output",
        `<div class="platform-card"><div class="platform-header"><span>Request Error</span><span class="platform-badge">Needs attention</span></div><div class="box">${data.detail || "API Error"}</div></div>`
      );
      showToast("Generation failed", data.detail || "API Error", "error");
      return;
    }

    // Prefer a stable delimiter ("LinkedIn:") from backend prompt.
    const parts = data.result.split("LinkedIn:");

    setHTML(
      "output",
      `
      <div class="platform-card">
        <div class="platform-header"><span>Twitter / X</span><span class="platform-badge">${xStyle === "single" ? "Single" : "Thread"}</span></div>
        <div class="box">${parts[0].replace(/^X:\\s*/i, "").trim()}</div>
      </div>

      <div class="platform-card">
        <div class="platform-header"><span>LinkedIn</span><span class="platform-badge">Professional</span></div>
        <div class="box">${(parts[1] || "").trim()}</div>
      </div>
    `
    );
    showToast("Posts generated", "Your X and LinkedIn drafts are ready.", "success");

  } catch (err) {
    setHTML(
      "output",
      `<div class="platform-card"><div class="platform-header"><span>Connection Error</span><span class="platform-badge">Offline</span></div><div class="box">Error connecting to API: ${err.message}</div></div>`
    );
    showToast("Connection error", `Error connecting to API: ${err.message}`, "error");
  } finally {
    button.innerText = "Generate Posts";
    button.disabled = false;
  }
}

/* ---------- UTILS ---------- */

function copyText() {
  const output = document.getElementById("output");
  if (output && output.innerText.trim()) {
    navigator.clipboard.writeText(output.innerText);
    showToast("Copied", "All generated results were copied to your clipboard.", "success");
  }
}
