import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sidebar: "#0B1020",
        canvas: "#F7F8FC",
        surface: "#FFFFFF",
        primary: {
          DEFAULT: "#2B6EF3",
          hover: "#1F5ED8",
        },
        text: "#192233",
        muted: "#657084",
        border: "#E5E9F0",
        success: "#138A5B",
        warning: "#B7791F",
        danger: "#C23B3B",
      },
      // The CSS variable comes from next/font in app/layout.tsx. Without it,
      // "Inter" here was only ever a wish — the browser had no font to load.
      fontFamily: { sans: ["var(--font-inter)", "Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
