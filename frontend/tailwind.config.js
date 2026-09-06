/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0a0a0c",
          elevated: "#111114",
          overlay: "rgba(255,255,255,0.03)",
        },
        border: {
          DEFAULT: "rgba(255,255,255,0.08)",
          subtle: "rgba(255,255,255,0.05)",
          strong: "rgba(255,255,255,0.12)",
        },
        accent: {
          DEFAULT: "#64d2ff",
          muted: "rgba(100,210,255,0.15)",
          soft: "rgba(100,210,255,0.08)",
        },
        muted: {
          DEFAULT: "#8e8e93",
          foreground: "#aeaeb2",
        },
        success: "#30d158",
        warning: "#ffd60a",
        danger: "#ff453a",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Display",
          "SF Pro Text",
          "Inter",
          "Segoe UI",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "SF Mono",
          "JetBrains Mono",
          "Menlo",
          "Monaco",
          "Consolas",
          "ui-monospace",
          "monospace",
        ],
      },
      boxShadow: {
        glass: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)",
        "glass-sm": "0 4px 16px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.04)",
        glow: "0 0 24px rgba(100,210,255,0.15)",
      },
      backdropBlur: {
        glass: "20px",
        xs: "2px",
      },
      animation: {
        "fade-in": "fadeIn 0.35s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
        "pulse-soft": "pulseSoft 2s ease-in-out infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.6" },
        },
      },
    },
  },
  plugins: [],
};
