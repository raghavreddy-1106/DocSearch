/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#F7F8FA',
        surface: '#FFFFFF',
        primary: {
          text: '#172033',
          accent: '#3B82F6', // Muted blue
        },
        secondary: {
          text: '#667085',
        },
        border: '#E4E7EC',
        success: '#10B981', // Muted green
        warning: '#F59E0B', // Muted amber
        danger: '#EF4444', // Muted red
      }
    },
  },
  plugins: [],
}
