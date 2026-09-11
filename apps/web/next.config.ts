// IP — Caramurú Construções — assinatura do autor

import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  transpilePackages: ["@caramuru/contracts"],
  outputFileTracingRoot: path.resolve(__dirname, "../.."),
};

export default nextConfig;
