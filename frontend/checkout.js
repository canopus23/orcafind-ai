let selectedPlan = "pro";
let billing = "monthly";

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

  showToast("Checkout coming soon", "Next step is Stripe checkout integration.", "success");
}

function contactSales() {
  showToast("Contact sales", "Add a contact form or mailto link here.", "success");
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
});

