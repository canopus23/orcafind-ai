/** @type {import('next').NextConfig} */
const nextConfig = {
  trailingSlash: true,
  async rewrites() {
    return {
      afterFiles: [
        { source: "/", destination: "/index.html" },
        { source: "/auth/", destination: "/auth/index.html" },
        { source: "/checkout/", destination: "/checkout/index.html" },
        { source: "/privacy/", destination: "/privacy/index.html" },
        { source: "/refund/", destination: "/refund/index.html" },
        { source: "/sitemap/", destination: "/sitemap/index.html" },
        { source: "/studio/", destination: "/studio/index.html" },
        { source: "/terms/", destination: "/terms/index.html" }
      ]
    };
  }
};

export default nextConfig;

