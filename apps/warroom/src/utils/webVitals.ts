/**
 * Lightweight Web Vitals reporter — 不引入 web-vitals 套件以保持 bundle 小。
 *
 * 只在 dev mode 啟用，使用 PerformanceObserver 蒐集 LCP、FID/INP（粗略）、CLS。
 * Production 若需要詳細指標可改用 `web-vitals` 套件並 lazy-load。
 */

export function startWebVitals(): void {
  if (typeof window === 'undefined' || typeof PerformanceObserver === 'undefined') return
  if (!import.meta.env.DEV) return

  // LCP
  try {
    const lcpObserver = new PerformanceObserver((list) => {
      const entries = list.getEntries()
      const last = entries[entries.length - 1]
      if (last) {
        // eslint-disable-next-line no-console
        console.info('[web-vitals] LCP', Math.round(last.startTime), 'ms')
      }
    })
    lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true })
  } catch {
    // ignore
  }

  // CLS
  try {
    let clsValue = 0
    const clsObserver = new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as PerformanceEntry[]) {
        const e = entry as PerformanceEntry & { hadRecentInput?: boolean; value?: number }
        if (!e.hadRecentInput && typeof e.value === 'number') {
          clsValue += e.value
        }
      }
      // eslint-disable-next-line no-console
      console.info('[web-vitals] CLS', clsValue.toFixed(4))
    })
    clsObserver.observe({ type: 'layout-shift', buffered: true })
  } catch {
    // ignore
  }
}
