/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        serif: ['Fraunces', 'ui-serif', 'Georgia', 'Cambria', 'serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        // Warm paper palette — never pure black or pure white
        paper: {
          DEFAULT: '#FAF6EF',   // page background
          soft: '#F3EDE1',      // cards / secondary surface
          tint: '#EFE7D6',      // hover / tertiary
        },
        ink: {
          900: '#1C1814',       // body text (warm espresso)      AA 16.4:1
          700: '#3A332B',       // strong labels                  AA 11.6:1
          500: '#615648',       // body copy                      AA  6.7:1
          400: '#6F6351',       // secondary copy (was #8A7F6E)   AA  5.5:1
          300: '#B3A796',       // placeholders / decorative only
          200: '#D9CFBC',       // subtle dividers
        },
        rule: '#E5DCCB',        // hairline dividers
        terra: {
          DEFAULT: '#B7591F',   // CTA / links
          deep: '#8F3F11',      // pressed
          soft: '#E9C7A9',      // badge bg
        },
        // Grade colors — muted, editorial, not neon
        grade: {
          a: '#5D7A3E',         // moss        AA 4.5:1 on paper
          b: '#64703C',         // olive       AA 5.0:1 (was #7E8F4E / 3.3:1)
          c: '#8A6A1F',         // umber       AA 4.7:1 (was #B58C3E / 2.9:1)
          d: '#8A4F22',         // deep rust   AA 6.1:1 (was #B56934 / 3.9:1)
          f: '#8B3A2E',         // burgundy    AA 7.1:1
        },
      },
      letterSpacing: {
        tightish: '-0.015em',
        tightser: '-0.03em',
      },
      animation: {
        'score-in': 'score-in 900ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'fade-in': 'fade-in 600ms ease-out both',
        'fade-in-up': 'fade-in-up 700ms cubic-bezier(0.22, 1, 0.36, 1) both',
        'rule-draw': 'rule-draw 800ms cubic-bezier(0.22, 1, 0.36, 1) 300ms both',
        'dot-pulse': 'dot-pulse 1.6s ease-in-out infinite',
      },
      keyframes: {
        'score-in': {
          '0%': { transform: 'scale(0.82)', opacity: '0' },
          '60%': { transform: 'scale(1.02)', opacity: '1' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'fade-in-up': {
          '0%': { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'rule-draw': {
          '0%': { transform: 'scaleX(0)' },
          '100%': { transform: 'scaleX(1)' },
        },
        'dot-pulse': {
          '0%, 100%': { opacity: '0.25' },
          '50%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};
