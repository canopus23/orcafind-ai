const ORCAFIND_CONFIG = window.__ORCAFIND_CONFIG || {};
const SUPABASE_URL = ORCAFIND_CONFIG.supabaseUrl || window.__ORCAFIND_SUPABASE_URL || "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = ORCAFIND_CONFIG.supabaseAnonKey || window.__ORCAFIND_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
const API_BASE_URL = ORCAFIND_CONFIG.apiBaseUrl || window.__ORCAFIND_API_BASE_URL
  || (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://127.0.0.1:8000"
    : "https://api.orcafind.com");

function isAuthPage() {
  return window.location.pathname === "/auth" || window.location.pathname.startsWith("/auth/");
}

function buildRelativeUrl({ stripParams = [] } = {}) {
  const url = new URL(window.location.href);
  stripParams.forEach((key) => url.searchParams.delete(key));
  const qs = url.searchParams.toString();
  return `${url.pathname}${qs ? `?${qs}` : ""}${url.hash || ""}`;
}

function getSafeNextFromURL() {
  const next = (new URLSearchParams(window.location.search).get("next") || "").trim();
  // Only allow same-origin relative paths.
  if (next && next.startsWith("/") && !next.startsWith("//") && !next.includes("://")) {
    if (next === "/auth" || next.startsWith("/auth/")) return "/studio/";
    return next;
  }
  return null;
}

function redirectToAuth(mode, next) {
  if (isAuthPage()) return;
  const params = new URLSearchParams();
  params.set("mode", mode === "signup" ? "signup" : "signin");
  params.set("next", next || buildRelativeUrl({ stripParams: ["auth"] }));
  window.location.href = `/auth/?${params.toString()}`;
}

async function getAccessTokenOrPromptAuth({ toastTitle, toastBody, mode } = {}) {
  let { data: { session } } = await supabaseClient.auth.getSession();
  let token = session?.access_token;
  if (token) return token;
  try {
    await supabaseClient.auth.refreshSession();
    ({ data: { session } } = await supabaseClient.auth.getSession());
    token = session?.access_token;
    if (token) return token;
  } catch (_err) {}
  if (mode) redirectToAuth(mode, buildRelativeUrl({ stripParams: ["auth"] }));
  if (!mode && (toastTitle || toastBody)) {
    showToast(toastTitle || "Authentication required", toastBody || "Sign in to continue.", "error");
  }
  return null;
}
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
    image_generations_total: 0,
    image_generations_used: 0,
    image_generations_remaining: 0,
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
  studioMode = mode === "images" ? "images" : mode === "builder" ? "builder" : mode === "vision" ? "vision" : "text";
  try {
    window.localStorage.setItem("orcafind_studio_mode", studioMode);
  } catch (_err) {}

  if (studioMode === "vision") {
    setText("studioModeHeadline", "Turn any image into social-ready drafts.");
    setText(
      "studioModeCopy",
      "Upload an image and generate multiple X variations, a LinkedIn draft, plus Instagram and Facebook captions based on what the image shows."
    );
  } else if (studioMode === "images") {
    setText("studioModeHeadline", "Generate post-ready visuals from a short brief.");
    setText("studioModeCopy", "Create post-ready images from a short visual brief plus your source content.");
  } else if (studioMode === "builder") {
    setText("studioModeHeadline", "Generate a complete post bundle.");
    setText("studioModeCopy", "Generate a complete post bundle: platform copy plus a matching image.");
  } else {
    setText("studioModeHeadline", "Generate polished posts from one source of truth.");
    setText(
      "studioModeCopy",
      "Paste an article, transcript, release note, or raw idea. OrcaFind will convert it into social-ready drafts designed for distribution."
    );
  }

  const textPanel = document.getElementById("studioTextPanel");
  const visionPanel = document.getElementById("studioVisionPanel");
  const imagesPanel = document.getElementById("studioImagesPanel");
  const tabText = document.getElementById("studioTabText");
  const tabVision = document.getElementById("studioTabVision");
  const tabImages = document.getElementById("studioTabImages");
  const builderPanel = document.getElementById("studioBuilderPanel");
  const tabBuilder = document.getElementById("studioTabBuilder");
  const workspaceFrame = document.getElementById("workspaceFrame");
  const studioBody = document.getElementById("studioBody");

  if (textPanel) textPanel.classList.toggle("is-hidden", studioMode !== "text");
  if (visionPanel) visionPanel.classList.toggle("is-hidden", studioMode !== "vision");
  if (imagesPanel) imagesPanel.classList.toggle("is-hidden", studioMode !== "images");
  if (builderPanel) builderPanel.classList.toggle("is-hidden", studioMode !== "builder");
  if (workspaceFrame) workspaceFrame.classList.toggle("is-hidden", studioMode === "vision");
  if (studioBody) studioBody.classList.toggle("is-vision", studioMode === "vision");

  if (tabText) {
    tabText.classList.toggle("is-active", studioMode === "text");
    tabText.setAttribute("aria-selected", studioMode === "text" ? "true" : "false");
  }
  if (tabVision) {
    tabVision.classList.toggle("is-active", studioMode === "vision");
    tabVision.setAttribute("aria-selected", studioMode === "vision" ? "true" : "false");
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
  } else if (studioMode === "vision") {
    const img = document.getElementById("visionImage");
    img?.focus?.();
  } else if (studioMode === "images") {
    const brief = document.getElementById("imageBrief");
    (brief || document.getElementById("inputText"))?.focus?.();
  } else {
    const input = document.getElementById("inputText");
    input?.focus?.();
  }

  // Keep the mobile dock in sync with the active studio mode.
  updateStudioMobileDock();
  if (isStudioMobileViewport()) {
    const currentView = studioBody?.dataset?.view || "source";
    if (currentView !== "results") {
      setStudioMobileView(studioMode === "vision" ? "options" : currentView === "options" ? "options" : "source");
    }
  }
}

function isStudioMobileViewport() {
  try {
    return window.matchMedia && window.matchMedia("(max-width: 820px)").matches;
  } catch (_err) {
    return false;
  }
}

function setStudioMobileView(view) {
  const body = document.getElementById("studioBody");
  if (!body) return;

  let next = view === "options" ? "options" : view === "results" ? "results" : "source";
  if (studioMode === "vision" && next === "source") {
    next = "options";
  }
  body.dataset.view = next;

  const tabMap = {
    source: "dockTabSource",
    options: "dockTabOptions",
    results: "dockTabResults",
  };

  Object.entries(tabMap).forEach(([key, id]) => {
    const tab = document.getElementById(id);
    if (!tab) return;
    const isActive = key === next;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", isActive ? "true" : "false");
  });
}

function updateStudioMobileDock() {
  const dock = document.getElementById("mobileDock");
  const primary = document.getElementById("mobileDockPrimary");
  const label = document.getElementById("mobileDockPrimaryLabel");
  if (!dock || !primary || !label) return;

  const shouldShow = isStudioMobileViewport();
  dock.setAttribute("aria-hidden", shouldShow ? "false" : "true");
  if (!shouldShow) {
    const resultsCard = document.getElementById("resultsCard");
    if (resultsCard?.dataset?.hasResults !== "true") {
      resultsCard?.classList?.add("is-hidden");
    }
    closeStudioOptions();
    return;
  }

  const body = document.getElementById("studioBody");
  setStudioMobileView(body?.dataset?.view || "source");

  let text = "Generate posts";
  if (studioMode === "vision") text = "Generate from image";
  if (studioMode === "images") text = "Generate images";
  if (studioMode === "builder") text = "Generate bundle";
  label.textContent = text;

  const map = {
    text: "generateBtn",
    vision: "visionGenerateBtn",
    images: "imageGenerateBtn",
    builder: "builderGenerateBtn",
  };
  const sourceBtn = document.getElementById(map[studioMode] || "");
  const isBusy = !!sourceBtn?.classList?.contains("is-loading") || !!sourceBtn?.disabled;
  primary.disabled = isBusy;
}

function openStudioOptions() {
  if (isStudioMobileViewport()) {
    setStudioMobileView("options");
    return;
  }

  document.querySelector(".studio-aside")?.scrollIntoView?.({ block: "start", behavior: "smooth" });
}

function closeStudioOptions() {
  const backdrop = document.getElementById("studioOptionsBackdrop");
  backdrop?.classList?.remove("is-open");
  backdrop?.setAttribute?.("aria-hidden", "true");
}

function runStudioMobilePrimary() {
  closeStudioOptions();
  if (studioMode === "vision") return generateFromImage();
  if (studioMode === "images") return startImageGeneration();
  if (studioMode === "builder") return startCompletePostGeneration();
  return generate();
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file) return resolve("");
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}

function canvasToBlob(canvas, mimeType, quality) {
  return new Promise((resolve) => {
    try {
      canvas.toBlob(
        (blob) => resolve(blob || null),
        mimeType,
        typeof quality === "number" ? quality : undefined,
      );
    } catch (_err) {
      resolve(null);
    }
  });
}

async function decodeImageFromFile(file) {
  if (!file) return null;
  if (window.createImageBitmap) {
    try {
      return await window.createImageBitmap(file);
    } catch (_err) {}
  }

  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.decoding = "async";
    img.src = url;
    await new Promise((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error("Failed to load image"));
    });
    return img;
  } catch (_err) {
    return null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function optimizeImageForVisionUpload(file) {
  // Vision model cost scales primarily with resolution (pixels), not original file size.
  // Goal: downscale to a "medium" resolution and compress into a modern format.
  const bitmapOrImg = await decodeImageFromFile(file);
  if (!bitmapOrImg) return { file, optimized: false };

  const originalWidth = bitmapOrImg.width || 0;
  const originalHeight = bitmapOrImg.height || 0;
  const originalMax = Math.max(originalWidth, originalHeight);
  if (!originalWidth || !originalHeight) return { file, optimized: false };

  // Default to 1024px max side ("medium"). If still heavy, we step down further.
  const targetMaxSides = [1024, 768];
  const mimeCandidates = ["image/webp", "image/jpeg"];

  let bestFile = file;
  let bestSize = file.size || Number.MAX_SAFE_INTEGER;

  for (const maxSide of targetMaxSides) {
    const scale = Math.min(1, maxSide / originalMax);
    const width = Math.max(1, Math.round(originalWidth * scale));
    const height = Math.max(1, Math.round(originalHeight * scale));

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) continue;

    // Fill background so JPEG doesn't render black where PNG had transparency.
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, width, height);
    try {
      ctx.drawImage(bitmapOrImg, 0, 0, width, height);
    } catch (_err) {
      continue;
    }

    for (const mimeType of mimeCandidates) {
      // Try a few quality levels to keep the upload light.
      for (const quality of [0.82, 0.74, 0.66]) {
        const blob = await canvasToBlob(canvas, mimeType, quality);
        if (!blob) continue;

        const sized = blob.size || 0;
        if (sized && sized < bestSize) {
          const ext = mimeType === "image/webp" ? "webp" : "jpg";
          const name = (file.name || "upload").replace(/\.[a-z0-9]+$/i, `.${ext}`);
          bestFile = new File([blob], name, { type: mimeType });
          bestSize = sized;
        }

        // Stop early if we reached a reasonably small payload.
        if (sized > 0 && sized <= 900 * 1024) break;
      }
    }

    // Stop early if we already hit our target size.
    if (bestSize <= 900 * 1024) break;
  }

  const optimized = bestFile !== file;
  return {
    file: bestFile,
    optimized,
    originalBytes: file.size || 0,
    optimizedBytes: bestFile.size || 0,
  };
}

async function generateFromImage() {
  const imageInput = document.getElementById("visionImage");
  const promptInput = document.getElementById("visionPrompt");
  const xStyleInput = document.getElementById("visionXStyle");
  const formatInput = document.getElementById("visionFormat");
  const button = document.getElementById("visionGenerateBtn");

  const accessToken = await getAccessTokenOrPromptAuth({
    mode: "signin",
    toastTitle: "Authentication required",
    toastBody: "Sign in to generate posts from an image.",
  });
  if (!accessToken) return;

  const visionRemaining = Number(entitlements?.limits?.image_to_posts_remaining ?? 0);
  if (!entitlements?.is_admin && visionRemaining <= 0) {
    showToast("Limit reached", "You have reached your image-to-posts limit. Upgrade to Pro for more.", "error");
    openPremiumModal();
    return;
  }

  const file = imageInput?.files?.[0];
  if (!file) {
    showToast("Missing image", "Upload an image to generate from.", "error");
    return;
  }

  if (file.type && !file.type.startsWith("image/")) {
    showToast("Unsupported file", "Please upload a PNG, JPG, or WebP image.", "error");
    return;
  }

  if (file.size > 6 * 1024 * 1024) {
    showToast("Image too large", "Please upload a smaller file (max 6MB).", "error");
    return;
  }

  const userPrompt = String(promptInput?.value || "").trim();
  const xStyle = String(xStyleInput?.value || "single").trim();
  const format = String(formatInput?.value || "professional").trim();

  if (formatInput) {
    const selected = formatInput.options[formatInput.selectedIndex];
    if (selected?.dataset?.premium === "true" && !entitlements?.is_premium) {
      showToast("Pro feature", "This format is available on Pro.", "error");
      formatInput.value = "professional";
      openPremiumModal();
      return;
    }
  }

  button && (button.disabled = true);
  if (button) {
    button.classList.add("is-loading");
    button.textContent = "Generating...";
  }

  let previewUrl = "";
  try {
    previewUrl = await readFileAsDataUrl(file);
  } catch (_err) {
    previewUrl = "";
  }

  addChatMessage({
    role: "user",
    title: "You",
    pill: "Image",
    text: userPrompt ? `Guidance: ${userPrompt}` : "Generate posts based on this image.",
    imageDataUrl: previewUrl,
  });

  const typingId = addTypingMessage({
    title: "OrcaFind",
    pill: "Working",
    label: "Analyzing image and writing posts...",
  });

  try {
    // Optimize the upload to reduce pixel resolution (and thus vision token cost).
    let uploadFile = file;
    try {
      const optimized = await optimizeImageForVisionUpload(file);
      if (optimized?.file) {
        uploadFile = optimized.file;
        if (optimized.optimized) {
          showToast(
            "Image optimized",
            `Reduced upload size from ${Math.round((optimized.originalBytes || 0) / 1024)}KB to ${Math.round((optimized.optimizedBytes || 0) / 1024)}KB.`,
            "success",
          );
        }
      }
    } catch (_err) {
      uploadFile = file;
    }

    const form = new FormData();
    form.append("image", uploadFile);
    form.append("prompt", userPrompt);
    form.append("x_style", xStyle);
    form.append("format", format);

    const response = await fetch(`${API_BASE_URL}/repurpose/image`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${accessToken}`,
      },
      body: form,
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      removeChatMessage(typingId);
      if (response.status === 401) {
        redirectToAuth("signin", buildRelativeUrl());
        showToast("Session expired", "Please sign in again to continue.", "error");
        return;
      }
      if (response.status === 402) {
        showToast("Pro required", data.detail?.message || data.detail || "Upgrade to Pro to use image-based generation.", "error");
        openPremiumModal();
        return;
      }
      const detail = data.detail?.message || data.detail || "API Error";
      addChatMessage({ role: "assistant", title: "Error", pill: "Failed", text: detail });
      showToast("Generation failed", detail, "error");
      return;
    }

    removeChatMessage(typingId);
    const sections = data.sections || parseSectionsFromText(data.result);
    const xText = (sections.x || "").trim();
    const linkedinText = (sections.linkedin || "").trim();
    const instagramText = (sections.instagram || "").trim();
    const facebookText = (sections.facebook || "").trim();

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

    showToast("Generated", "Your image-based posts and captions are ready.", "success");
  } catch (err) {
    removeChatMessage(typingId);
    addChatMessage({
      role: "assistant",
      title: "Connection Error",
      pill: "Offline",
      text: `Error connecting to API: ${err.message}`,
    });
    showToast("Connection error", `Error connecting to API: ${err.message}`, "error");
  } finally {
    if (button) {
      button.classList.remove("is-loading");
      button.disabled = false;
      button.textContent = "Generate From Image";
    }
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

function compressSourceForImage(text, maxChars) {
  const cleaned = String(text || "").replace(/\s+/g, " ").trim();
  if (!cleaned) return "";
  const limit = Math.max(120, Number(maxChars) || 520);
  if (cleaned.length <= limit) return cleaned;
  return `${cleaned.slice(0, limit - 3)}...`;
}

function buildImageBrief({ sourceText, visualBrief, maxSourceChars } = {}) {
  const source = compressSourceForImage(sourceText, maxSourceChars || 520);
  const visual = String(visualBrief || "").trim();

  if (source && visual) {
    return `Use BOTH the source context and the visual brief.\n\nSource context:\n${source}\n\nVisual brief:\n${visual}`;
  }
  if (visual) {
    return visual;
  }
  if (source) {
    return `Create a post cover image for this content:\n${source}`;
  }
  return "";
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
  if (!entitlements?.is_admin && remaining <= 0) {
    showToast("Limit reached", "You have reached your image generation limit. Upgrade to Pro for more.", "error");
    openPremiumModal();
    return;
  }

  const briefRaw = document.getElementById("imageBrief")?.value?.trim() || "";
  const aspect = document.getElementById("imageAspect")?.value || "square";
  const style = document.getElementById("imageStyle")?.value?.trim() || "";
  let count = Number(document.getElementById("imageCount")?.value || 1);
  if (!entitlements?.is_admin && !entitlements?.is_premium && count > 1) {
    count = 1;
    showToast("Free plan", "Free plan generates 1 image per request. Upgrade for multi-image runs.", "default");
  }
  const sourceText = document.getElementById("inputText")?.value?.trim() || "";
  const brief = buildImageBrief({ sourceText, visualBrief: briefRaw, maxSourceChars: 900 });

  if (!brief) {
    showToast("Missing brief", "Add a short visual brief or paste source content first.", "error");
    return;
  }

  const accessToken = await getAccessTokenOrPromptAuth({
    mode: "signin",
    toastTitle: "Authentication required",
    toastBody: "Sign in to generate images.",
  });
  if (!accessToken) return;

  addChatMessage({
    role: "user",
    title: "You",
    pill: "Images",
    text: `Generate ${count} image${count === 1 ? "" : "s"} · ${aspect}${style ? ` · ${style}` : ""}\n\n${brief}`,
  });
  const typingId = addTypingMessage({
    title: "OrcaFind",
    pill: "Working",
    label: "Generating post images...",
  });

  setImageUIState({ statusText: "Generating image concepts...", isBusy: true, images: null });
  try {
    const payload = {
      brief,
      aspect,
      count: Math.max(1, Math.min(3, count)),
    };
    if (style) {
      payload.style = style;
    }

    const response = await fetch(`${API_BASE_URL}/images/generate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        openAuthModal("signin");
        showToast("Session expired", "Please sign in again to continue.", "error");
      }
      removeChatMessage(typingId);
      if (response.status === 402 || response.status === 403) {
        openPremiumModal();
      }
      throw new Error(data?.detail || "Failed to generate images");
    }

    removeChatMessage(typingId);
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
        const url = img?.url || img?.data_url || "";
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
    removeChatMessage(typingId);
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
  const remainingBuilder = Number(entitlements?.limits?.post_builder_remaining ?? 0);
  const remainingImages = Number(entitlements?.limits?.image_generations_remaining ?? 0);
  if (!entitlements?.is_admin && (remainingBuilder <= 0 || remainingImages <= 0)) {
    showToast("Limit reached", "You have reached your Post Builder or image limit. Upgrade to Pro for more.", "error");
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
    statusEl.textContent = "Generating full post bundle...";
  }

  setResultsVisibility(true);

  const accessToken = await getAccessTokenOrPromptAuth({
    mode: "signin",
    toastTitle: "Authentication required",
    toastBody: "Sign in to generate a complete post bundle.",
  });
  if (!accessToken) {
    if (btn) {
      btn.classList.remove("is-loading");
      btn.disabled = false;
    }
    if (statusEl) statusEl.classList.add("is-hidden");
    return;
  }

  addChatMessage({
    role: "user",
    title: "You",
    pill: "Post Builder",
    text: `Generate a complete post bundle · X: ${xStyle === "single" ? "Variations" : "Thread"} · Format: ${format}`,
  });
  const typingId = addTypingMessage({
    title: "Post Builder",
    pill: "Working",
    label: "Generating copy and image...",
  });

  const payload = {
    text,
    x_style: xStyle,
    format,
    image_aspect: aspect,
    image_count: 1,
  };
  const combinedBrief = buildImageBrief({ sourceText: text, visualBrief: imageBrief, maxSourceChars: 420 });
  if (combinedBrief) payload.image_brief = combinedBrief;
  if (imageStyle) payload.image_style = imageStyle;

  try {
    const response = await fetch(`${API_BASE_URL}/posts/complete`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}`,
      },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        openAuthModal("signin");
        showToast("Session expired", "Please sign in again to continue.", "error");
      }
      removeChatMessage(typingId);
      if (response.status === 402 || response.status === 403) {
        openPremiumModal();
      }
      throw new Error(data?.detail || "Failed to generate complete post");
    }

    removeChatMessage(typingId);
    const image = (data.images || [])[0] || null;
    const imageUrl = image?.url || image?.data_url || null;
    if (imageUrl) {
      addChatMessage({
        role: "assistant",
        title: "Post Image",
        pill: "Pro",
        text: "Generated a post-ready image for this bundle.",
        actionsHTML: `<a class="btn btn-secondary btn-mini" href="${imageUrl}" download="orcafind-post-image.png">Download</a>`,
        imageDataUrl: imageUrl,
      });
    }

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
        pill: xStyle === "single" ? "Variations" : "Thread",
        text: sections.x,
        actionsHTML: `<button class="btn btn-ghost btn-mini" onclick="copyFromStore('${id}', 'X')">Copy</button>`,
      });
    }
    if (sections.linkedin) {
      const id = storeCopyText(sections.linkedin);
      addChatMessage({
        role: "assistant",
        title: "LinkedIn",
        pill: "Post",
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
    removeChatMessage(typingId);
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
      ? "Continue with Google or X to access your OrcaFind workspace."
      : "Continue with Google or X to create your OrcaFind workspace."
  );
  setText("primaryAuthAction", authMode === "signin" ? "Sign In" : "Create Account");
}

function openAuthModal(mode = "signin") {
  redirectToAuth(mode, buildRelativeUrl({ stripParams: ["auth"] }));
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
  // Profile is now a dedicated page.
  window.location.href = "/profile/";
}

function closeProfileModal() {
  const modal = document.getElementById("profileModal");
  if (modal) {
    modal.classList.remove("is-visible");
    modal.setAttribute("aria-hidden", "true");
  }
}

function openStudioSidebar() {
  const panel = document.getElementById("studioSidebar");
  const backdrop = document.getElementById("studioSidebarBackdrop");
  if (panel) {
    panel.classList.add("is-open");
    panel.setAttribute("aria-hidden", "false");
  }
  if (backdrop) backdrop.classList.add("is-open");
}

function closeStudioSidebar() {
  const panel = document.getElementById("studioSidebar");
  const backdrop = document.getElementById("studioSidebarBackdrop");
  if (panel) {
    panel.classList.remove("is-open");
    panel.setAttribute("aria-hidden", "true");
  }
  if (backdrop) backdrop.classList.remove("is-open");
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
  // Best-effort cache so the UI doesn't fall back to "free" after a successful payment
  // due to transient network errors.
  const dirtyAt = Number(window.localStorage.getItem("orcafind_entitlements_dirty") || "0");
  try {
    const cached = JSON.parse(window.localStorage.getItem("orcafind_entitlements_cache") || "null");
    if (cached?.entitlements && typeof cached?.at === "number") {
      const cacheFresh = Date.now() - cached.at < 7 * 24 * 60 * 60 * 1000;
      // If checkout marked entitlements as dirty, don't trust older cache.
      const cacheNotStaleForDirty = !dirtyAt || cached.at >= dirtyAt;
      if (cacheFresh && cacheNotStaleForDirty) {
        entitlements = cached.entitlements;
        applyEntitlementsToUI();
      }
    }
  } catch (_err) {}

  if (!accessToken) {
    entitlements = {
      plan: "free",
      is_admin: false,
      is_premium: false,
      limits: {
        x_single_variants: 2,
        x_thread_tweets_min: 4,
        x_thread_tweets_max: 7,
        text_posts_total: 60,
        text_posts_used: 0,
        text_posts_remaining: 60,
        image_to_posts_total: 5,
        image_to_posts_used: 0,
        image_to_posts_remaining: 5,
        post_builder_total: 0,
        post_builder_used: 0,
        post_builder_remaining: 0,
        image_generations_total: 0,
        image_generations_used: 0,
        image_generations_remaining: 0,
      },
    };
    applyEntitlementsToUI();
    return entitlements;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/entitlements`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${accessToken}`
      }
    });

    if (!response.ok) {
      throw new Error(`Entitlements error ${response.status}`);
    }

    entitlements = await response.json();
    try {
      window.localStorage.setItem(
        "orcafind_entitlements_cache",
        JSON.stringify({ at: Date.now(), entitlements })
      );
      if (dirtyAt) {
        window.localStorage.removeItem("orcafind_entitlements_dirty");
      }
    } catch (_err) {}
  } catch (err) {
    // Keep the last known entitlements if we have them; otherwise fall back to free.
    if (!entitlements?.plan) {
      entitlements = {
        plan: "free",
        is_admin: false,
        is_premium: false,
        limits: {
          x_single_variants: 2,
          x_thread_tweets_min: 4,
          x_thread_tweets_max: 7,
          text_posts_total: 60,
          text_posts_used: 0,
          text_posts_remaining: 60,
          image_to_posts_total: 5,
          image_to_posts_used: 0,
          image_to_posts_remaining: 5,
          post_builder_total: 0,
          post_builder_used: 0,
          post_builder_remaining: 0,
          image_generations_total: 0,
          image_generations_used: 0,
          image_generations_remaining: 0,
        },
      };
    }
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

  const visionFormat = document.getElementById("visionFormat");
  if (visionFormat && !isPremium && visionFormat.options[visionFormat.selectedIndex]?.dataset?.premium === "true") {
    visionFormat.value = "professional";
  }

  const hint = document.getElementById("imageLimitHint");
  if (hint) {
    const remaining = Number(entitlements?.limits?.image_generations_remaining ?? 0);
    const planLabel = String(entitlements?.plan || (isPremium ? "pro" : "free"))
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    if (isAdmin) {
      hint.textContent = "Admin: unlimited image generation enabled.";
    } else if (remaining > 0) {
      hint.textContent = `${planLabel}: ${remaining} image${remaining === 1 ? "" : "s"} remaining this month.`;
    } else {
      hint.textContent = "Image limit reached. Upgrade to Pro for more.";
    }
  }

  const builderHint = document.getElementById("builderProHint");
  if (builderHint) {
    const remaining = Number(entitlements?.limits?.post_builder_remaining ?? 0);
    const planLabel = String(entitlements?.plan || (isPremium ? "pro" : "free"))
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
    if (isAdmin) {
      builderHint.textContent = "Admin: unlimited Post Builder enabled.";
    } else if (remaining > 0) {
      builderHint.textContent = `${planLabel}: ${remaining} Post Builder run${remaining === 1 ? "" : "s"} remaining this month.`;
    } else {
      builderHint.textContent = "Post Builder limit reached. Upgrade to Pro for more.";
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
  const summary = document.getElementById("generationSummary");

  if (!xStyle || !format || !summary) {
    return;
  }

  const xLabel = xStyle.value === "single" ? "post variations" : "thread";
  const formatValue = (format.value || "professional").replace("-", " ");
  summary.textContent = `This run generates: X ${xLabel} + LinkedIn post draft, plus Instagram and Facebook captions · Format: ${formatValue}.`;
}

function initStudioControls() {
  const xStyle = document.getElementById("xStyle");
  const format = document.getElementById("contentFormat");
  const visionFormat = document.getElementById("visionFormat");

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

  if (visionFormat) {
    visionFormat.addEventListener("change", () => {
      const selected = visionFormat.options[visionFormat.selectedIndex];
      if (selected?.dataset?.premium === "true" && !entitlements?.is_premium) {
        showToast("Pro feature", "This format is available on Pro.", "error");
        visionFormat.value = "professional";
        openPremiumModal();
      }
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
      const href = (link.getAttribute("href") || "").trim();
      // Only hash links (e.g. "#platform") can be used as selectors.
      if (!href.startsWith("#")) {
        return null;
      }
      const target = document.querySelector(href);
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
  const resultsCard = document.getElementById("resultsCard");

  if (resultsCard) {
    resultsCard.dataset.hasResults = isVisible ? "true" : "false";
    if (isStudioMobileViewport()) {
      resultsCard.classList.remove("is-hidden");
    } else {
      resultsCard.classList.toggle("is-hidden", !isVisible);
    }
  }

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
let __orcafindChatSeed = 0;

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

function removeChatMessage(messageId) {
  const output = document.getElementById("output");
  if (!output || !messageId) return;
  const node = output.querySelector(`[data-message-id="${CSS.escape(String(messageId))}"]`);
  if (node) node.remove();
}

function addTypingMessage({ title, pill, label } = {}) {
  const safeLabel = escapeHTML(label || "Generating...");
  const body = `
    <div class="typing" role="status" aria-live="polite">
      <span>${safeLabel}</span>
      <span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span>
    </div>
  `.trim();
  return addChatMessage({
    role: "assistant",
    title: title || "OrcaFind",
    pill: pill || "Working",
    html: body,
  });
}

function addChatMessage({ id, role, title, text, html, pill, actionsHTML, imageDataUrl } = {}) {
  const output = document.getElementById("output");
  if (!output) return;

  const isUser = role === "user";
  const messageId = id || `msg_${Date.now()}_${__orcafindChatSeed++}`;
  const row = document.createElement("div");
  row.dataset.messageId = messageId;
  row.className = `chat-row ${isUser ? "is-user" : "is-assistant"}`;

  const avatarHTML = isUser ? "" : `<div class="chat-avatar" aria-hidden="true">O</div>`;
  const safeTitle = escapeHTML(title || (isUser ? "You" : "OrcaFind"));
  const safePill = pill ? `<span class="chat-pill">${escapeHTML(pill)}</span>` : "";
  const safeText = text ? `<div class="chat-text">${escapeHTML(text)}</div>` : "";
  const safeHTML = html ? `<div class="chat-text">${html}</div>` : "";
  const imageHTML = imageDataUrl
    ? `<div class="chat-image"><img src="${imageDataUrl}" alt="Image" /></div>`
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
      ${safeHTML || safeText}
      ${imageHTML}
    </div>
  `;

  output.appendChild(row);
  setResultsVisibility(true);
  // Scroll into view for long chats.
  row.scrollIntoView({ block: "end", behavior: "smooth" });
  if (!isUser && isStudioMobileViewport() && pill !== "Working") {
    setStudioMobileView("results");
  }
  return messageId;
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
    if (isAuthPage()) {
      const next = getSafeNextFromURL() || "/studio/";
      // Give Supabase a beat to persist the session before navigating away.
      Promise.resolve()
        .then(() => supabaseClient.auth.getSession())
        .catch(() => null)
        .finally(() => {
          window.setTimeout(() => {
            window.location.href = next;
          }, 180);
        });
    }
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
  const sideOut = document.getElementById("studioSideSignedOut");
  const sideIn = document.getElementById("studioSideSignedIn");
  const footerSignIn = document.getElementById("footerAccountSignIn");
  const footerSignOut = document.getElementById("footerAccountSignOut");
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
  if (sideOut) {
    sideOut.style.display = "none";
  }
  if (sideIn) {
    sideIn.style.display = "grid";
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
  setText("studioSideName", displayName);
  setText("studioSideEmail", email);
  setAvatar("studioSideAvatar", displayName);
  if (footerSignIn) footerSignIn.style.display = "none";
  if (footerSignOut) footerSignOut.style.display = "inline-flex";
  closeAuthModal();
  closeProfileModal();
  supabaseClient.auth.getSession().then(({ data }) => fetchEntitlements(data?.session?.access_token));

  // Intentionally no console logging in production UI.
}

function resetUI() {
  const emailInput = document.getElementById("email");
  const passwordInput = document.getElementById("password");
  const signedOutWrapper = document.getElementById("accountSignedOutWrapper");
  const signedInHint = document.getElementById("accountSignedInHint");
  const headerProfile = document.getElementById("headerProfile");
  const headerAuth = document.getElementById("headerAuth");
  const sideOut = document.getElementById("studioSideSignedOut");
  const sideIn = document.getElementById("studioSideSignedIn");
  const footerSignIn = document.getElementById("footerAccountSignIn");
  const footerSignOut = document.getElementById("footerAccountSignOut");

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
  if (sideOut) {
    sideOut.style.display = "grid";
  }
  if (sideIn) {
    sideIn.style.display = "none";
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
  setText("studioSideName", "Workspace user");
  setText("studioSideEmail", "Sign in to access the studio");
  setAvatar("studioSideAvatar", "OrcaFind");
  if (footerSignIn) footerSignIn.style.display = "inline-flex";
  if (footerSignOut) footerSignOut.style.display = "none";
  closeAuthModal();
  closeProfileModal();
  setResultsVisibility(false);
  fetchEntitlements(null);
  const requested = new URLSearchParams(window.location.search).get("mode");
  setAuthMode(requested === "signup" ? "signup" : "signin");
}

/* ---------- AUTH ACTIONS ---------- */

async function handleSignup() {
  const emailEl = document.getElementById("email");
  const passwordEl = document.getElementById("password");
  if (!emailEl || !passwordEl) {
    showToast("Unavailable", "Email/password sign-up is disabled. Use Google or X.", "error");
    return;
  }
  const email = emailEl.value;
  const password = passwordEl.value;
  setButtonLoading("primaryAuthAction", true, "Create Account", "Creating account...");
  const next = getSafeNextFromURL() || "/studio/";
  const emailRedirectTo = `${window.location.origin}/auth/?mode=signin&next=${encodeURIComponent(next)}`;
  const { error } = await supabaseClient.auth.signUp({
    email,
    password,
    options: {
      emailRedirectTo,
    },
  });
  setButtonLoading("primaryAuthAction", false, authMode === "signup" ? "Create Account" : "Sign In", "Creating account...");
  if (error) {
    showToast("Signup failed", error.message, "error");
  } else {
    showToast("Check your inbox", "Your account was created. Confirm your email to continue.", "success");
  }
}

async function handleLogin() {
  const emailEl = document.getElementById("email");
  const passwordEl = document.getElementById("password");
  if (!emailEl || !passwordEl) {
    showToast("Unavailable", "Email/password sign-in is disabled. Use Google or X.", "error");
    return;
  }
  const email = emailEl.value;
  const password = passwordEl.value;
  setButtonLoading("primaryAuthAction", true, "Sign In", "Signing in...");
  const { error } = await supabaseClient.auth.signInWithPassword({ email, password });
  setButtonLoading("primaryAuthAction", false, authMode === "signup" ? "Create Account" : "Sign In", "Signing in...");
  if (error) {
    const msg = String(error.message || "").toLowerCase().includes("email not confirmed")
      ? "Please confirm your email address (check your inbox) before signing in."
      : error.message;
    showToast("Login failed", msg, "error");
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
  window.OrcaFindLoader?.show({ title: "Signing in", body: "Redirecting to Google…" });
  const next = getSafeNextFromURL() || buildRelativeUrl({ stripParams: ["auth"] });
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: `${window.location.origin}/auth/?mode=signin&next=${encodeURIComponent(next)}`
    }
  });

  if (error) {
    window.OrcaFindLoader?.hide();
    showToast("Google sign-in failed", error.message, "error");
  }
}

async function loginWithX() {
  window.OrcaFindLoader?.show({ title: "Signing in", body: "Redirecting to X…" });
  const next = getSafeNextFromURL() || buildRelativeUrl({ stripParams: ["auth"] });
  // Supabase uses "twitter" as the provider name for X.
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "twitter",
    options: {
      redirectTo: `${window.location.origin}/auth/?mode=signin&next=${encodeURIComponent(next)}`
    }
  });

  if (error) {
    window.OrcaFindLoader?.hide();
    showToast("X sign-in failed", error.message, "error");
  }
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeAuthModal();
    closeProfileModal();
    closeStudioSidebar();
    closeStudioOptions();
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
  // Hydrate auth UI on load so profile icon shows when already signed in.
  supabaseClient.auth.getSession().then(({ data }) => {
    const session = data?.session;
    if (session?.user) {
      updateUIForUser(session.user);
    } else {
      resetUI();
    }
  });
  setImageUIState({ statusText: null, isBusy: false, images: null });

  try {
    const savedMode = window.localStorage.getItem("orcafind_studio_mode");
    if (savedMode === "images" || savedMode === "builder" || savedMode === "vision" || savedMode === "text") {
      studioMode = savedMode;
    }
  } catch (_err) {}
  setStudioMode(studioMode);
  updateStudioMobileDock();

  window.addEventListener("resize", () => updateStudioMobileDock(), { passive: true });

  const headerProfile = document.getElementById("headerProfile");
  if (headerProfile) {
    // If headerProfile is an anchor, it already works with keyboard by default.
    if (headerProfile.tagName !== "A") {
      headerProfile.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openProfileModal();
        }
      });
    }
  }

  const params = new URLSearchParams(window.location.search);
  const auth = params.get("auth");
  if (auth === "signin" || auth === "signup") {
    // Back-compat: old deep links used ?auth=signin on /studio/.
    redirectToAuth(auth, buildRelativeUrl({ stripParams: ["auth"] }));
  }

  if (isAuthPage()) {
    const requested = params.get("mode");
    if (requested === "signin" || requested === "signup") {
      setAuthMode(requested);
      document.title = requested === "signup" ? "OrcaFind AI | Sign Up" : "OrcaFind AI | Sign In";
    } else {
      document.title = "OrcaFind AI | Sign In";
    }
    const hint = document.getElementById("authNextHint");
    if (hint) {
      hint.textContent = params.get("next")
        ? "After sign-in, we’ll take you back to where you left off."
        : "After sign-in, we’ll open the Studio.";
    }
  }
});

/* ---------- GENERATE ---------- */

async function generate() {
  const text = document.getElementById("inputText").value;
  const button = document.getElementById("generateBtn");
  const xStyle = document.getElementById("xStyle")?.value || "thread";
  const contentFormat = document.getElementById("contentFormat")?.value || "professional";

  const accessToken = await getAccessTokenOrPromptAuth({
    mode: "signin",
    toastTitle: "Authentication required",
    toastBody: "Sign in to access protected content generation.",
  });
  if (!accessToken) return;

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
  const typingId = addTypingMessage({
    title: "OrcaFind",
    pill: "Working",
    label: "Generating posts and captions...",
  });

  try {
    const response = await fetch(`${API_BASE_URL}/repurpose/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${accessToken}` // Send the JWT to the backend
      },
      body: JSON.stringify({ text, x_style: xStyle, format: contentFormat })
    });

    const data = await response.json();

    if (!response.ok) {
      if (response.status === 401) {
        openAuthModal("signin");
        showToast("Session expired", "Please sign in again to continue.", "error");
      }
      removeChatMessage(typingId);
      addChatMessage({
        role: "assistant",
        title: "Error",
        pill: "Failed",
        text: data.detail || "API Error",
      });
      showToast("Generation failed", data.detail || "API Error", "error");
      return;
    }

    removeChatMessage(typingId);
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

    showToast("Generated", "Your posts and captions are ready.", "success");

  } catch (err) {
    removeChatMessage(typingId);
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
