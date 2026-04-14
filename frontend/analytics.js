(function () {
  "use strict";

  // GA4 is intentionally optional.
  // If the Measurement ID isn't configured, do nothing.
  var cfg = (window && window.__ORCAFIND_CONFIG) || {};
  var measurementId = String(cfg.gaMeasurementId || window.__ORCAFIND_GA_MEASUREMENT_ID || "G-7CC59GT8LH").trim();
  if (!measurementId) return;

  // Avoid polluting prod analytics during local development unless explicitly desired.
  var isLocal = typeof cfg.isLocal === "boolean"
    ? cfg.isLocal
    : (location.hostname === "localhost" || location.hostname === "127.0.0.1");
  if (isLocal) return;

  // Load GA4 (gtag.js)
  try {
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };

    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(measurementId);
    document.head.appendChild(s);

    window.gtag("js", new Date());
    window.gtag("config", measurementId, {
      anonymize_ip: true,
      // We don't use cookies for auth; avoid any accidental cross-site credential behavior.
      // GA uses its own cookies; this just keeps our integration conservative.
      allow_google_signals: false,
    });

    // Minimal helper for future custom events.
    window.orcafindTrack = function (eventName, params) {
      try {
        window.gtag("event", String(eventName || "event"), params || {});
      } catch (_err) {}
    };
  } catch (_err) {
    // If an adblocker blocks GA, don't affect UX.
  }
})();
