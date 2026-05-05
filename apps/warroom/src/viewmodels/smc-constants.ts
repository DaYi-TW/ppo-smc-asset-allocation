/**
 * SMC 相關常數 — 與型別分離以便 import 不觸發 tree-shaking 副作用。
 */

import type { SMCMarkerKind } from './smc'

export const ALL_SMC_KINDS: ReadonlyArray<SMCMarkerKind> = [
  'BOS_BULL',
  'BOS_BEAR',
  'CHOCH_BULL',
  'CHOCH_BEAR',
  'FVG',
  'OB',
]
