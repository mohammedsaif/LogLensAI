/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 950: "#0b1426", 900: "#0f1d36", 800: "#152a4d", 700: "#1e3a64", 600: "#2a4d80" },
        sev: {
          critical: "#a21caf",
          error: "#dc2626",
          warn: "#ca8a04",
          info: "#0d9488",
          debug: "#94a3b8",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
