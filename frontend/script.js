const FREE_LIMIT = 3;

async function generate() {
  const text = document.getElementById("inputText").value;
  const button = document.getElementById("generateBtn");
  const output = document.getElementById("output");

  let usage = localStorage.getItem("usage") || 0;

  if (usage >= FREE_LIMIT) {
    alert("🚫 Free limit reached. Upgrade to continue.");
    return;
  }

  if (!text.trim()) {
    alert("Enter content");
    return;
  }

  button.innerText = "Generating...";
  button.disabled = true;
  output.innerHTML = "⏳ Generating...";

  try {
    const response = await fetch("https://api.orcafind.com/repurpose/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ text })
    });

    if (!response.ok) {
      const err = await response.json();
      output.innerHTML = "🚫 " + err.detail;
      return;
    }

    const data = await response.json();

    const parts = data.result.split("LinkedIn");

    output.innerHTML = `
      <h3>🐦 Twitter</h3>
      <div class="box">${parts[0]}</div>

      <h3>💼 LinkedIn</h3>
      <div class="box">${parts[1] || ""}</div>
    `;

    usage++;
    localStorage.setItem("usage", usage);

  } catch (err) {
    output.innerHTML = "❌ Error occurred";
  }

  button.innerText = "Generate";
  button.disabled = false;
}

function copyText() {
  const text = document.getElementById("output").innerText;
  navigator.clipboard.writeText(text);
  alert("Copied!");
}