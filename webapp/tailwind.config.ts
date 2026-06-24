import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#211A17",
        saffron: "#E8672A",
        maroon: "#641F26",
        sand: "#F4EBDD",
        cream: "#FCF8F1",
        gold: "#C99B52",
      },
      fontFamily: {
        sans: ['"Inter Variable"', '"Noto Sans Devanagari Variable"', "sans-serif"],
        serif: ['"Inter Variable"', '"Noto Sans Devanagari Variable"', "sans-serif"],
      },
      boxShadow: {
        soft: "0 18px 60px rgba(58, 35, 24, 0.10)",
      },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.22s ease-out",
        "accordion-up": "accordion-up 0.22s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
