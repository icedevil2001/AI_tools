import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm, low-contrast palette. This gets used at the dinner table and
        // sometimes during an episode, when bright screens are unpleasant.
        cream: "#faf7f2",
        ink: "#2c2a27",
      },
    },
  },
  plugins: [],
} satisfies Config;
