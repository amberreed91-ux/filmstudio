/** Cinematic Command HUD — Tailwind design tokens (Fee Fee Anne Studios).
 *
 * Tailwind v4 reads theme natively via `@theme` in CSS; this config file
 * keeps the canonical token table in one place and is wired into
 * `src/index.css` via `@config`. Token pairs in the spec are exposed as
 * DEFAULT + `-alt` (e.g. graphite-l1 / graphite-l1-alt).
 *
 * @type {import('tailwindcss').Config}
 */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Base surfaces
        void: '#050505',
        'graphite-l1': '#0B0F17',
        'graphite-l1-alt': '#131313',
        'graphite-l2': '#121824',
        'graphite-l2-alt': '#1c1b1b',
        'high-surface': '#2a2a2a',
        'high-surface-alt': '#353534',
        // Glass borders
        'hairline-slate': '#1E293B',
        'hairline-slate-alt': '#353534',
        'active-slate': '#334155',
        'active-slate-alt': '#494454',
        // Energy (violet)
        'energy-core': '#8B5CF6',
        'energy-core-alt': '#d0bcff',
        'energy-deep': '#6D28D9',
        'energy-deep-alt': '#a078ff',
        'energy-abyss': '#4C1D95',
        'energy-abyss-alt': '#340080',
        // Status
        verified: '#10B981',
        'verified-alt': '#4edea3',
        normalization: '#F59E0B',
        'normalization-alt': '#ffb95f',
        huderror: '#EF4444',
        'huderror-alt': '#ffb4ab',
        // Telemetry type
        'silver-high': '#E2E8F0',
        'silver-high-alt': '#e5e2e1',
        'silver-low': '#94A3B8',
        'silver-low-alt': '#cbc3d7',
      },
      fontFamily: {
        headline: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        body: ['Geist', 'system-ui', 'sans-serif'],
        label: ['"JetBrains Mono"', 'monospace'],
      },
      backdropBlur: {
        '2xl': '40px',
        '3xl': '64px',
      },
    },
  },
  plugins: [],
}
