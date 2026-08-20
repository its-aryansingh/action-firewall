import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0B1020",
        panel: "#121a33",
        edge: "#1f2a4a",
        brand: "#3395FF",   // Razorpay blue
        allow: "#22C55E",
        block: "#F43F5E",
        muted: "#8FA0C4",
      },
      fontFamily: { sans: ["Inter", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
} satisfies Config;
