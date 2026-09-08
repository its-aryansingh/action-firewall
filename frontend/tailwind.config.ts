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
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
