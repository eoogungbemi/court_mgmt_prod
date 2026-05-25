import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        court: {
          navy:  "#1a2e4a",
          gold:  "#c9a84c",
          slate: "#4a5568",
        },
      },
    },
  },
  plugins: [],
};

export default config;
