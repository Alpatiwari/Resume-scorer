/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        paper: '#F6F4EE',
        ink: '#16302A',
        'ink-soft': '#3D5049',
        gold: '#C99A3E',
        'gold-soft': '#EFE3C4',
        line: '#DEDACD',
      },
      fontFamily: {
        display: ['"Fraunces"', 'serif'],
        sans: ['"IBM Plex Sans"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
