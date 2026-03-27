import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        "nu-purple": {
          DEFAULT: "#4E2A84",
          50: "#F3EFF8",
          100: "#E2D6F0",
          200: "#C5ADE1",
          300: "#A884D2",
          400: "#7B4FB3",
          500: "#4E2A84",
          600: "#3E216A",
          700: "#2F194F",
          800: "#1F1035",
          900: "#10081A",
        },
      },
    },
  },
  plugins: [],
};

export default config;
