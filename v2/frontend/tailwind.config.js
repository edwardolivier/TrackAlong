/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          900: '#0f172a',
          800: '#1e293b',
          700: '#334155',
          600: '#475569',
        },
        sky: {
          400: '#38bdf8',
          500: '#0ea5e9',
        },
      },
    },
  },
  plugins: [],
}
