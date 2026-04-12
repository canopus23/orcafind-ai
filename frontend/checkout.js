let selectedPlan = "starter";
let currentPlan = null;

const ORCAFIND_CONFIG = window.__ORCAFIND_CONFIG || {};
const SUPABASE_URL = ORCAFIND_CONFIG.supabaseUrl || window.__ORCAFIND_SUPABASE_URL || "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = ORCAFIND_CONFIG.supabaseAnonKey || window.__ORCAFIND_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";
const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
const API_BASE_URL = ORCAFIND_CONFIG.apiBaseUrl || window.__ORCAFIND_API_BASE_URL || "https://api.orcafind.com";

function formatINR(amount) {
  const value = Number(amount || 0);
  try {
    return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(value);
  } catch (_err) {
    return String(Math.round(value));
  }
}

const PLAN_CATALOG = {
  free: { label: "Free", amountInr: 0, priceLabel: "₹0", checkoutLabel: "₹0" },
  starter: { label: "Starter", amountInr: 499, priceLabel: `₹${formatINR(499)}`, checkoutLabel: `₹${formatINR(499)} / mo` },
  pro: { label: "Pro", amountInr: 1499, priceLabel: `₹${formatINR(1499)}`, checkoutLabel: `₹${formatINR(1499)} / mo` },
  business: { label: "Business", amountInr: 2999, priceLabel: `₹${formatINR(2999)}`, checkoutLabel: `₹${formatINR(2999)} / mo` },
};

function showToast(title, message, type = "default") {
  const stack = document.getElementById("toastStack");
  if (!stack) return;

  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<strong>${title}</strong><p>${message}</p>`;
  stack.appendChild(toast);

  window.setTimeout(() => {
    toast.remove();
  }, 3200);
}

function setCurrentPlan(plan) {
  const normalized = String(plan || "").trim().toLowerCase();
  currentPlan = PLAN_CATALOG[normalized] ? normalized : null;

  ["free", "starter", "pro", "business"].forEach((key) => {
    document.getElementById(`${key}Current`)?.classList.toggle("is-visible", currentPlan === key);
  });

  // If the user is already on a paid plan, default to showing that plan as selected.
  if (currentPlan && currentPlan !== "free") {
    selectPlan(currentPlan);
  } else if (currentPlan === "free") {
    // If explicitly free, keep the existing default selection (Starter) so upgrades are easy.
    syncSummary();
  }

  updateCheckoutCTA();
}

function updateCheckoutCTA() {
  const note = document.getElementById("currentPlanNote");
  const btn = document.getElementById("continueBtn");

  if (!btn) return;

  if (currentPlan && selectedPlan === currentPlan && selectedPlan !== "free") {
    btn.disabled = true;
    btn.textContent = "Current plan";
    if (note) {
      note.classList.add("is-visible");
      note.textContent = `You're currently on the ${PLAN_CATALOG[selectedPlan]?.label || "Pro"} plan.`;
    }
    return;
  }

  btn.disabled = false;
  btn.textContent = "Continue";
  if (note) {
    note.classList.remove("is-visible");
    note.textContent = "";
  }
}

function selectPlan(plan) {
  const next = String(plan || "").trim().toLowerCase();
  selectedPlan = PLAN_CATALOG[next] ? next : "starter";
  ["free", "starter", "pro", "business"].forEach((key) => {
    document.getElementById(`${key}Plan`)?.classList.toggle("is-selected", selectedPlan === key);
  });
  syncSummary();
  updateCheckoutCTA();
}

function syncSummary() {
  const planPill = document.getElementById("planPill");
  const summaryPlan = document.getElementById("summaryPlan");
  const summaryTotal = document.getElementById("summaryTotal");
  const priceNode = document.getElementById("starterPrice");
  if (priceNode) priceNode.textContent = PLAN_CATALOG.starter.priceLabel;
  const proPriceNode = document.getElementById("proPrice");
  if (proPriceNode) proPriceNode.textContent = PLAN_CATALOG.pro.priceLabel;
  const businessPriceNode = document.getElementById("businessPrice");
  if (businessPriceNode) businessPriceNode.textContent = PLAN_CATALOG.business.priceLabel;

  if (planPill) planPill.textContent = `${PLAN_CATALOG[selectedPlan]?.label || "Starter"} selected`;
  if (summaryPlan) summaryPlan.textContent = PLAN_CATALOG[selectedPlan]?.label || "Starter";

  if (summaryTotal) {
    summaryTotal.textContent = PLAN_CATALOG[selectedPlan]?.checkoutLabel || `₹${formatINR(499)} / mo`;
  }
}

function proceedToPayment() {
  const email = document.getElementById("checkoutEmail")?.value?.trim();
  if (!email) {
    showToast("Missing email", "Enter an email to continue.", "error");
    return;
  }

  if (selectedPlan === "free") {
    showToast("No payment needed", "Free plan does not require checkout.", "success");
    return;
  }

  window.OrcaFindLoader?.show({ title: "Preparing checkout", body: "Starting a secure Razorpay session…" });
  startRazorpayCheckout(email).catch((err) => {
    window.OrcaFindLoader?.hide();
    showToast("Checkout failed", err.message || "Unable to start payment.", "error");
  });
}

function contactSales() {
  showToast("Contact sales", "Add a contact form or mailto link here.", "success");
}

async function startRazorpayCheckout(email) {
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) {
    window.location.href = `/auth/?mode=signin&next=${encodeURIComponent("/checkout/")}`;
    return;
  }

  const orderRes = await fetch(`${API_BASE_URL}/billing/razorpay/order`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      plan: selectedPlan,
      billing: "monthly",
      email,
    }),
  });

  const orderData = await orderRes.json();
  if (!orderRes.ok) {
    window.OrcaFindLoader?.hide();
    const detail = orderData?.detail;
    const msg = typeof detail === "string"
      ? detail
      : (detail?.message || orderData?.message || "Failed to create order");
    throw new Error(msg);
  }

  const options = {
    key: orderData.key_id,
    amount: orderData.amount,
    currency: orderData.currency,
    name: orderData.name,
    description: orderData.description,
    order_id: orderData.order_id,
    prefill: {
      email: email,
    },
    theme: { color: "#1367ff" },
    handler: async function (response) {
      try {
        window.OrcaFindLoader?.show({ title: "Verifying payment", body: "Finalizing your subscription…" });
        // The checkout flow can take time. Refresh the Supabase session so we don't
        // verify with an expired/stale access token.
        const { data: { session: latestSession } } = await supabaseClient.auth.getSession();
        if (!latestSession) {
          window.OrcaFindLoader?.hide();
          window.location.href = `/auth/?mode=signin&next=${encodeURIComponent("/checkout/")}`;
          return;
        }

        const verifyRes = await fetch(`${API_BASE_URL}/billing/razorpay/verify`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${latestSession.access_token}`,
          },
          body: JSON.stringify({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          }),
        });

        let verifyData = null;
        try {
          verifyData = await verifyRes.json();
        } catch (_err) {
          verifyData = null;
        }
        if (!verifyRes.ok) {
          window.OrcaFindLoader?.hide();
          const detail = verifyData?.detail;
          const msg = typeof detail === "string"
            ? detail
            : (detail?.message || verifyData?.message || "Payment verification failed");
          const reqId = detail?.request_id;
          throw new Error(reqId ? `${msg} (request_id: ${reqId})` : msg);
        }

        window.OrcaFindLoader?.hide();

        // Immediately refresh entitlements so the UI shows the new plan.
        try {
          const entRes = await fetch(`${API_BASE_URL}/entitlements`, {
            method: "GET",
            headers: { "Authorization": `Bearer ${latestSession.access_token}` },
          });
          if (entRes.ok) {
            const ent = await entRes.json();
            window.localStorage.setItem("orcafind_entitlements_cache", JSON.stringify({
              at: Date.now(),
              entitlements: ent,
            }));
          }
        } catch (_err) {}

        const planLabel = String(verifyData?.effective_plan || verifyData?.plan || "pro").toUpperCase();
        showToast("Payment successful", `${planLabel} is now enabled for your account.`, "success");
        // Force a fresh entitlements fetch on next page load.
        try {
          window.localStorage.setItem("orcafind_entitlements_dirty", String(Date.now()));
        } catch (_err) {}
        window.setTimeout(() => {
        window.location.href = "/studio/#studio";
      }, 900);
      } catch (err) {
        window.OrcaFindLoader?.hide();
        showToast("Verification failed", err.message || "Could not verify payment.", "error");
      }
    },
  };

  // Razorpay Checkout injected globally by the script tag.
  const rzp = new window.Razorpay(options);
  // Hide the loader as the Razorpay modal takes over the screen.
  window.setTimeout(() => window.OrcaFindLoader?.hide(), 450);
  rzp.open();
}

document.addEventListener("DOMContentLoaded", () => {
  // Keyboard access for plan cards.
  ["freePlan", "starterPlan", "proPlan", "businessPlan"].forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectPlan(id.replace("Plan", ""));
      }
    });
  });

  syncSummary();

  // Prefill email when already signed in.
  supabaseClient.auth.getSession().then(({ data }) => {
    const email = data?.session?.user?.email;
    const input = document.getElementById("checkoutEmail");
    if (email && input && !input.value) {
      input.value = email;
    }
  });

  // If signed in, fetch entitlements so we can highlight the current plan.
  supabaseClient.auth.getSession().then(async ({ data }) => {
    const session = data?.session;
    if (!session?.access_token) {
      setCurrentPlan("free");
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/entitlements`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${session.access_token}` },
      });
      if (!res.ok) throw new Error("Entitlements fetch failed");
      const ent = await res.json();
      setCurrentPlan(ent?.plan || "free");
    } catch (_err) {
      // Don't block checkout; just avoid claiming a current plan.
      setCurrentPlan(null);
    }
  });
});
