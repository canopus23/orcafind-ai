const SUPABASE_URL = "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

// Renamed from 'supabase' to 'supabaseClient' to avoid naming conflicts
const supabaseClient = window.supabase.createClient(
  SUPABASE_URL,
  SUPABASE_ANON_KEY
);

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
  else alert("Logged in");
}

async function logout() {
  await supabaseClient.auth.signOut();
  alert("Logged out");
}

async function generate() {
  const text = document.getElementById("inputText").value;
  const button = document.getElementById("generateBtn");
  const output = document.getElementById("output");

  const { data: { session } } = await supabaseClient.auth.getSession();

  if (!session) {
    alert("Please login first");
    return;
  }

  const token = session.access_token;

  if (!text.trim()) {
    alert("Enter content");
    return;
  }

  button.innerText = "Generating...";
  button.disabled = true;
  output.innerHTML = "Generating...";

  try {
    const response = await fetch("https://api.orcafind.com/repurpose/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${token}`
      },
      body: JSON.stringify({ text })
    });

    const data = await response.json();

    if (!response.ok) {
      output.innerHTML = data.detail || "Request failed";
      return;
    }

    const parts = data.result.split("LinkedIn");

    output.innerHTML = `
      <h3>Twitter</h3>
      <div class="box">${parts[0] || ""}</div>

      <h3>LinkedIn</h3>
      <div class="box">${parts[1] || ""}</div>
    `;

  } catch (err) {
    output.innerHTML = "Error occurred: " + err.message;
  }

  button.innerText = "Generate";
  button.disabled = false;
}

function copyText() {
  const output = document.getElementById("output");
  if (output) {
    navigator.clipboard.writeText(output.innerText);
    alert("Copied to clipboard!");
  }
}