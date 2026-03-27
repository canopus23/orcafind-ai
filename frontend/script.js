const SUPABASE_URL = "https://rcfehmuiovcesucsvfsr.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

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
  else alert("Logged in successfully!");
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
  if (!session) { alert("Please login first"); return; }

  if (!text.trim()) { alert("Please enter some content"); return; }

  button.innerText = "Processing...";
  button.disabled = true;
  output.innerHTML = "<p style='grid-column: span 2; text-align: center;'>Our AI is crafting your posts...</p>";

  try {
    const response = await fetch("https://api.orcafind.com/repurpose/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${session.access_token}`
      },
      body: JSON.stringify({ text })
    });

    const data = await response.json();
    if (!response.ok) { output.innerHTML = `<p>${data.detail}</p>`; return; }

    const parts = data.result.split("LinkedIn");

    output.innerHTML = `
      <div class="platform-card">
        <div class="platform-header"><span>Twitter / X</span> 📋</div>
        <div class="box">${parts[0].trim()}</div>
      </div>
      <div class="platform-card">
        <div class="platform-header"><span>LinkedIn</span> 📋</div>
        <div class="box">${(parts[1] || "").trim()}</div>
      </div>
    `;

  } catch (err) {
    output.innerHTML = "<p>Error connecting to API.</p>";
  } finally {
    button.innerText = "Generate Posts";
    button.disabled = false;
  }
}

function copyText() {
  const text = document.getElementById("output").innerText;
  navigator.clipboard.writeText(text);
  alert("Copied to clipboard!");
}