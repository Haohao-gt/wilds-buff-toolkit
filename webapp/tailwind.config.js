/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        sky1: '#74CBF4',
        sky2: '#2F86D6',
        deep: '#154C86',
        panel: '#10406F',
        panel2: '#17538C',
        gold: '#FFC93C',
        gold2: '#F0A21C',
        brown: '#4A2A05',
        cream: '#FFF6DC',
        teal: '#46D6CE',
        lav: '#B78CFF',
        inkblue: '#0C2E52',
      },
      fontFamily: {
        sans: ['HarmonyOS Sans SC', 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', 'sans-serif'],
        mono: ['Consolas', 'Cascadia Mono', 'monospace'],
        serifroman: ['Times New Roman', 'serif'],
      },
    },
  },
  plugins: [],
}
