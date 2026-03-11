/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'glass-border': 'rgba(255, 255, 255, 0.12)',
        'glass-border-subtle': 'rgba(255, 255, 255, 0.07)',
        'glass-fill-soft': 'rgba(255, 255, 255, 0.045)',
        'glass-fill-strong': 'rgba(255, 255, 255, 0.08)',
        'text-primary': '#f4f6f8',
        'text-secondary': 'rgba(244, 246, 248, 0.78)',
        'text-muted': 'rgba(244, 246, 248, 0.48)',
        amber: '#ffca94',
        'amber-text': 'rgba(255, 212, 168, 0.96)',
        'amber-glow': 'rgba(255, 188, 96, 0.16)',
        'amber-fill': 'rgba(255, 188, 96, 0.12)',
        'confidence-high': '#ff857a',
        'confidence-medium': '#ffd870',
        'confidence-low': '#8be0b3',
      },
      borderRadius: {
        shell: '22px',
        control: '16px',
        pill: '999px',
      },
      fontFamily: {
        sans: ['"Helvetica Neue"', '-apple-system', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
