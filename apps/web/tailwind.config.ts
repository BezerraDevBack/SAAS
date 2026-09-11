// IP — Caramurú Construções — assinatura do autor

import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        caramuru: {
          ink: "#1a2332",
          gold: "#c4a35a",
          sand: "#f4efe4",
        },
      },
    },
  },
  plugins: [],
};

export default config;
