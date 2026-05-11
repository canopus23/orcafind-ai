(function () {
  // Keep auth sessions stable by forcing one canonical host in production.
  // localStorage sessions do not carry across subdomains (www vs non-www).
  try {
    const host = String(window.location.hostname || "");
    const isProdHost = host === "orcafind.com" || host === "www.orcafind.com";
    if (isProdHost && host.startsWith("www.")) {
      const url = new URL(window.location.href);
      url.hostname = host.replace(/^www\./, "");
      window.location.replace(url.toString());
      return;
    }
  } catch (_err) {}

  const isLocal =
    window.location.hostname === "localhost" ||
    window.location.hostname === "127.0.0.1";

  const supabaseUrl =
    window.__ORCAFIND_SUPABASE_URL ||
    "https://rcfehmuiovcesucsvfsr.supabase.co";

  const supabaseAnonKey =
    window.__ORCAFIND_SUPABASE_ANON_KEY ||
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJjZmVobXVpb3ZjZXN1Y3N2ZnNyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ1MzE3MzAsImV4cCI6MjA5MDEwNzczMH0.8J4k5tlyA5G3gr70JT8aDbY36cidBc4s08hlwE-z9tY";

  const apiBaseUrl =
    window.__ORCAFIND_API_BASE_URL ||
    (isLocal ? "http://127.0.0.1:8000" : "https://api.orcafind.com");

  // Billing provider override for the frontend (optional).
  // Set this via a global before config.js loads:
  //   window.__ORCAFIND_BILLING_PROVIDER = "dodo"
  const billingProvider =
    window.__ORCAFIND_BILLING_PROVIDER ||
    "";

  // Google Analytics 4 Measurement ID (e.g. "G-XXXXXXXXXX").
  // Set this via a global before config.js loads:
  //   window.__ORCAFIND_GA_MEASUREMENT_ID = "G-...";
  // or leave unset to disable GA.
  const gaMeasurementId =
    window.__ORCAFIND_GA_MEASUREMENT_ID ||
    "G-7CC59GT8LH";

  window.__ORCAFIND_CONFIG = {
    supabaseUrl,
    supabaseAnonKey,
    apiBaseUrl,
    isLocal,
    gaMeasurementId,
    billingProvider,
  };
})();
