let selectedPlan = "starter";
let currentPlan = null;
let currentSubscription = null;

const ORCAFIND_CONFIG = window.__ORCAFIND_CONFIG || {};
const SUPABASE_URL = ORCAFIND_CONFIG.supabaseUrl || window.__ORCAFIND_SUPABASE_URL || "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = ORCAFIND_CONFIG.supabaseAnonKey || window.__ORCAFIND_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";
const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: true,
  },
});
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

function syncCheckoutModal() {
  const title = document.getElementById("checkoutModalTitle");
  const payBtn = document.getElementById("continueBtn");
  const emailField = document.getElementById("checkoutEmail");

  const label = PLAN_CATALOG[selectedPlan]?.label || "Starter";
  if (title) title.textContent = `Checkout · ${label}`;

  if (payBtn) {
    if (selectedPlan === "free") {
      payBtn.textContent = "Done";
    } else {
      payBtn.textContent = "Pay now";
    }
  }

  // For free plan, email isn't required; keep the field but de-emphasize.
  if (emailField) {
    emailField.placeholder = selectedPlan === "free" ? "Optional for Free plan" : "you@company.com";
  }
}

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

function openCheckoutModal() {
  const modal = document.getElementById("checkoutModal");
  if (!modal) return;
  modal.classList.add("is-open");
  modal.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  syncCheckoutModal();

  // Focus the email input for fast checkout.
  window.setTimeout(() => {
    const input = document.getElementById("checkoutEmail");
    if (input) input.focus();
  }, 40);
}

function closeCheckoutModal() {
  const modal = document.getElementById("checkoutModal");
  if (!modal) return;
  modal.classList.remove("is-open");
  modal.setAttribute("aria-hidden", "true");
  document.body.style.overflow = "";
}

window.openCheckoutModal = openCheckoutModal;
window.closeCheckoutModal = closeCheckoutModal;

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
  const applyBtn = document.getElementById("applyChangeBtn");
  const manageBlock = document.getElementById("manageBlock");

  if (!btn) return;

  // If user has an active recurring subscription, show management actions.
  if (manageBlock) {
    manageBlock.style.display = currentSubscription ? "block" : "none";
  }
  if (currentSubscription) {
    btn.style.display = "none";
    if (applyBtn) {
      applyBtn.disabled = !selectedPlan || selectedPlan === currentPlan || selectedPlan === "free";
    }
  } else {
    btn.style.display = "inline-block";
  }

  if (currentSubscription && currentPlan && selectedPlan === currentPlan && selectedPlan !== "free") {
    btn.disabled = true;
    btn.textContent = "Current plan";
    if (note) {
      note.classList.add("is-visible");
      note.textContent = `You're currently on the ${PLAN_CATALOG[selectedPlan]?.label || "Pro"} plan.`;
    }
    return;
  }

  btn.disabled = false;
  btn.textContent = currentPlan && !currentSubscription && selectedPlan === currentPlan && selectedPlan !== "free"
    ? "Start subscription"
    : "Continue";
  if (note) {
    if (currentPlan && !currentSubscription && selectedPlan === currentPlan && selectedPlan !== "free") {
      note.classList.add("is-visible");
      note.textContent = "You're on a legacy upgrade. Start a subscription to manage changes and cancellations.";
    } else {
      note.classList.remove("is-visible");
      note.textContent = "";
    }
  }
}

function selectPlan(plan) {
  const next = String(plan || "").trim().toLowerCase();
  selectedPlan = PLAN_CATALOG[next] ? next : "starter";
  ["free", "starter", "pro", "business"].forEach((key) => {
    document.getElementById(`${key}Plan`)?.classList.toggle("is-selected", selectedPlan === key);
  });
  syncSummary();
  syncCheckoutModal();
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
  syncCheckoutModal();
}

function proceedToPayment() {
  const email = document.getElementById("checkoutEmail")?.value?.trim();
  if (!email) {
    showToast("Missing email", "Enter an email to continue.", "error");
    return;
  }

  if (selectedPlan === "free") {
    closeCheckoutModal();
    showToast("No payment needed", "Free plan does not require checkout.", "success");
    return;
  }

  closeCheckoutModal();
  window.OrcaFindLoader?.show({ title: "Preparing checkout", body: "Starting a secure Dodo Payments session…" });
  startDodoCheckout(email).catch((err) => {
    window.OrcaFindLoader?.hide();
    showToast("Checkout failed", err.message || "Unable to start payment.", "error");
  });
}

function contactSales() {
  showToast("Contact sales", "Add a contact form or mailto link here.", "success");
}

function isDodoSuccessStatus(status) {
  const s = String(status || "").trim().toLowerCase();
  return s === "succeeded" || s === "success" || s === "paid" || s === "completed";
}

function readDodoReturnParams() {
  const params = new URLSearchParams(window.location.search);
  const isReturn = params.get("dodo_return") === "1";
  const subscriptionId =
    params.get("subscription_id") ||
    params.get("subscriptionId") ||
    params.get("sub_id") ||
    "";
  const paymentId =
    params.get("payment_id") ||
    params.get("paymentId") ||
    params.get("pay_id") ||
    "";
  const status = params.get("status") || "";
  return {
    isReturn,
    subscription_id: String(subscriptionId || "").trim(),
    payment_id: String(paymentId || "").trim(),
    status: String(status || "").trim(),
  };
}

async function startDodoCheckout(email) {
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) {
    window.location.href = `/auth/?mode=signin&next=${encodeURIComponent("/checkout/")}`;
    return;
  }

  const returnUrl = `${window.location.origin}/checkout/?dodo_return=1`;
  const subRes = await fetch(`${API_BASE_URL}/billing/dodo/checkout-session`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      plan: selectedPlan,
      email,
      return_url: returnUrl,
    }),
  });

  const subData = await subRes.json();
  if (!subRes.ok) {
    window.OrcaFindLoader?.hide();
    const detail = subData?.detail;
    const msg = typeof detail === "string"
      ? detail
      : (detail?.message || subData?.message || "Failed to start subscription");
    throw new Error(msg);
  }

  const url = String(subData?.checkout_url || "").trim();
  if (!url) {
    throw new Error("Checkout URL missing from server response.");
  }

  // Hosted checkout: redirect the browser.
  window.location.href = url;
}

async function applyPlanChange() {
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) {
    window.location.href = `/auth/?mode=signin&next=${encodeURIComponent("/checkout/")}`;
    return;
  }

  if (!selectedPlan || selectedPlan === "free" || selectedPlan === currentPlan) {
    showToast("No change", "Select a different paid plan to apply.", "error");
    return;
  }

  let nextEntitlements = null;
  window.OrcaFindLoader?.show({ title: "Updating plan", body: "Applying your subscription change…" });
  try {
    const endpoint = String(currentSubscription?.provider || "").toLowerCase() === "dodo_payments"
      ? `${API_BASE_URL}/billing/dodo/subscription/change`
      : `${API_BASE_URL}/billing/razorpay/subscription/change`;
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ plan: selectedPlan }),
    });
    const data = await res.json();
    if (!res.ok) {
      const detail = data?.detail;
      const code = typeof detail === "object" ? detail?.code : null;
      const msg = typeof detail === "string" ? detail : (detail?.message || "Failed to update plan");
      // Razorpay limitation: UPI subscriptions cannot be updated. Guide the user to cancel + re-subscribe.
      if (code === "UPI_SUBSCRIPTION_UNCHANGEABLE") {
        showToast(
          "Plan change not supported",
          "Razorpay doesn’t allow plan changes on UPI subscriptions. Cancel your current subscription, then start a new one on the plan you want (Card/NetBanking recommended).",
          "error"
        );
        return;
      }
      throw new Error(msg);
    }
    nextEntitlements = data?.entitlements || null;
    showToast("Plan updated", data?.schedule_change_at === "cycle_end" ? "Downgrade scheduled for period end." : "Upgrade applied immediately.", "success");
  } catch (err) {
    showToast("Update failed", err.message || "Could not update plan.", "error");
  } finally {
    window.OrcaFindLoader?.hide();
    // Refresh entitlements + UI (prefer the payload returned by the API to avoid extra latency).
    if (nextEntitlements) {
      hydrateFromEntitlements(nextEntitlements);
      try {
        window.localStorage.setItem(
          "orcafind_entitlements_cache",
          JSON.stringify({ at: Date.now(), entitlements: nextEntitlements })
        );
        window.localStorage.removeItem("orcafind_entitlements_dirty");
      } catch (_err) {}
    } else {
      try {
        const entRes = await fetch(`${API_BASE_URL}/entitlements`, {
          method: "GET",
          headers: { "Authorization": `Bearer ${session.access_token}` },
        });
        if (entRes.ok) {
          const ent = await entRes.json();
          hydrateFromEntitlements(ent);
          try {
            window.localStorage.setItem(
              "orcafind_entitlements_cache",
              JSON.stringify({ at: Date.now(), entitlements: ent })
            );
            window.localStorage.removeItem("orcafind_entitlements_dirty");
          } catch (_err) {}
        }
      } catch (_err) {}
    }
  }
}

async function cancelSubscription() {
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) {
    window.location.href = `/auth/?mode=signin&next=${encodeURIComponent("/checkout/")}`;
    return;
  }

  let nextEntitlements = null;
  // Default behavior: cancel at period end (SaaS-standard). Backend will fall back to immediate
  // cancellation when Razorpay indicates no billing cycle has started yet.
  window.OrcaFindLoader?.show({ title: "Cancelling", body: "Scheduling cancellation at period end…" });
  try {
    const endpoint = String(currentSubscription?.provider || "").toLowerCase() === "dodo_payments"
      ? `${API_BASE_URL}/billing/dodo/subscription/cancel`
      : `${API_BASE_URL}/billing/razorpay/subscription/cancel`;
    const res = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ cancel_at_cycle_end: true }),
    });
    const data = await res.json();
    if (!res.ok) {
      const detail = data?.detail;
      const msg = typeof detail === "string" ? detail : (detail?.message || "Failed to cancel subscription");
      throw new Error(msg);
    }
    nextEntitlements = data?.entitlements || null;
    if (data?.cancel_at_cycle_end) {
      showToast("Cancellation scheduled", "Your plan will remain active until the end of the billing period.", "success");
    } else {
      showToast("Subscription cancelled", "Your subscription was cancelled immediately.", "success");
    }
  } catch (err) {
    showToast("Cancel failed", err.message || "Could not cancel subscription.", "error");
  } finally {
    window.OrcaFindLoader?.hide();
    if (nextEntitlements) {
      hydrateFromEntitlements(nextEntitlements);
      try {
        window.localStorage.setItem(
          "orcafind_entitlements_cache",
          JSON.stringify({ at: Date.now(), entitlements: nextEntitlements })
        );
        window.localStorage.removeItem("orcafind_entitlements_dirty");
      } catch (_err) {}
    } else {
      try {
        const entRes = await fetch(`${API_BASE_URL}/entitlements`, {
          method: "GET",
          headers: { "Authorization": `Bearer ${session.access_token}` },
        });
        if (entRes.ok) {
          const ent = await entRes.json();
          hydrateFromEntitlements(ent);
          try {
            window.localStorage.setItem(
              "orcafind_entitlements_cache",
              JSON.stringify({ at: Date.now(), entitlements: ent })
            );
            window.localStorage.removeItem("orcafind_entitlements_dirty");
          } catch (_err) {}
        }
      } catch (_err) {}
    }
  }
}

window.applyPlanChange = applyPlanChange;
window.cancelSubscription = cancelSubscription;

function formatEpoch(epochSeconds) {
  const sec = Number(epochSeconds || 0);
  if (!sec) return "—";
  const date = new Date(sec * 1000);
  try {
    return new Intl.DateTimeFormat("en-IN", { month: "short", day: "2-digit", year: "numeric" }).format(date);
  } catch (_err) {
    return date.toISOString().slice(0, 10);
  }
}

function hydrateFromEntitlements(ent) {
  currentSubscription = ent?.subscription || null;
  setCurrentPlan(ent?.plan || "free");

  const statusNode = document.getElementById("subStatus");
  const renewsNode = document.getElementById("subRenews");
  const schedNode = document.getElementById("subScheduled");
  const cancelBtn = document.getElementById("cancelSubBtn");

  if (currentSubscription) {
    if (statusNode) statusNode.textContent = String(currentSubscription.status || "active").toUpperCase();
    if (renewsNode) renewsNode.textContent = formatEpoch(currentSubscription.current_period_end);
    if (schedNode) {
      const sched = currentSubscription.scheduled_plan;
      const cancel = currentSubscription.cancel_at_cycle_end;
      schedNode.textContent = cancel ? "Cancel at period end" : (sched ? `Switch to ${String(sched).toUpperCase()}` : "—");
    }
    if (cancelBtn) {
      const status = String(currentSubscription.status || "").toLowerCase();
      const cancelled = status === "cancelled" || status === "canceled";
      const scheduledCancel = Boolean(currentSubscription.cancel_at_cycle_end);
      // Once cancellation is scheduled (or already cancelled), disable the button and show "Cancelled".
      cancelBtn.disabled = cancelled || scheduledCancel;
      cancelBtn.textContent = (cancelled || scheduledCancel) ? "Cancelled" : "Cancel at period end";
      cancelBtn.setAttribute("aria-disabled", cancelBtn.disabled ? "true" : "false");
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // If we were redirected back from Dodo Payments checkout, confirm and hydrate entitlements.
  (function () {
    const returned = readDodoReturnParams();
    if (!returned.isReturn) return;

    if (returned.status && !isDodoSuccessStatus(returned.status)) {
      showToast("Payment not completed", `Checkout status: ${returned.status}`, "error");
      return;
    }

    if (!returned.subscription_id) {
      showToast("Checkout incomplete", "Missing subscription_id in return URL.", "error");
      return;
    }

    window.OrcaFindLoader?.show({ title: "Finalizing", body: "Confirming your subscription…" });
    supabaseClient.auth.getSession()
      .then(async ({ data }) => {
        const session = data?.session;
        if (!session) {
          window.location.href = `/auth/?mode=signin&next=${encodeURIComponent("/checkout/")}`;
          return null;
        }
        const confirmRes = await fetch(`${API_BASE_URL}/billing/dodo/confirm`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({
            subscription_id: returned.subscription_id,
            payment_id: returned.payment_id,
          }),
        });
        let confirmData = null;
        try {
          confirmData = await confirmRes.json();
        } catch (_err) {
          confirmData = null;
        }
        if (!confirmRes.ok) {
          const detail = confirmData?.detail;
          const msg = typeof detail === "string"
            ? detail
            : (detail?.message || confirmData?.message || "Could not confirm subscription");
          throw new Error(msg);
        }
        return confirmData;
      })
      .then((confirmData) => {
        if (!confirmData) return;

        // Cache entitlements for instant UX.
        try {
          const ent = confirmData?.entitlements;
          if (ent && typeof ent === "object") {
            window.localStorage.setItem(
              "orcafind_entitlements_cache",
              JSON.stringify({ at: Date.now(), entitlements: ent })
            );
            window.localStorage.removeItem("orcafind_entitlements_dirty");
            hydrateFromEntitlements(ent);
          }
        } catch (_err) {}

        const planLabel = String(confirmData?.effective_plan || confirmData?.plan || selectedPlan || "pro").toUpperCase();
        showToast("Payment successful", `${planLabel} is now enabled for your account.`, "success");
        window.setTimeout(() => {
          window.location.href = "/studio/#studio";
        }, 900);
      })
      .catch((err) => {
        showToast("Confirmation failed", err.message || "Could not confirm subscription.", "error");
      })
      .finally(() => {
        window.OrcaFindLoader?.hide();
      });
  })();

  // Fast path: hydrate from cached entitlements so "Current plan" shows instantly.
  // We'll still reconcile with the API in the background.
  try {
    const cached = JSON.parse(window.localStorage.getItem("orcafind_entitlements_cache") || "null");
    if (cached?.entitlements) {
      hydrateFromEntitlements(cached.entitlements);
    }
  } catch (_err) {}

  // Modal close events.
  const modal = document.getElementById("checkoutModal");
  if (modal) {
    modal.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      if (target.matches("[data-modal-close]")) {
        closeCheckoutModal();
      }
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const m = document.getElementById("checkoutModal");
    if (m && m.classList.contains("is-open")) closeCheckoutModal();
  });

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

  // If signed in, fetch entitlements so we can highlight the current plan + manage subscription.
  supabaseClient.auth.getSession().then(async ({ data }) => {
    const session = data?.session;
    if (!session?.access_token) {
      // Don't force the UI to "free" if we already hydrated a cache.
      if (!currentPlan) {
        hydrateFromEntitlements({ plan: "free", subscription: null });
      }
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/entitlements`, {
        method: "GET",
        headers: { "Authorization": `Bearer ${session.access_token}` },
      });
      if (!res.ok) throw new Error("Entitlements fetch failed");
      const ent = await res.json();
      hydrateFromEntitlements(ent);
    } catch (_err) {
      // Keep any cached plan shown; if there is no cache, avoid claiming a current plan.
      if (!currentPlan) {
        hydrateFromEntitlements({ plan: null, subscription: null });
      }
    }
  });
});
