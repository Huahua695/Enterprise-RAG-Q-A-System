/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#8B6F47',
          light: '#A68B5A',
          dark: '#6B5635',
        },
        accent: {
          DEFAULT: '#C2703E',
          light: '#D4895A',
          dark: '#A85A2E',
        },
        warm: {
          bg: '#FAF8F5',
          surface: '#FFFFFF',
          border: '#E8E0D5',
          text: '#2D2D2D',
          textSecondary: '#6B6B6B',
        }
      }
    },
  },
  plugins: [],
}
