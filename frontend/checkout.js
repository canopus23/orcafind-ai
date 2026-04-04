let selectedPlan = "pro";
let billing = "monthly";

const SUPABASE_URL = window.__ORCAFIND_SUPABASE_URL || "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = window.__ORCAFIND_SUPABASE_ANON_KEY || "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";
const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

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

function setBilling(next) {
  billing = next === "yearly" ? "yearly" : "monthly";
  document.getElementById("monthlyBtn")?.classList.toggle("is-active", billing === "monthly");
  document.getElementById("yearlyBtn")?.classList.toggle("is-active", billing === "yearly");
  syncSummary();
}

function selectPlan(plan) {
  selectedPlan = plan === "free" ? "free" : "pro";
  document.getElementById("freePlan")?.classList.toggle("is-selected", selectedPlan === "free");
  document.getElementById("proPlan")?.classList.toggle("is-selected", selectedPlan === "pro");
  syncSummary();
}

function getProPrice() {
  if (billing === "yearly") {
    return { amount: 190, label: "$190 / yr" };
  }
  return { amount: 19, label: "$19 / mo" };
}

function syncSummary() {
  const planPill = document.getElementById("planPill");
  const summaryPlan = document.getElementById("summaryPlan");
  const summaryBilling = document.getElementById("summaryBilling");
  const summaryTotal = document.getElementById("summaryTotal");
  const proPrice = document.getElementById("proPrice");
  const proPer = document.getElementById("proPer");

  const price = getProPrice();
  if (proPrice && proPer) {
    proPrice.textContent = billing === "yearly" ? "$190" : "$19";
    proPer.textContent = billing === "yearly" ? "per year" : "per month";
  }

  if (planPill) planPill.textContent = `${selectedPlan === "free" ? "Free" : "Pro"} selected`;
  if (summaryPlan) summaryPlan.textContent = selectedPlan === "free" ? "Free" : "Pro";
  if (summaryBilling) summaryBilling.textContent = billing === "yearly" ? "Yearly" : "Monthly";

  if (summaryTotal) {
    summaryTotal.textContent = selectedPlan === "free" ? "$0" : price.label;
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

  startRazorpayCheckout(email).catch((err) => {
    showToast("Checkout failed", err.message || "Unable to start payment.", "error");
  });
}

function contactSales() {
  showToast("Contact sales", "Add a contact form or mailto link here.", "success");
}

async function startRazorpayCheckout(email) {
  const { data: { session } } = await supabaseClient.auth.getSession();
  if (!session) {
    showToast("Sign in required", "Please sign in first, then return to checkout.", "error");
    return;
  }

  const orderRes = await fetch("https://api.orcafind.com/billing/razorpay/order", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${session.access_token}`,
    },
    body: JSON.stringify({
      plan: "pro",
      billing,
      email,
    }),
  });

  const orderData = await orderRes.json();
  if (!orderRes.ok) {
    throw new Error(orderData?.detail || "Failed to create order");
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
        const verifyRes = await fetch("https://api.orcafind.com/billing/razorpay/verify", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          }),
        });

        const verifyData = await verifyRes.json();
        if (!verifyRes.ok) {
          throw new Error(verifyData?.detail || "Payment verification failed");
        }

        showToast("Payment successful", "Pro is now enabled for your account.", "success");
        window.setTimeout(() => {
        window.location.href = "/studio/#studio";
      }, 900);
      } catch (err) {
        showToast("Verification failed", err.message || "Could not verify payment.", "error");
      }
    },
  };

  // Razorpay Checkout injected globally by the script tag.
  const rzp = new window.Razorpay(options);
  rzp.open();
}

document.addEventListener("DOMContentLoaded", () => {
  // Keyboard access for plan cards.
  ["freePlan", "proPlan"].forEach((id) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectPlan(id === "freePlan" ? "free" : "pro");
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
});
