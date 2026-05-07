/**
 * 載入骨架 — 用於 React Query pending 狀態，比 spinner 更穩定（不跳版）。
 */

export interface LoadingSkeletonProps {
  /** 預設 1 — 一條矩形 */
  rows?: number
  /** Tailwind utility for height per row（預設 h-4） */
  rowClassName?: string
  /** 整體 wrapper 的額外 class */
  className?: string
  ariaLabel?: string
}

export function LoadingSkeleton({
  rows = 1,
  rowClassName = 'h-4',
  className = '',
  ariaLabel = 'Loading',
}: LoadingSkeletonProps) {
  return (
    <div
      role="status"
      aria-label={ariaLabel}
      aria-busy="true"
      className={`flex flex-col gap-sm ${className}`}
    >
      {Array.from({ length: rows }).map((_, idx) => (
        <div
          key={idx}
          className={`${rowClassName} rounded-sm bg-bg-elevated animate-pulse`}
        />
      ))}
    </div>
  )
}
