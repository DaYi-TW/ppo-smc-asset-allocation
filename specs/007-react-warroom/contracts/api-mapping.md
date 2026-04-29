# API Mapping Contract

**Feature**: 007-react-warroom
**Date**: 2026-04-29

定義 006 Spring Gateway OpenAPI 端點到前端 React Query hook 的對應規約。所有 hook 位於
`src/hooks/`，所有型別由 `openapi-typescript` 從 006 `services/gateway/src/main/resources/static/openapi.yaml`
生成至 `src/api/types.gen.ts`（不手改）。

---

## Codegen 流程

```
.specify/extensions/openapi/                          # CI 共享路徑
└── gateway-openapi.yaml                              # 由 006 build 階段 dump 並 commit

apps/warroom/
├── package.json
│   └── scripts:
│       gen:api: "openapi-typescript ../../.specify/extensions/openapi/gateway-openapi.yaml -o src/api/types.gen.ts"
│       gen:check: "openapi-typescript ... && git diff --exit-code src/api/types.gen.ts"
```

CI step（GitHub Actions）：
```yaml
- run: npm run gen:check    # 若 types.gen.ts 與 yaml 不同步則 fail
```

---

## 端點 → Hook 對應表

| HTTP Method & Path                          | React Query Hook            | Query Key                              | Stale Time | Cache Time |
|---------------------------------------------|-----------------------------|----------------------------------------|------------|------------|
| GET `/api/v1/policies`                      | `usePolicies()`             | `['policies']`                         | 5 min      | 10 min     |
| GET `/api/v1/policies/{id}`                 | `usePolicyDetail(id)`       | `['policies', id]`                     | 5 min      | 10 min     |
| GET `/api/v1/episodes`                      | `useEpisodeList(filters)`   | `['episodes', filters]`                | 30 sec     | 5 min      |
| GET `/api/v1/episodes/{id}`                 | `useEpisodeDetail(id)`      | `['episodes', id]`                     | 1 min      | 10 min     |
| GET `/api/v1/episodes/{id}/trajectory`      | `useTrajectory(id)`         | `['episodes', id, 'trajectory']`       | 5 min      | 10 min     |
| POST `/api/v1/infer`                        | `useInfer()` (mutation)     | n/a (mutation)                         | n/a        | n/a        |
| POST `/api/v1/episodes/run`                 | `useRunEpisode()` (mutation)| n/a                                    | n/a        | n/a        |
| GET `/api/v1/episodes/stream` (SSE)         | `useEpisodeStream(params)`  | `['stream', params]` (manual)          | infinite   | 1 min      |
| GET `/api/v1/episodes/{id}/audit`           | `useAuditLog(id)`           | `['episodes', id, 'audit']`            | 5 min      | 10 min     |
| GET `/api/v1/health`                        | `useHealthCheck()`          | `['health']`                           | 10 sec     | 30 sec     |

備註：
- `filters` 為 `{ policyId?, status?, from?, to?, page?, pageSize? }`，由呼叫端傳入。
- mutation 不存 cache key；成功後手動 `queryClient.invalidateQueries(['episodes'])`。
- SSE 用 React Query 的 `useQuery` + custom `queryFn` 包裝，refetchOnWindowFocus 關閉。

---

## Hook 簽章標準

每個 hook 必須遵循下列 5 點：

1. **參數顯式**：用具名物件傳遞參數，不接受 positional list。
2. **回傳型別**：明示 `UseQueryResult<TData, ApiErrorViewModel>`。
3. **錯誤類型**：所有錯誤統一轉成 `ApiErrorViewModel`（透過 `client.ts` 的 fetch wrapper）。
4. **無 magic string**：query key 從 `src/api/queryKeys.ts` 集中匯出（避免 typo）。
5. **可被 MSW mock**：handler 在 `src/test/mocks/handlers.ts` 對應一筆。

範例：

```typescript
// src/hooks/useEpisodeList.ts
import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { episodeKeys } from '../api/queryKeys';
import { client } from '../api/client';
import type { ApiErrorViewModel } from '../viewmodels/error';
import type { EpisodeSummaryViewModel } from '../viewmodels/episode';
import type { EpisodeListFilters } from '../api/filters';
import { toEpisodeSummary } from '../api/envelopes';

export function useEpisodeList(
  filters: EpisodeListFilters,
): UseQueryResult<EpisodeSummaryViewModel[], ApiErrorViewModel> {
  return useQuery({
    queryKey: episodeKeys.list(filters),
    queryFn: async ({ signal }) => {
      const dto = await client.get('/api/v1/episodes', { params: filters, signal });
      return dto.items.map(toEpisodeSummary);
    },
    staleTime: 30_000,
    gcTime: 5 * 60_000,
  });
}
```

---

## SSE Hook 標準（`useEpisodeStream`）

```typescript
function useEpisodeStream(params: { policyId: string }): {
  events: TrajectoryFrame[];
  status: 'idle' | 'connecting' | 'open' | 'closed' | 'error';
  error?: ApiErrorViewModel;
  reconnect: () => void;
};
```

實作要點：
- 使用 `EventSource`（瀏覽器原生）；fallback 不需要（Chrome 120+ 支援度 100%）。
- 收到事件 → push 進 React state（最近 1000 個 frame，超過則 FIFO 丟棄前頭，避免 OOM）。
- 連線中斷：自動 retry 3 次（指數退避 1s/2s/4s），失敗後 status=`error`。
- `reconnect()` 手動觸發重連，重設 retry 計數。
- unmount 時務必 `eventSource.close()`，否則造成連線洩漏。

---

## 認證機制

所有 `/api/v1/*` 端點需 JWT Bearer token（006 已啟用 spring-security）：

```typescript
// src/api/client.ts
async function fetchWithAuth(path: string, init?: RequestInit) {
  const token = await getJwt();   // 從 localStorage 或 dev mode hard-code
  return fetch(BASE_URL + path, {
    ...init,
    headers: { ...init?.headers, Authorization: `Bearer ${token}` },
  });
}
```

**Demo 模式**：`VITE_DEMO_MODE=true` 時，token 由前端用 dev-only secret 簽發（HS256），有
效期 24h；MSW handler 不驗 token，僅檢查存在。

**Production**：未來會接 OAuth2／OIDC（屬未來 feature；本 plan 不延伸）。

---

## Idempotency

對所有 mutation hook（`useInfer`、`useRunEpisode`），fetcher 必須自動產生 UUID v4 並
注入 `Idempotency-Key` header：

```typescript
import { v4 as uuidv4 } from 'uuid';

const headers = { 'Idempotency-Key': uuidv4(), ... };
```

key 由前端管理而非 server 端，這樣使用者重試時可重用同一 key（透過 React Query 的
`retry` 機制配合 mutation context）。

---

## 錯誤碼到 i18n 的對應

統一在 `src/api/errorMap.ts`：

```typescript
export const errorCodeToI18nKey: Record<string, string> = {
  POLICY_NOT_FOUND: 'errors.policyNotFound',
  EPISODE_NOT_FOUND: 'errors.episodeNotFound',
  OBSERVATION_DIM_MISMATCH: 'errors.observationDimMismatch',
  OBSERVATION_NAN: 'errors.observationNaN',
  RATE_LIMIT_EXCEEDED: 'errors.rateLimitExceeded',
  CIRCUIT_OPEN: 'errors.circuitOpen',
  GATEWAY_TIMEOUT: 'errors.gatewayTimeout',
  AUTH_INVALID_TOKEN: 'errors.authInvalidToken',
  AUTH_EXPIRED_TOKEN: 'errors.authExpiredToken',
  IDEMPOTENCY_CONFLICT: 'errors.idempotencyConflict',
  // ... 完整列表須對齊 006 contracts/error-codes.md
};

export function resolveErrorMessage(error: ApiErrorViewModel): string {
  const key = errorCodeToI18nKey[error.code] ?? 'errors.unknown';
  return t(key, { defaultValue: error.message });
}
```

---

## API 端點清單（從 006 OpenAPI 摘錄，前端必實作對應 hook）

```
GET  /api/v1/health                         → useHealthCheck
GET  /api/v1/policies                       → usePolicies
GET  /api/v1/policies/{id}                  → usePolicyDetail
GET  /api/v1/episodes                       → useEpisodeList
GET  /api/v1/episodes/{id}                  → useEpisodeDetail
GET  /api/v1/episodes/{id}/trajectory       → useTrajectory
GET  /api/v1/episodes/{id}/audit            → useAuditLog
GET  /api/v1/episodes/stream                → useEpisodeStream (SSE)
POST /api/v1/infer                          → useInfer (mutation)
POST /api/v1/episodes/run                   → useRunEpisode (mutation)
```

不在前端範圍：
- POST `/api/v1/admin/*`（管理員端點，未來 feature）
- POST `/api/v1/policies/upload`（policy 上傳由後端 ops 流程處理）

---

## CI Drift Detection

`.github/workflows/web.yml` 必須包含：

```yaml
- name: Check OpenAPI sync
  run: |
    cd apps/warroom
    npm ci
    npm run gen:api
    git diff --exit-code src/api/types.gen.ts || \
      (echo "::error::types.gen.ts out of sync with gateway-openapi.yaml; run npm run gen:api locally" && exit 1)
```

確保 006 Gateway 改 API 時，前端編譯失敗能在 PR 階段就被發現。
