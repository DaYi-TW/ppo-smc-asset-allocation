/**
 * Empty state — 用於查詢無資料、過濾後 0 筆等情境。
 */

import type { ReactNode } from 'react'

export interface EmptyStateProps {
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export function EmptyState({ title, description, action, className = '' }: EmptyStateProps) {
  return (
    <div
      role="status"
      className={`flex flex-col items-center justify-center gap-sm p-xl text-center text-text-secondary ${className}`}
    >
      <p className="text-lg font-medium text-text-primary">{title}</p>
      {description && <p className="text-sm">{description}</p>}
      {action}
    </div>
  )
}
