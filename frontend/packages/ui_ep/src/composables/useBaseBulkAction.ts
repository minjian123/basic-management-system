/** 批量动作编排投影：把核心批量动作编排能力基类 `BaseBulkAction` 投影为组合式（选中集合 + 动作 / 确认 / 进度 / 结果）。 */

import {
  BaseAccess,
  BaseBulkAction,
  type BulkActionDef,
  type BulkActionPhase,
  type BulkActionProgress,
  type BulkActionResult,
  type SelectionKey,
  type SelectionMode,
  type SelectionSummary,
} from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体批量动作件（可实例化）。 */
class Bulk extends BaseBulkAction {}

/** 函数式权限判定（内联权限上下文）。 */
class InlineAccess extends BaseAccess {
  /** 判定函数。 */
  private readonly check: (code: string) => boolean

  /**
   * 构造内联权限上下文。
   *
   * @param check 判定函数。
   */
  constructor(check: (code: string) => boolean) {
    super()
    this.check = check
  }

  /**
   * 是否具备某权限码（委托判定函数）。
   *
   * @param code 权限码。
   */
  override has(code: string): boolean {
    return this.check(code)
  }
}

/** 选项。 */
export interface UseBaseBulkActionOptions {
  /** 动作集合。 */
  actions?: BulkActionDef[]
  /** 选择模式（缺省 `cross-page`，允许跨页全选）。 */
  mode?: SelectionMode
  /** 总记录数。 */
  total?: number
  /** 当前页行键。 */
  pageKeys?: SelectionKey[]
  /** 初始选中集合。 */
  selected?: SelectionKey[]
  /** 超量确认阈值（0 表示不限制）。 */
  confirmThreshold?: number
  /** 完成后是否清空选择（缺省 `true`）。 */
  clearAfterDone?: boolean
  /** 常用动作直显数。 */
  maxVisible?: number
  /** 函数式权限判定（未提供时不过滤）。 */
  permChecker?: (perm: string) => boolean
}

/** `useBaseBulkAction` 返回面。 */
export interface UseBaseBulkActionResult {
  /** 批量动作编排基类实例。 */
  bulk: BaseBulkAction
  /** 选中键（响应式）。 */
  selected: Ref<SelectionKey[]>
  /** 已选数量（响应式）。 */
  count: Ref<number>
  /** 选中摘要（响应式）。 */
  summary: Ref<SelectionSummary>
  /** 可见动作（权限过滤后，响应式）。 */
  visibleActions: Ref<BulkActionDef[]>
  /** 执行阶段（响应式）。 */
  phase: Ref<BulkActionPhase>
  /** 是否执行中（响应式）。 */
  running: Ref<boolean>
  /** 待确认动作键（响应式）。 */
  pendingActionKey: Ref<string | undefined>
  /** 执行进度（响应式）。 */
  progress: Ref<BulkActionProgress>
  /** 最近结果（响应式）。 */
  lastResult: Ref<BulkActionResult | undefined>
  /** 设置动作集合。 */
  setActions: (actions: BulkActionDef[]) => void
  /** 设置总记录数。 */
  setTotal: (total: number) => void
  /** 设置当前页行键。 */
  setPageKeys: (keys: SelectionKey[]) => void
  /** 设置选中态。 */
  select: (key: SelectionKey, selected?: boolean) => void
  /** 跨页全选。 */
  selectAllAcrossPages: () => void
  /** 清空选中集合。 */
  clear: () => void
  /** 整体回写选中集合（按内容比较）。 */
  replace: (keys: SelectionKey[]) => void
  /** 是否需要二次确认。 */
  needsConfirm: (key: string) => boolean
  /** 请求执行（需确认时进入确认阶段并返回 `undefined`）。 */
  request: (key: string) => Promise<BulkActionResult | undefined>
  /** 确认执行。 */
  confirm: () => Promise<BulkActionResult | undefined>
  /** 取消确认。 */
  cancel: () => void
  /** 直接执行（跳过确认）。 */
  run: (key: string) => Promise<BulkActionResult | undefined>
  /** 重置执行状态（不清选中集合）。 */
  resetAction: () => void
}

/**
 * 使用批量动作编排投影。
 *
 * @param options 选项。
 * @returns 批量动作基类实例与响应式面。
 */
export function useBaseBulkAction(options: UseBaseBulkActionOptions = {}): UseBaseBulkActionResult {
  const bulk = new Bulk()
  bulk.actions = options.actions ?? []
  bulk.setMode(options.mode ?? 'cross-page')
  bulk.confirmThreshold = options.confirmThreshold ?? 0
  bulk.clearAfterDone = options.clearAfterDone ?? true
  bulk.maxVisible = options.maxVisible ?? 3
  if (options.permChecker !== undefined) {
    const check = options.permChecker
    bulk.access = new InlineAccess((code) => check(code))
  }
  if (options.total !== undefined) {
    bulk.setTotal(options.total)
  }
  if (options.pageKeys !== undefined) {
    bulk.setPageKeys(options.pageKeys)
  }
  if (options.selected !== undefined) {
    bulk.replace(options.selected)
  }

  const selected = ref<SelectionKey[]>([...bulk.selected])
  const count = ref(bulk.count)
  const summary = ref(bulk.summary)
  const visibleActions = ref<BulkActionDef[]>(bulk.visibleActions)
  const phase = ref<BulkActionPhase>(bulk.phase)
  const running = ref(bulk.running)
  const pendingActionKey = ref<string | undefined>(bulk.pendingActionKey)
  const progress = ref<BulkActionProgress>({ ...bulk.progress })
  const lastResult = ref<BulkActionResult | undefined>(bulk.lastResult)

  /** 从基类实例同步响应式面。 */
  const sync = (): void => {
    selected.value = [...bulk.selected]
    count.value = bulk.count
    summary.value = bulk.summary
    visibleActions.value = bulk.visibleActions
    phase.value = bulk.phase
    running.value = bulk.running
    pendingActionKey.value = bulk.pendingActionKey
    progress.value = { ...bulk.progress }
    lastResult.value = bulk.lastResult
  }

  const off = bulk.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    bulk,
    selected,
    count,
    summary,
    visibleActions,
    phase,
    running,
    pendingActionKey,
    progress,
    lastResult,
    setActions: (actions) => {
      bulk.actions = actions
      sync()
    },
    setTotal: (total) => {
      bulk.setTotal(total)
      sync()
    },
    setPageKeys: (keys) => {
      bulk.setPageKeys(keys)
      sync()
    },
    select: (key, isSelected) => {
      bulk.select(key, isSelected)
      sync()
    },
    selectAllAcrossPages: () => {
      bulk.selectAllAcrossPages()
      sync()
    },
    clear: () => {
      bulk.clear()
      sync()
    },
    replace: (keys) => {
      bulk.replace(keys)
      sync()
    },
    needsConfirm: (key) => {
      const action = bulk.actionOf(key)
      return action === undefined ? false : bulk.needsConfirm(action)
    },
    request: async (key) => {
      const result = await bulk.request(key)
      sync()
      return result
    },
    confirm: async () => {
      const result = await bulk.confirm()
      sync()
      return result
    },
    cancel: () => {
      bulk.cancel()
      sync()
    },
    run: async (key) => {
      const result = await bulk.run(key)
      sync()
      return result
    },
    resetAction: () => {
      bulk.resetAction()
      sync()
    },
  }
}
