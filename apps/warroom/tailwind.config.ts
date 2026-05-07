import type { Config } from 'tailwindcss'

/**
 * Tailwind config — 與 src/theme/tailwind-preset.ts 同步維護。
 *
 * 為避免 tsc 在 vite/web 與 node 兩個 project 間因共享 src/ 檔案造成
 * "File not in project" 衝突，preset 內容直接在此處 inline。
 * src/theme/tailwind-preset.ts 仍保留作為 token 映射的單一文件來源（被
 * Storybook、設計檔、文件引用）。
 */
const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          base: 'var(--color-bg-base)',
          surface: 'var(--color-bg-surface)',
          elevated: 'var(--color-bg-elevated)',
        },
        text: {
          primary: 'var(--color-text-primary)',
          secondary: 'var(--color-text-secondary)',
          muted: 'var(--color-text-muted)',
        },
        border: {
          DEFAULT: 'var(--color-border-default)',
          strong: 'var(--color-border-strong)',
        },
        primary: {
          DEFAULT: 'var(--color-primary-default)',
          hover: 'var(--color-primary-hover)',
        },
        success: 'var(--color-success)',
        danger: 'var(--color-danger)',
        warn: 'var(--color-warn)',
        info: 'var(--color-info)',
        choch: 'var(--color-choch)',
        'ob-demand': 'var(--color-ob-demand)',
        'ob-supply': 'var(--color-ob-supply)',
        cash: 'var(--color-cash)',
        asset: {
          nvda: '#76B900',
          amd: '#ED1C24',
          tsm: '#CC0000',
          mu: '#B71F31',
          gld: '#FFD700',
          tlt: '#1E40AF',
          cash: '#64748B',
        },
      },
      fontFamily: {
        sans: 'var(--font-family-sans)',
        mono: 'var(--font-family-mono)',
      },
      fontSize: {
        xs: 'var(--font-size-xs)',
        sm: 'var(--font-size-sm)',
        base: 'var(--font-size-base)',
        lg: 'var(--font-size-lg)',
        xl: 'var(--font-size-xl)',
        '2xl': 'var(--font-size-2xl)',
        '3xl': 'var(--font-size-3xl)',
      },
      spacing: {
        xs: 'var(--space-xs)',
        sm: 'var(--space-sm)',
        md: 'var(--space-md)',
        lg: 'var(--space-lg)',
        xl: 'var(--space-xl)',
        '2xl': 'var(--space-2xl)',
      },
      borderRadius: {
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      zIndex: {
        base: 'var(--z-base)',
        overlay: 'var(--z-overlay)',
        modal: 'var(--z-modal)',
        tooltip: 'var(--z-tooltip)',
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
}

export default config
