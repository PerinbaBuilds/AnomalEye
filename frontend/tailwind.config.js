/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Bank-grade dark palette with a Société-Générale-style red accent.
        ink: {
          900: "#0a0e17",
          800: "#0f1420",
          700: "#151b2b",
          600: "#1c2436",
          500: "#28324a",
          400: "#3a4560",
        },
        panel: "#111725",
        panel2: "#161d2e",
        line: "#232c42",
        accent: {
          DEFAULT: "#e60028",
          soft: "#ff3355",
          dim: "#8f0019",
        },
        risk: {
          high: "#ef4444",
          medium: "#f59e0b",
          low: "#22c55e",
        },
        muted: "#8a93a6",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(230,0,40,0.3), 0 0 20px rgba(230,0,40,0.15)",
      },
    },
  },
  plugins: [],
};
