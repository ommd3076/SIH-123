import type { NextConfig } from "next";

const BRIDGE_PORT = 8010;

const nextConfig: NextConfig = {
  output: "standalone",
  allowedDevOrigins: ["*.space-z.ai"],
  reactStrictMode: false,
  async rewrites() {
    // When the dashboard is opened on an origin that does NOT terminate the
    // XTransformPort gateway convention (e.g. localhost:3000 directly),
    // proxy bridge traffic ourselves so the app works on any origin.
    return [
      {
        // Next normalizes "/socket.io/" to "/socket.io" (308) before rewrites;
        // python-socketio serves the trailing-slash route, so restore it here.
        source: "/socket.io",
        has: [{ type: "query", key: "XTransformPort", value: String(BRIDGE_PORT) }],
        destination: `http://localhost:${BRIDGE_PORT}/socket.io/`,
      },
      {
        source: "/socket.io/:path*",
        has: [{ type: "query", key: "XTransformPort", value: String(BRIDGE_PORT) }],
        destination: `http://localhost:${BRIDGE_PORT}/socket.io/:path*`,
      },
      {
        source: "/api/:path*",
        has: [{ type: "query", key: "XTransformPort", value: String(BRIDGE_PORT) }],
        destination: `http://localhost:${BRIDGE_PORT}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
