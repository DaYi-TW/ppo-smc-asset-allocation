/**
 * Tailwind preset — 以 CSS variable 為單一資料來源，亮暗主題切換不需 rebuild。
 *
 * 對應 contracts/theme-tokens.md：所有顏色透過 var(--color-*) 注入，
 * tokens.ts 為型別與 default value 來源，CSS variable 由 styles/index.css 宣告。
 */

import type { Config } from 'tailwindcss'

const preset: Partial<Config> = {
  darkMode: 'class',
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
        // 資產品牌色（不隨主題變色）
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
}

export default preset
