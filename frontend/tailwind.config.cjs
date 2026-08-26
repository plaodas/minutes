module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        'bg-default': 'var(--bg-default)',
        'bg-surface': 'var(--bg-surface)',
        'text-primary': 'var(--text-primary)',
        muted: 'var(--muted)',
        accent: 'var(--accent)'
      }
    }
  },
  plugins: []
}
