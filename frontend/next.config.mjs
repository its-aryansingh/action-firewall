import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = path.dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  outputFileTracingRoot: projectRoot,
  // Emits .next/standalone: a server with only the packages actually imported,
  // which is what frontend/Dockerfile ships. Harmless for `next dev` and
  // `next start` locally; required for the container image to be small and to
  // run without node_modules.
  output: "standalone",
};
export default nextConfig;
