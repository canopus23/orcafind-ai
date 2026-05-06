import Script from "next/script";
import ProfileClient from "./profile-client";

export const metadata = {
  title: "OrcaFind AI | Profile",
  description: "Manage your OrcaFind AI profile, subscription, and usage details from your account dashboard."
};

export default function ProfilePage() {
  return (
    <>
      <ProfileClient />

      <Script src="/vendor/supabase-js-2.105.1.umd.min.js" strategy="afterInteractive" />
      <Script src="/analytics.js" strategy="afterInteractive" />
      <Script src="/loader.js" strategy="afterInteractive" />
      <Script src="/profile.js" strategy="afterInteractive" />
      <Script id="orcafind-footer-year" strategy="afterInteractive">
        {`
          (function () {
            var node = document.getElementById("footerYear");
            if (node) node.textContent = String(new Date().getFullYear());
          })();
        `}
      </Script>
    </>
  );
}
