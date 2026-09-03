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
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
          muted: "var(--accent-muted)",
          foreground: "var(--accent-foreground)",
        },
        ink: {
          DEFAULT: "var(--ink)",
          secondary: "var(--ink-secondary)",
        },
        surface: {
          DEFAULT: "var(--surface)",
          elevated: "var(--surface-elevated)",
        },
        line: {
          DEFAULT: "var(--border)",
          strong: "var(--border-strong)",
        },
        soft: "var(--muted)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "ui-serif", "Georgia", "serif"],
      },
      fontSize: {
        "display-xl": [
          "3.5rem",
          { lineHeight: "1.08", letterSpacing: "-0.03em", fontWeight: "560" },
        ],
        "display-lg": [
          "2.75rem",
          { lineHeight: "1.12", letterSpacing: "-0.025em", fontWeight: "560" },
        ],
        "heading-lg": [
          "2rem",
          { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" },
        ],
        "heading-md": [
          "1.375rem",
          { lineHeight: "1.3", letterSpacing: "-0.015em", fontWeight: "600" },
        ],
      },
      maxWidth: {
        content: "68rem",
      },
      spacing: {
        section: "6.5rem",
        "section-sm": "4.5rem",
      },
    },
  },
  plugins: [],
};
export default config;
