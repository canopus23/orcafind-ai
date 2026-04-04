const SUPABASE_URL = "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
let authMode = "signin";
let heroRotationIndex = 0;
let heroRotationTimer;
let toastTimerSeed = 0;
let lastGenerated = { x: "", linkedin: "" };
let entitlements = {
  plan: "free",
  is_admin: false,
  is_premium: false,
  limits: {
    x_single_variants: 2,
    x_thread_tweets_min: 4,
    x_thread_tweets_max: 7,
    image_generations_total: 20,
    image_generations_used: 0,
    image_generations_remaining: 20,
  },
};
let studioMode = "text";

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

function setStudioMode(mode) {
  studioMode = mode === "images" ? "images" : mode === "builder" ? "builder" : "text";
  try {
    window.localStorage.setItem("orcafind_studio_mode", studioMode);
  } catch (_err) {}

  const textPanel = document.getElementById("studioTextPanel");
  const imagesPanel = document.getElementById("studioImagesPanel");
  const tabText = document.getElementById("studioTabText");
  const tabImages = document.getElementById("studioTabImages");
  const builderPanel = document.getElementById("studioBuilderPanel");
  const tabBuilder = document.getElementById("studioTabBuilder");

  if (textPanel) textPanel.classList.toggle("is-hidden", studioMode !== "text");
  if (imagesPanel) imagesPanel.classList.toggle("is-hidden", studioMode !== "images");
  if (builderPanel) builderPanel.classList.toggle("is-hidden", studioMode !== "builder");

  if (tabText) {
    tabText.classList.toggle("is-active", studioMode === "text");
    tabText.setAttribute("aria-selected", studioMode === "text" ? "true" : "false");
  }
  if (tabImages) {
    tabImages.classList.toggle("is-active", studioMode === "images");
    tabImages.setAttribute("aria-selected", studioMode === "images" ? "true" : "false");
  }
  if (tabBuilder) {
    tabBuilder.classList.toggle("is-active", studioMode === "builder");
    tabBuilder.setAttribute("aria-selected", studioMode === "builder" ? "true" : "false");
  }

  if (studioMode === "text") {
    const input = document.getElementById("inputText");
    input?.focus?.();
  } else if (studioMode === "images") {
    const brief = document.getElementById("imageBrief");
    (brief || document.getElementById("inputText"))?.focus?.();
  } else {
    const input = document.getElementById("inputText");
    input?.focus?.();
  }
}

function clearSource() {
  const input = document.getElementById("inputText");
  if (!input) {
    return;
  }
  input.value = "";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  setResultsVisibility(false);
  clearChat();
}

function setImageUIState({ statusText, isBusy, images } = {}) {
  const statusEl = document.getElementById("imageStatus");
  const btn = document.getElementById("imageGenerateBtn");

  if (btn) {
    btn.classList.toggle("is-loading", !!isBusy);
    btn.disabled = !!isBusy;
    btn.textContent = isBusy ? "Generating..." : "Generate Images";
  }

  if (statusEl) {
    if (statusText) {
      statusEl.classList.remove("is-hidden");
      statusEl.textContent = statusText;
    } else {
      statusEl.classList.add("is-hidden");
      statusEl.textContent = "";
    }
  }
}

// Post Builder results are rendered into the same chat feed as other outputs.

async function startImageGeneration() {
  const remaining = Number(entitlements?.limits?.image_generations_remaining ?? 0);
  if (!entitlements?.is_premium && remaining <= 0) {
    showToast("Upgrade to Pro", "You have reached your image generation limit. Upgrade for more.", "error");
    openPremiumModal();
    return;
  }

  const briefRaw = document.getElementById("imageBrief")?.value?.trim() || "";
  const aspect = document.getElementById("imageAspect")?.value || "square";
  const style = document.getElementById("imageStyle")?.value?.trim() || "";
  const count = Number(document.getElementById("imageCount")?.value || 1);
  const sourceText = document.getElementById("inputText")?.value?.trim() || "";
  const brief = briefRaw || (sourceText ? `Create a post cover image for this content: ${sourceText.slice(0, 600)}` : "");

  if (!brief) {
    showToast("Missing brief", "Add a short visual brief or paste source content first.", "error");
    return;
  }

  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) {
    openAuthModal("signin");
    showToast("Authentication required", "Sign in to generate images.", "error");
    return;
  }

  addChatMessage({
    role: "user",
    title: "You",
    pill: "Images",
    text: `Generate ${count} image${count === 1 ? "" : "s"} · ${aspect}${style ? ` · ${style}` : ""}\n\n${brief}`,
  });
  addChatMessage({
    role: "assistant",
    title: "OrcaFind",
    pill: "Working",
    text: "Generating post images…",
  });

  setImageUIState({ statusText: "Generating image concepts…", isBusy: true, images: null });
  try {
    const payload = {
      brief,
      aspect,
      count: Math.max(1, Math.min(6, count)),
    };
    if (style) {
      payload.style = style;
    }

    const response = await fetch("https://api.orcafind.com/images/generate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}`,
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      if (response.status === 402 || response.status === 403) {
        openPremiumModal();
      }
      throw new Error(data?.detail || "Failed to generate images");
    }

    setImageUIState({ statusText: null, isBusy: false, images: null });
    const images = Array.isArray(data.images) ? data.images : [];
    if (!images.length) {
      addChatMessage({
        role: "assistant",
        title: "AI Images",
        pill: "Empty",
        text: "No images were returned. Try increasing the brief clarity and run again.",
      });
    } else {
      images.forEach((img, idx) => {
        const url = img?.data_url || "";
        if (!url) return;
        addChatMessage({
          role: "assistant",
          title: "AI Image",
          pill: `Option ${idx + 1}`,
          text: img?.label ? String(img.label) : "Post-ready image generated.",
          actionsHTML: `<a class="btn btn-secondary btn-mini" href="${url}" download="orcafind-post-${idx + 1}.png">Download</a>`,
          imageDataUrl: url,
        });
      });
    }
    showToast("Images ready", "Your post images are ready to download.", "success");
    supabaseClient.auth.getSession().then(({ data }) => fetchEntitlements(data?.session?.access_token));
  } catch (err) {
    setImageUIState({ statusText: null, isBusy: false, images: null });
    addChatMessage({
      role: "assistant",
      title: "AI Images",
      pill: "Failed",
      text: err.message || "Failed to generate images.",
    });
    showToast("Image failed", err.message || "Failed to generate images.", "error");
  }
}

async function startCompletePostGeneration() {
  if (!entitlements?.is_premium) {
    showToast("Pro feature", "Post Builder is available on Pro.", "error");
    openPremiumModal();
    return;
  }

  const text = document.getElementById("inputText")?.value?.trim() || "";
  if (!text) {
    showToast("Missing content", "Paste source content first.", "error");
    return;
  }

  const xStyle = document.getElementById("builderXStyle")?.value || "single";
  const format = document.getElementById("builderFormat")?.value || "professional";
  const aspect = document.getElementById("builderImageAspect")?.value || "square";
  const imageBrief = document.getElementById("builderImageBrief")?.value?.trim() || "";
  const imageStyle = document.getElementById("builderImageStyle")?.value?.trim() || "";

  const statusEl = document.getElementById("builderStatus");
  const btn = document.getElementById("builderGenerateBtn");
  if (btn) {
    btn.classList.add("is-loading");
    btn.disabled = true;
  }
  if (statusEl) {
    statusEl.classList.remove("is-hidden");
    statusEl.textContent = "Generating full post bundle…";
  }

  setResultsVisibility(true);

  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) {
    openAuthModal("signin");
    showToast("Authentication required", "Sign in to generate a complete post bundle.", "error");
    if (btn) {
      btn.classList.remove("is-loading");
      btn.disabled = false;
    }
    if (statusEl) statusEl.classList.add("is-hidden");
    return;
  }

  const payload = {
    text,
    x_style: xStyle,
    format,
    image_aspect: aspect,
    image_count: 1,
  };
  if (imageBrief) payload.image_brief = imageBrief;
  if (imageStyle) payload.image_style = imageStyle;

  try {
    const response = await fetch("https://api.orcafind.com/posts/complete", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}`,
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 402 || response.status === 403) {
        openPremiumModal();
      }
      throw new Error(data?.detail || "Failed to generate complete post");
    }

    const image = (data.images || [])[0] || null;
    addChatMessage({
      role: "assistant",
      title: "Post Builder",
      pill: "Bundle",
      text: "Generated a complete bundle: copy plus image.",
      actionsHTML: image?.data_url
        ? `<a class="btn btn-secondary btn-mini" href="${image.data_url}" download="orcafind-post-image.png">Download</a>`
        : "",
      imageDataUrl: image?.data_url || null,
    });

    const sections = {
      x: data.x || "",
      linkedin: data.linkedin || "",
      instagram: data.instagram || "",
      facebook: data.facebook || "",
    };

    if (sections.x) {
      const id = storeCopyText(sections.x);
      addChatMessage({
        role: "assistant",
        title: "Twitter / X",
        pill: "Copy",
        text: sections.x,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'X')">Copy</button>`,
      });
    }
    if (sections.linkedin) {
      const id = storeCopyText(sections.linkedin);
      addChatMessage({
        role: "assistant",
        title: "LinkedIn",
        pill: "Copy",
        text: sections.linkedin,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'LinkedIn')">Copy</button>`,
      });
    }
    if (sections.instagram) {
      const id = storeCopyText(sections.instagram);
      addChatMessage({
        role: "assistant",
        title: "Instagram",
        pill: "Caption",
        text: sections.instagram,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'Instagram')">Copy</button>`,
      });
    }
    if (sections.facebook) {
      const id = storeCopyText(sections.facebook);
      addChatMessage({
        role: "assistant",
        title: "Facebook",
        pill: "Caption",
        text: sections.facebook,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'Facebook')">Copy</button>`,
      });
    }

    showToast("Complete post ready", "Copy captions and download the image.", "success");
  } catch (err) {
    showToast("Post builder failed", err.message || "Failed to generate complete post.", "error");
  } finally {
    if (btn) {
      btn.classList.remove("is-loading");
      btn.disabled = false;
    }
    if (statusEl) {
      statusEl.classList.add("is-hidden");
      statusEl.textContent = "";
    }
  }
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

function openPremiumModal() {
  const modal = document.getElementById("premiumModal");
  if (modal) {
    modal.classList.add("is-visible");
    modal.setAttribute("aria-hidden", "false");
  }
}

function closePremiumModal() {
  const modal = document.getElementById("premiumModal");
  if (modal) {
    modal.classList.remove("is-visible");
    modal.setAttribute("aria-hidden", "true");
  }
}

function handlePremiumBackdrop(event) {
  if (event.target?.id === "premiumModal") {
    closePremiumModal();
  }
}

async function fetchEntitlements(accessToken) {
  if (!accessToken) {
    entitlements = {
      plan: "free",
      is_admin: false,
      is_premium: false,
      limits: {
        x_single_variants: 2,
        x_thread_tweets_min: 4,
        x_thread_tweets_max: 7,
        image_generations_total: 20,
        image_generations_used: 0,
        image_generations_remaining: 20,
      },
    };
    applyEntitlementsToUI();
    return entitlements;
  }

  try {
    const response = await fetch("https://api.orcafind.com/entitlements", {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${accessToken}`
      }
    });

    if (!response.ok) {
      throw new Error(`Entitlements error ${response.status}`);
    }

    entitlements = await response.json();
  } catch (err) {
    entitlements = {
      plan: "free",
      is_admin: false,
      is_premium: false,
      limits: {
        x_single_variants: 2,
        x_thread_tweets_min: 4,
        x_thread_tweets_max: 7,
        image_generations_total: 20,
        image_generations_used: 0,
        image_generations_remaining: 20,
      },
    };
  }

  applyEntitlementsToUI();
  return entitlements;
}

function applyEntitlementsToUI() {
  const format = document.getElementById("contentFormat");
  if (!format) {
    // Still allow non-studio pages to call this safely.
    const hint = document.getElementById("imageLimitHint");
    if (hint) {
      hint.textContent = "";
    }
    return;
  }

  const isPremium = !!entitlements?.is_premium;
  const isAdmin = !!entitlements?.is_admin || entitlements?.plan === "admin";
  if (!isPremium && format.options[format.selectedIndex]?.dataset?.premium === "true") {
    format.value = "professional";
    updateStudioOutputTags();
  }

  const hint = document.getElementById("imageLimitHint");
  if (hint) {
    if (isAdmin) {
      hint.textContent = "Admin: unlimited image generations enabled (testing mode).";
    } else if (isPremium) {
      hint.textContent = "Pro: higher image generation limits enabled.";
    } else {
      const remaining = Number(entitlements?.limits?.image_generations_remaining ?? 0);
      hint.textContent = `Free generations remaining: ${remaining}.`;
    }
  }

  const builderHint = document.getElementById("builderProHint");
  if (builderHint) {
    if (isAdmin) {
      builderHint.textContent = "Admin: Post Builder enabled (testing mode).";
    } else if (isPremium) {
      builderHint.textContent = "Pro: Generate a complete post bundle (copy + image).";
    } else {
      builderHint.textContent = "Upgrade to Pro to unlock Post Builder (copy + image in one run).";
    }
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
  // Studio page doesn't include the hero metrics.
  if (!document.getElementById("metricPrimaryValue")) {
    return;
  }
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

  outputTag.textContent = `Output: X ${xStyle.value === "single" ? "post variations" : "thread"} + LinkedIn`;
  formatTag.textContent = `Format: ${formatValue.replace("-", " ")}`;
}

function initStudioControls() {
  const xStyle = document.getElementById("xStyle");
  const format = document.getElementById("contentFormat");

  if (xStyle) {
    xStyle.addEventListener("change", updateStudioOutputTags);
  }
  if (format) {
    format.addEventListener("change", () => {
      const selected = format.options[format.selectedIndex];
      if (selected?.dataset?.premium === "true" && !entitlements?.is_premium) {
        showToast("Pro feature", "This format is available on Pro.", "error");
        format.value = "professional";
        updateStudioOutputTags();
        openPremiumModal();
        return;
      }
      updateStudioOutputTags();
    });
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

function setResultsVisibility(isVisible) {
  const output = document.getElementById("output");

  if (output) {
    output.classList.toggle("is-hidden", !isVisible);
  }
}

function escapeHTML(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const __orcafindCopyStore = {};
let __orcafindCopySeed = 0;

function storeCopyText(text) {
  const id = `copy_${Date.now()}_${__orcafindCopySeed++}`;
  __orcafindCopyStore[id] = String(text || "");
  return id;
}

function copyFromStore(id, label) {
  return copyText(__orcafindCopyStore[id] || "", label || "Text");
}

function clearChat() {
  const output = document.getElementById("output");
  if (!output) return;
  output.innerHTML = "";
}

function addChatMessage({ role, title, text, pill, actionsHTML, imageDataUrl } = {}) {
  const output = document.getElementById("output");
  if (!output) return;

  const isUser = role === "user";
  const row = document.createElement("div");
  row.className = `chat-row ${isUser ? "is-user" : "is-assistant"}`;

  const avatarHTML = isUser ? "" : `<div class="chat-avatar" aria-hidden="true">O</div>`;
  const safeTitle = escapeHTML(title || (isUser ? "You" : "OrcaFind"));
  const safePill = pill ? `<span class="chat-pill">${escapeHTML(pill)}</span>` : "";
  const safeText = text ? `<div class="chat-text">${escapeHTML(text)}</div>` : "";
  const imageHTML = imageDataUrl
    ? `<div class="chat-image"><img src="${imageDataUrl}" alt="Generated post image" /></div>`
    : "";
  const actions = actionsHTML ? `<div class="chat-actions">${actionsHTML}</div>` : "";

  row.innerHTML = `
    ${!isUser ? avatarHTML : ""}
    <div class="chat-bubble">
      <div class="chat-meta">
        <strong>${safeTitle}</strong>
        ${safePill}
        ${actions}
      </div>
      ${safeText}
      ${imageHTML}
    </div>
  `;

  output.appendChild(row);
  setResultsVisibility(true);
  // Scroll into view for long chats.
  row.scrollIntoView({ block: "end", behavior: "smooth" });
}

function parseSectionsFromText(raw) {
  const text = String(raw || "").trim();
  const headers = ["X", "LinkedIn", "Instagram", "Facebook"];
  const out = { x: "", linkedin: "", instagram: "", facebook: "" };
  if (!text) return out;

  const rx = /^(X|LinkedIn|Instagram|Facebook):\s*$/gim;
  const matches = [...text.matchAll(rx)];
  if (!matches.length) {
    // Legacy 2-section output.
    const parts = text.split(/LinkedIn:/i);
    out.x = parts[0].replace(/^X:\s*/i, "").trim();
    out.linkedin = (parts[1] || "").trim();
    return out;
  }

  for (let i = 0; i < matches.length; i++) {
    const header = matches[i][1];
    const start = matches[i].index + matches[i][0].length;
    const end = i + 1 < matches.length ? matches[i + 1].index : text.length;
    const chunk = text.slice(start, end).trim();
    if (header === "X") out.x = chunk;
    if (header === "LinkedIn") out.linkedin = chunk;
    if (header === "Instagram") out.instagram = chunk;
    if (header === "Facebook") out.facebook = chunk;
  }
  return out;
}

async function copyText(text, label) {
  if (!text || !text.trim()) {
    showToast("Nothing to copy", "Generate results first.", "error");
    return;
  }
  try {
    await navigator.clipboard.writeText(text.trim());
    showToast("Copied", `${label} copied to clipboard.`, "success");
  } catch (_err) {
    showToast("Copy failed", "Your browser blocked clipboard access.", "error");
  }
}

async function copyPlatform(which) {
  const text = which === "linkedin" ? lastGenerated.linkedin : lastGenerated.x;
  if (!text || !text.trim()) {
    showToast("Nothing to copy", "Generate results first.", "error");
    return;
  }

  try {
    await navigator.clipboard.writeText(text.trim());
    showToast("Copied", `${which === "linkedin" ? "LinkedIn" : "X"} content copied to clipboard.`, "success");
  } catch (err) {
    showToast("Copy failed", "Your browser blocked clipboard access.", "error");
  }
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
  supabaseClient.auth.getSession().then(({ data }) => fetchEntitlements(data?.session?.access_token));

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
  setResultsVisibility(false);
  fetchEntitlements(null);
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
  setResultsVisibility(false);
  supabaseClient.auth.getSession().then(({ data }) => fetchEntitlements(data?.session?.access_token));
  setImageUIState({ statusText: null, isBusy: false, images: null });

  try {
    const savedMode = window.localStorage.getItem("orcafind_studio_mode");
    if (savedMode === "images" || savedMode === "builder" || savedMode === "text") {
      studioMode = savedMode;
    }
  } catch (_err) {}
  setStudioMode(studioMode);

  const headerProfile = document.getElementById("headerProfile");
  if (headerProfile) {
    headerProfile.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openProfileModal();
      }
    });
  }

  const params = new URLSearchParams(window.location.search);
  const auth = params.get("auth");
  if (auth === "signin" || auth === "signup") {
    openAuthModal(auth);
  }
});

/* ---------- GENERATE ---------- */

async function generate() {
  const text = document.getElementById("inputText").value;
  const button = document.getElementById("generateBtn");
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
  addChatMessage({
    role: "user",
    title: "You",
    pill: "Source",
    text: text.trim().slice(0, 900),
  });
  addChatMessage({
    role: "assistant",
    title: "OrcaFind",
    pill: "Working",
    text: "Generating X, LinkedIn, Instagram, and Facebook captions from your source content…",
  });

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
      addChatMessage({
        role: "assistant",
        title: "Error",
        pill: "Failed",
        text: data.detail || "API Error",
      });
      showToast("Generation failed", data.detail || "API Error", "error");
      return;
    }

    const sections = data.sections || parseSectionsFromText(data.result);
    const xText = (sections.x || "").trim();
    const linkedinText = (sections.linkedin || "").trim();
    const instagramText = (sections.instagram || "").trim();
    const facebookText = (sections.facebook || "").trim();

    lastGenerated = { x: xText, linkedin: linkedinText };

    if (xText) {
      const id = storeCopyText(xText);
      addChatMessage({
        role: "assistant",
        title: "Twitter / X",
        pill: xStyle === "single" ? "Variations" : "Thread",
        text: xText,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'X')">Copy</button>`,
      });
    }
    if (linkedinText) {
      const id = storeCopyText(linkedinText);
      addChatMessage({
        role: "assistant",
        title: "LinkedIn",
        pill: "Formatted",
        text: linkedinText,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'LinkedIn')">Copy</button>`,
      });
    }
    if (instagramText) {
      const id = storeCopyText(instagramText);
      addChatMessage({
        role: "assistant",
        title: "Instagram",
        pill: "Caption",
        text: instagramText,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'Instagram')">Copy</button>`,
      });
    }
    if (facebookText) {
      const id = storeCopyText(facebookText);
      addChatMessage({
        role: "assistant",
        title: "Facebook",
        pill: "Caption",
        text: facebookText,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'Facebook')">Copy</button>`,
      });
    }

    showToast("Generated", "Your captions are ready.", "success");

  } catch (err) {
    addChatMessage({
      role: "assistant",
      title: "Connection Error",
      pill: "Offline",
      text: `Error connecting to API: ${err.message}`,
    });
    showToast("Connection error", `Error connecting to API: ${err.message}`, "error");
  } finally {
    button.innerText = "Generate Posts";
    button.disabled = false;
  }
}

/* ---------- UTILS ---------- */

// Intentionally no "Copy all results" button; each platform card has its own copy action.
