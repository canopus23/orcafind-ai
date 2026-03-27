const SUPABASE_URL = "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

/* ---------- AUTH STATE LISTENER ---------- */

// Listen for the redirect from Google or manual login and update the UI
supabaseClient.auth.onAuthStateChange((event, session) => {
  if (event === 'SIGNED_IN' || event === 'INITIAL_SESSION') {
    updateUIForUser(session.user);
  } else if (event === 'SIGNED_OUT') {
    resetUI();
  }
});

function updateUIForUser(user) {
  const emailInput = document.getElementById("email");
  if (emailInput) {
    emailInput.value = user.email;
    emailInput.disabled = true;
  }
  console.log("User is authenticated:", user.email);
}

function resetUI() {
  const emailInput = document.getElementById("email");
  if (emailInput) {
    emailInput.value = "";
    emailInput.disabled = false;
  }
}

/* ---------- AUTH ACTIONS ---------- */

async function handleSignup() {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const { error } = await supabaseClient.auth.signUp({ email, password });
  if (error) alert(error.message);
  else alert("Check your email to confirm");
}

async function handleLogin() {
  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const { error } = await supabaseClient.auth.signInWithPassword({ email, password });
  if (error) alert(error.message);
}

async function logout() {
  await supabaseClient.auth.signOut();
  alert("Logged out");
}

async function loginWithGoogle() {
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: window.location.origin
    }
  });

  if (error) alert(error.message);
}

/* ---------- GENERATE ---------- */

async function generate() {
  const text = document.getElementById("inputText").value;
  const button = document.getElementById("generateBtn");
  const output = document.getElementById("output");

  // Re-fetch session specifically at time of click to get the access_token
  const { data: { session }, error: sessionError } = await supabaseClient.auth.getSession();

  if (!session) {
    alert("Authentication required. Please login with Google or Email.");
    return;
  }

  if (!text.trim()) {
    alert("Please enter some content");
    return;
  }

  button.innerText = "Processing...";
  button.disabled = true;

  output.innerHTML = `
    <div style="grid-column: span 2; text-align: center; color: #94a3b8;">
      Crafting your content...
    </div>
  `;

  try {
    const response = await fetch("https://api.orcafind.com/repurpose/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}` // Send the JWT to the backend
      },
      body: JSON.stringify({ text })
    });

    const data = await response.json();

    if (!response.ok) {
      output.innerHTML = `<div style="grid-column: span 2; color: #ef4444;">${data.detail || 'API Error'}</div>`;
      return;
    }

    // Logic assumes API returns text separated by "LinkedIn"
    const parts = data.result.split("LinkedIn");

    output.innerHTML = `
      <div class="platform-card">
        <div class="platform-header"><span>Twitter / X</span></div>
        <div class="box">${parts[0].trim()}</div>
      </div>

      <div class="platform-card">
        <div class="platform-header"><span>LinkedIn</span></div>
        <div class="box">${(parts[1] || "").trim()}</div>
      </div>
    `;

  } catch (err) {
    output.innerHTML = `<div style="grid-column: span 2; color: #ef4444;">Error connecting to API: ${err.message}</div>`;
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
    alert("Copied to clipboard");
  }
}