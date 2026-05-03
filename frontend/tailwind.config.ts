import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Surface scale — pitch black to barely-there grey
        "surface-0": "#080808",
        "surface-1": "#0f0f0f",
        "surface-2": "#161616",
        "surface-3": "#1e1e1e",
        "surface-4": "#262626",

        // Accent — electric green (Vercel/Linear energy)
        accent: "#00e5a0",
        "accent-dim": "#00b87a",
        "accent-glow": "rgba(0,229,160,0.12)",

        // Danger
        danger: "#ff3b30",
        "danger-dim": "#cc2f26",

        // Warning
        warning: "#ffb800",

        // Text scale
        "text-primary": "#f0f0f0",
        "text-secondary": "#8a8a8a",
        "text-muted": "#4a4a4a",
        "text-disabled": "#2e2e2e",

        // Borders
        border: "#1f1f1f",
        "border-bright": "#2e2e2e",
      },

      fontFamily: {
        sans: ["DM Sans", "system-ui", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "monospace"],
      },

      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "1rem" }],
      },

      boxShadow: {
        "accent-sm": "0 0 0 1px rgba(0,229,160,0.3)",
        "accent-md": "0 0 20px rgba(0,229,160,0.15)",
        "accent-lg": "0 0 40px rgba(0,229,160,0.1)",
        "surface-up": "0 -1px 0 0 #1f1f1f",
      },

      animation: {
        "cursor-blink": "blink 1s step-end infinite",
        "fade-in": "fadeIn 0.2s ease-out",
        "slide-up": "slideUp 0.25s ease-out",
        "pulse-accent": "pulseAccent 2s ease-in-out infinite",
      },

      keyframes: {
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        fadeIn: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        slideUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulseAccent: {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(0,229,160,0)" },
          "50%": { boxShadow: "0 0 20px 4px rgba(0,229,160,0.15)" },
        },
      },

      backgroundImage: {
        "grid-pattern":
          "linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)",
        "gradient-radial-accent":
          "radial-gradient(ellipse 60% 40% at 50% 0%, rgba(0,229,160,0.08) 0%, transparent 70%)",
      },

      backgroundSize: {
        grid: "40px 40px",
      },
    },
  },
  plugins: [],
};

export default config;
