/**
 * OverviewPage — US1 戰情總覽（single-page dashboard）。
 *
 * Layout（mockup `mockups/war-room.html` 對應）：
 *   ┌─ Top KPI row（5 卡）──────────────────────────┐
 *   ├─ Timeline scrubber（全寬 brush，同步全圖）──┤
 *   ├──────────────────────────┬─────────────────────┤
 *   │ NAV + drawdown           │ Reward 拆解          │
 *   │ Allocation stacked area  │ 當前配置 by bucket   │
 *   │ K-line + SMC（wide）     │ SMC 事件流           │
 *   └──────────────────────────┴─────────────────────┘
 *
 * 資料源：useEpisodeList() → 預設選 Live (id 後綴 _live)，fallback latest OOS → useEpisodeDetail。
 *
 * Timeline 模式（feature 007 v2）：TimeRangeProvider 提供 [start, end)；
 * 圖表 slice frames，sidebar 顯示「視窗末端」對應的 frame（時光機）。
 */

import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { KLineWithSMC } from '@/components/charts/KLineWithSMC'
import {
  DEFAULT_SMC_VISIBLE,
  type SMCVisibleConfig,
} from '@/components/charts/smcOverlayPrimitive'
import { NavDrawdownChart } from '@/components/charts/NavDrawdownChart'
import { WeightStackedArea } from '@/components/charts/WeightStackedArea'
import { EmptyState } from '@/components/common/EmptyState'
import { LoadingSkeleton } from '@/components/common/LoadingSkeleton'
import { CurrentWeights } from '@/components/panels/CurrentWeights'
import { KPIRow } from '@/components/panels/KPIRow'
import { RewardSidebar } from '@/components/panels/RewardSidebar'
import { SMCEventList } from '@/components/panels/SMCEventList'
import { SMCToggleBar } from '@/components/panels/SMCToggleBar'
import { TimelineScrubber } from '@/components/panels/TimelineScrubber'
import { DataLagBadge } from '@/components/overview/DataLagBadge'
import { FailureToast } from '@/components/overview/FailureToast'
import { LiveRefreshButton } from '@/components/overview/LiveRefreshButton'
import {
  TimeRangeProvider,
  useTimeRange,
} from '@/contexts/TimeRangeContext'
import { useEpisodeDetail } from '@/hooks/useEpisodeDetail'
import { useEpisodeList } from '@/hooks/useEpisodeList'
import { useLiveRefresh } from '@/hooks/useLiveRefresh'
import type { EpisodeDetailViewModel } from '@/viewmodels/episode'
import type { TrajectoryFrame } from '@/viewmodels/trajectory'

function Panel({
  title,
  hint,
  className,
  children,
}: {
  title: string
  hint?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <section
      className={`flex flex-col rounded-xl border border-border bg-bg-surface p-4 ${className ?? ''}`}
    >
      <header className="mb-2 flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold tracking-wide text-text-primary">{title}</h3>
        {hint && <span className="ml-auto text-[11px] text-text-muted">{hint}</span>}
      </header>
      <div className="flex min-h-0 flex-1 flex-col">{children}</div>
    </section>
  )
}

function SidebarCard({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-border bg-bg-surface p-4">
      <h3 className="mb-2.5 text-[13px] font-semibold uppercase tracking-wider text-text-secondary">
        {title}
      </h3>
      {children}
    </section>
  )
}

interface DashboardProps {
  detail: EpisodeDetailViewModel
  frames: ReadonlyArray<TrajectoryFrame>
}

const KLINE_ASSETS = ['NVDA', 'AMD', 'TSM', 'MU', 'GLD', 'TLT'] as const

/** 內層 component — 在 TimeRangeProvider 之內，能讀 useTimeRange()。 */
function Dashboard({ detail, frames }: DashboardProps) {
  const { t } = useTranslation()
  const { range } = useTimeRange(frames.length)
  const [selectedAsset, setSelectedAsset] = useState<string>('NVDA')
  const [smcVisible, setSmcVisible] = useState<SMCVisibleConfig>(DEFAULT_SMC_VISIBLE)

  // 偵測 fixture 是否帶 per-asset OHLC；沒有則 selector 隱藏
  const hasPerAssetOHLC = useMemo(
    () => frames.some((f) => f.ohlcvByAsset && Object.keys(f.ohlcvByAsset).length > 0),
    [frames],
  )

  const overlay = detail.smcOverlayByAsset?.[selectedAsset]

  // 視窗 slice — Recharts 重畫；KLine 內部用 lwc setVisibleLogicalRange 不切資料
  const visibleFrames = useMemo(
    () => frames.slice(range.start, range.end),
    [frames, range.start, range.end],
  )
  // 時光機：sidebar 顯示視窗末端 frame
  const focusFrame = visibleFrames[visibleFrames.length - 1] ?? frames[frames.length - 1]
  const focusReward =
    detail.rewardBreakdown.byStep[Math.max(0, range.end - 1)] ??
    detail.rewardBreakdown.byStep.at(-1)

  return (
    <>
      <KPIRow episode={detail} frames={visibleFrames} />

      <TimelineScrubber frames={frames} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:auto-rows-[360px]">
          <Panel
            title={t('overview.navChart.title')}
            hint="proposed_design §4-2"
          >
            <div className="flex-1">
              <NavDrawdownChart frames={visibleFrames} height={300} />
            </div>
          </Panel>
          <Panel
            title={t('overview.weightChart.title')}
            hint="proposed_design §4-1"
          >
            <div className="flex-1">
              <WeightStackedArea frames={visibleFrames} height={300} />
            </div>
          </Panel>
          <Panel
            className="lg:col-span-2"
            title={t('trajectory.kline.title')}
            hint={hasPerAssetOHLC ? selectedAsset : 'proposed_design §4-3'}
          >
            {hasPerAssetOHLC && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {KLINE_ASSETS.map((a) => (
                  <button
                    key={a}
                    type="button"
                    onClick={() => setSelectedAsset(a)}
                    className={`rounded-md border px-2.5 py-1 text-[11px] font-medium tracking-wide transition-colors ${
                      selectedAsset === a
                        ? 'border-info bg-info/15 text-info'
                        : 'border-border bg-bg-elevated text-text-secondary hover:border-info/40 hover:text-text-primary'
                    }`}
                    aria-pressed={selectedAsset === a}
                  >
                    {a}
                  </button>
                ))}
              </div>
            )}
            <SMCToggleBar value={smcVisible} onChange={setSmcVisible} />
            <div className="flex-1">
              <KLineWithSMC
                frames={frames}
                height={320}
                {...(hasPerAssetOHLC ? { selectedAsset } : {})}
                {...(overlay ? { overlay } : {})}
                visible={smcVisible}
              />
            </div>
          </Panel>
        </div>

        <aside className="flex flex-col gap-3">
          {focusReward && (
            <SidebarCard title={t('overview.rewardSummary.title')}>
              <RewardSidebar reward={focusReward} />
            </SidebarCard>
          )}

          {focusFrame && (
            <SidebarCard title={t('overview.weightChart.title')}>
              <CurrentWeights frame={focusFrame} />
            </SidebarCard>
          )}

          <SidebarCard title={t('overview.smc.title')}>
            <SMCEventList frames={visibleFrames} />
          </SidebarCard>
        </aside>
      </div>
    </>
  )
}

export function OverviewPage() {
  const { t } = useTranslation()

  const listFilters = useMemo(() => ({ pageSize: 10 }), [])
  const listQuery = useEpisodeList(listFilters)
  // FR-021: 預設選 Live tracking episode（id 後綴 `_live`），fallback latest OOS。
  const items = listQuery.data ?? []
  const liveEpisode = items.find((e) => e.episodeId.endsWith('_live'))
  const fallbackEpisode = items.find((e) => !e.episodeId.endsWith('_live'))
  const selectedEpisode = liveEpisode ?? fallbackEpisode
  const detailQuery = useEpisodeDetail(selectedEpisode?.episodeId)

  const detail = detailQuery.data
  const frames = detail?.trajectoryInline ?? []
  const isLoading = listQuery.isPending || detailQuery.isPending

  // Feature 010：Live tracking status + manual refresh
  const liveEpisodeIdForInvalidate = liveEpisode?.episodeId ?? null
  const { status: liveStatusQuery, refresh: liveRefresh } = useLiveRefresh({
    liveEpisodeId: liveEpisodeIdForInvalidate,
  })
  const liveStatus = liveStatusQuery.data
  const dataLagDays = liveStatus?.dataLagDays ?? null
  const isPipelineRunning = liveStatus?.isRunning ?? false
  const lastError = liveStatus?.lastError ?? null
  const lastUpdated = liveStatus?.lastUpdated ?? null

  return (
    <section aria-labelledby="overview-heading" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="overview-heading" className="sr-only">
          {t('overview.title')}
        </h2>
        <div className="flex items-center gap-2">
          <DataLagBadge dataLagDays={dataLagDays} />
        </div>
        <div className="flex items-center gap-2">
          <LiveRefreshButton
            refresh={liveRefresh}
            isPipelineRunning={isPipelineRunning}
          />
        </div>
      </div>

      <FailureToast
        lastError={lastError}
        lastUpdated={lastUpdated}
        refresh={liveRefresh}
      />

      {isLoading ? (
        <LoadingSkeleton />
      ) : !detail || !selectedEpisode ? (
        <EmptyState
          title={t(
            'overview.liveTracking.notStarted',
            'Live tracking 尚未啟動，請按「手動更新到最新」建立。',
          )}
        />
      ) : (
        <TimeRangeProvider totalFrames={frames.length}>
          <Dashboard detail={detail} frames={frames} />
        </TimeRangeProvider>
      )}
    </section>
  )
}
