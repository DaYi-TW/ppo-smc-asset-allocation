/**
 * 暫時性首頁佔位元件 — 將於 Phase 2 T040-T044 AppShell + Router 完成後移除。
 */
export function Placeholder() {
  return (
    <div className="flex h-screen items-center justify-center bg-bg-base text-fg-primary">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">PPO + SMC War Room</h1>
        <p className="mt-2 text-sm text-fg-muted">
          Phase 1 scaffold ready · waiting for Phase 2
        </p>
      </div>
    </div>
  )
}
