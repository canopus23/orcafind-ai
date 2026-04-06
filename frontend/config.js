(function () {
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

  window.__ORCAFIND_CONFIG = {
    supabaseUrl,
    supabaseAnonKey,
    apiBaseUrl,
    isLocal,
  };
})();

