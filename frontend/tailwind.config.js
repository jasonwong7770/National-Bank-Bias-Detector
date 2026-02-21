/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,jsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        syne: ['Syne', 'sans-serif'],
        mono: ['Space Mono', 'monospace'],
      },
      colors: {
        background: '#0a0a0f',
        card: '#15151f',
        border: '#1e1e2e',
        accent: '#ff3b5c',
        teal: '#00d4aa',
        muted: '#5a5a7a',
      },
    },
  },
  plugins: [],
}
