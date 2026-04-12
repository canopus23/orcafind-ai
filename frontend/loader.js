(function () {
  function getRoot() {
    return document.getElementById("pageLoader");
  }

  function ensure() {
    let root = getRoot();
    if (root) return root;

    root = document.createElement("div");
    root.id = "pageLoader";
    root.className = "page-loader";
    root.setAttribute("aria-hidden", "true");
    root.innerHTML = [
      '<div class="page-loader-card" role="status" aria-live="polite">',
      '  <div class="page-loader-spinner" aria-hidden="true"></div>',
      '  <div class="page-loader-copy">',
      '    <strong id="pageLoaderTitle">Loading…</strong>',
      '    <p id="pageLoaderBody">Please wait.</p>',
      "  </div>",
      "</div>",
    ].join("\n");
    document.body.appendChild(root);
    return root;
  }

  function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function show(options) {
    const root = ensure();
    const title = options && options.title ? String(options.title) : "Loading…";
    const body = options && options.body ? String(options.body) : "Please wait.";
    setText("pageLoaderTitle", title);
    setText("pageLoaderBody", body);
    root.classList.add("is-visible");
    root.setAttribute("aria-hidden", "false");
  }

  function hide() {
    const root = getRoot();
    if (!root) return;
    root.classList.remove("is-visible");
    root.setAttribute("aria-hidden", "true");
  }

  window.OrcaFindLoader = { show, hide };
})();

