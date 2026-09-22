import type { NextConfig } from "next";

const backendOrigin = process.env.SURPRIZ_BACKEND_ORIGIN ?? "http://127.0.0.1:5050";
const developmentAssetOrigin =
  process.env.NODE_ENV === "development" ? "http://127.0.0.1:4173" : undefined;
const publicAssetOrigin = (process.env.SURPRIZ_PUBLIC_ASSET_ORIGIN ?? developmentAssetOrigin)?.replace(/\/$/, "");
const configuredBuildId =
  process.env.SURPRIZ_RELEASE_ID ??
  process.env.VERCEL_GIT_COMMIT_SHA ??
  process.env.SOURCE_VERSION;
const publicBuildId = (configuredBuildId || `build-${Date.now().toString(36)}`)
  .replace(/[^a-zA-Z0-9._-]/g, "-")
  .slice(0, 64);
const scriptPolicy = process.env.NODE_ENV === "development" ? "'self' 'unsafe-inline' 'unsafe-eval'" : "'self' 'unsafe-inline'";
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src ${scriptPolicy}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "media-src 'self'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  compress: true,
  env: {
    NEXT_PUBLIC_SURPRIZ_BUILD_ID: publicBuildId,
  },
  generateBuildId: async () => publicBuildId,
  turbopack: { root: process.cwd() },
  images: {
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 2_678_400,
    localPatterns: [
      { pathname: "/wp-content/**" },
      { pathname: "/admin-media/**" },
      { pathname: "/brand/**" },
      { pathname: "/media/**" },
      { pathname: "/surpriz/**" }
    ]
  },
  async rewrites() {
    return {
      afterFiles: [
        { source: "/api/legacy/:path*", destination: `${backendOrigin}/api/:path*` },
        ...(publicAssetOrigin
          ? [{ source: "/surpriz/:path*", destination: `${publicAssetOrigin}/surpriz/:path*` }]
          : []),
      ]
    };
  },
  async headers() {
    const privateAdminHeaders = [
      { key: "Cache-Control", value: "private, no-store, no-cache, must-revalidate, max-age=0" },
      { key: "Surrogate-Control", value: "no-store" },
      { key: "Pragma", value: "no-cache" },
      { key: "Expires", value: "0" },
      { key: "X-Surpriz-Build-Id", value: publicBuildId },
    ];
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(self)" },
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }
        ]
      },
      {
        source: "/admin",
        headers: privateAdminHeaders,
      },
      {
        source: "/admin/:path*",
        headers: privateAdminHeaders,
      },
      {
        source: "/api/admin/:path*",
        headers: privateAdminHeaders,
      },
      {
        source: "/api/csrf",
        headers: privateAdminHeaders,
      }
    ];
  }
};

export default nextConfig;
