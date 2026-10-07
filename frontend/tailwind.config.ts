import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#070a0f", 900: "#0b1017", 850: "#0d131b", 800: "#111925", 700: "#1c2634" },
        edge: { DEFAULT: "#1c2634", bright: "#26334a" },
        bull: "#22c58b",
        bear: "#ff5c6c",
        warn: "#f5a623",
        info: "#4c9aff",
        violet: "#9d7bff",
        cyan2: "#37d0d8",
        muted: "#8494ab",
        dim: "#5b6a80",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "SFMono-Regular", "Consolas", "monospace"],
      },
      keyframes: {
        slideIn: { "0%": { opacity: "0", transform: "translateY(-6px)" }, "100%": { opacity: "1", transform: "none" } },
        ring: { "0%": { boxShadow: "0 0 0 0 rgba(76,154,255,.45)" }, "70%": { boxShadow: "0 0 0 8px rgba(76,154,255,0)" }, "100%": { boxShadow: "0 0 0 0 rgba(76,154,255,0)" } },
        pulseRed: { "0%,100%": { boxShadow: "0 0 0 0 rgba(255,92,108,.5)" }, "50%": { boxShadow: "0 0 0 7px rgba(255,92,108,0)" } },
      },
      animation: {
        slideIn: "slideIn .45s ease",
        ring: "ring 1.3s infinite",
        pulseRed: "pulseRed 1.4s infinite",
      },
    },
  },
  plugins: [],
};

export default config;