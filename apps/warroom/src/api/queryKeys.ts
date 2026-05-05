/**
 * 集中匯出 React Query key factories — 對應 contracts/api-mapping.md。
 *
 * 命名規則：<resource>.<sub-resource>(<params>?) 形成穩定可序列化的 tuple key。
 */

export const policyKeys = {
  all: ['policies'] as const,
  list: () => [...policyKeys.all, 'list'] as const,
  detail: (policyId: string) => [...policyKeys.all, 'detail', policyId] as const,
}

export const episodeKeys = {
  all: ['episodes'] as const,
  list: (filters?: Record<string, unknown>) =>
    [...episodeKeys.all, 'list', filters ?? {}] as const,
  detail: (episodeId: string) => [...episodeKeys.all, 'detail', episodeId] as const,
  trajectory: (episodeId: string) =>
    [...episodeKeys.all, 'trajectory', episodeId] as const,
}

export const inferKeys = {
  all: ['infer'] as const,
  /** infer 為 mutation，此 key 用於 react-query 的 mutationKey 與並發追蹤 */
  invoke: (policyId: string) => [...inferKeys.all, 'invoke', policyId] as const,
}

export const auditKeys = {
  all: ['audit'] as const,
  list: (filters?: Record<string, unknown>) =>
    [...auditKeys.all, 'list', filters ?? {}] as const,
}
