/**
 * 批量动作编排能力基类：动作定义 / 权限过滤 / 危险与超量确认 / 执行阶段 / 进度 / 部分成功汇总 / 完成后清空。
 *
 * 在选中集合能力基类 `BaseSelection` 之上派生：选中集合是底座，动作编排是其上的一层。
 * **不含渲染语义**（按钮排布、文案、下拉收纳由具体件与宿主决定）；长任务转异步归 `BaseAsyncTask`。
 */

import { BaseSelection, type SelectionKey } from './selection'
import type { BaseAccess } from './access'
import type { BaseNotice } from './notice'

/** 动作执行上下文。 */
export interface BulkActionContext {
  /** 显式选中的行键（跨页全选时为空）。 */
  keys: SelectionKey[]
  /** 是否按当前条件全选（跨页）。 */
  allAcrossPages: boolean
  /** 总记录数。 */
  total: number
  /** 上报进度。 */
  setProgress(current: number, total: number): void
}

/** 动作结果（支持部分成功）。 */
export interface BulkActionResult {
  /** 成功数量。 */
  success: number
  /** 失败数量。 */
  failed: number
  /** 失败明细。 */
  failures?: { key: SelectionKey; reason: string }[]
  /** 结果提示文案（缺省由件层生成）。 */
  message?: string
}

/** 动作定义。 */
export interface BulkActionDef {
  /** 动作键（集合内唯一）。 */
  key: string
  /** 动作名称。 */
  label: string
  /** 图标名。 */
  icon?: string
  /** 危险动作（红色 + 默认二次确认）。 */
  danger?: boolean
  /** 权限码（未注入权限能力时不过滤）。 */
  perm?: string
  /** 强制二次确认。 */
  confirm?: boolean
  /** 确认文案（缺省由件层按动作与数量生成）。 */
  confirmText?: string
  /** 超量阈值（`count >= threshold` 强制确认；缺省取组件级阈值）。 */
  threshold?: number
  /** 处理逻辑（由调用方提供）。 */
  run: (context: BulkActionContext) => BulkActionResult | Promise<BulkActionResult>
}

/** 执行阶段。 */
export type BulkActionPhase = 'idle' | 'confirming' | 'running' | 'done'

/** 执行进度。 */
export interface BulkActionProgress {
  /** 已完成数量。 */
  current: number
  /** 总数。 */
  total: number
}

/** 批量动作编排能力基类（抽象）。 */
export abstract class BaseBulkAction extends BaseSelection {
  /** 能力键。 */
  readonly identifier: string = 'bulk-action'
  /** 动作集合。 */
  actions: BulkActionDef[] = []
  /** 超量确认阈值（0 表示不限制）。 */
  confirmThreshold = 0
  /** 完成后是否清空选择。 */
  clearAfterDone = true
  /** 常用动作直显数（其余收进「更多」；由件层消费）。 */
  maxVisible = 3
  /** 执行阶段。 */
  phase: BulkActionPhase = 'idle'
  /** 待确认动作键（确认阶段）。 */
  pendingActionKey: string | undefined
  /** 执行进度。 */
  progress: BulkActionProgress = { current: 0, total: 0 }
  /** 最近一次动作结果。 */
  lastResult: BulkActionResult | undefined
  /** 权限上下文（注入时按权限码过滤；未注入不过滤）。 */
  access: BaseAccess | undefined
  /** 提示通知（注入时按结果提示；未注入不发通知）。 */
  notice: BaseNotice | undefined
  /** 待确认动作（内部）。 */
  private pendingAction: BulkActionDef | undefined

  /** 是否执行中。 */
  get running(): boolean {
    return this.phase === 'running'
  }

  /** 可见动作（按权限码过滤）。 */
  get visibleActions(): BulkActionDef[] {
    return this.actions.filter((action) => this.isAllowed(action))
  }

  /** 是否存在可见动作。 */
  get hasVisibleActions(): boolean {
    return this.visibleActions.length > 0
  }

  /**
   * 取动作定义。
   *
   * @param key 动作键。
   */
  actionOf(key: string): BulkActionDef | undefined {
    return this.actions.find((action) => action.key === key)
  }

  /**
   * 是否有权执行动作（未注入权限能力或未声明权限码时视为有权）。
   *
   * @param action 动作定义。
   */
  isAllowed(action: BulkActionDef): boolean {
    if (action.perm === undefined || action.perm === '' || this.access === undefined) {
      return true
    }
    return this.access.has(action.perm)
  }

  /**
   * 是否需要二次确认（危险 / 显式声明 / 超量阈值命中）。
   *
   * @param action 动作定义。
   */
  needsConfirm(action: BulkActionDef): boolean {
    if (action.danger === true || action.confirm === true) {
      return true
    }
    const threshold = action.threshold ?? this.confirmThreshold
    return threshold > 0 && this.count >= threshold
  }

  /**
   * 请求执行动作（需确认时进入确认阶段，返回 `undefined`；否则直接执行）。
   *
   * @param key 动作键。
   * @returns 动作结果；无选中 / 无权 / 执行中 / 动作不存在时返回 `undefined`。
   */
  async request(key: string): Promise<BulkActionResult | undefined> {
    const action = this.actionOf(key)
    if (action === undefined || !this.isAllowed(action) || this.running || this.phase === 'confirming') {
      return undefined
    }
    if (this.count === 0) {
      return undefined
    }
    if (this.needsConfirm(action)) {
      this.pendingAction = action
      this.pendingActionKey = action.key
      this.phase = 'confirming'
      this.touch()
      return undefined
    }
    return this.execute(action)
  }

  /**
   * 确认当前待确认动作并执行。
   *
   * @returns 动作结果；无待确认动作时返回 `undefined`。
   */
  async confirm(): Promise<BulkActionResult | undefined> {
    const action = this.pendingAction
    if (this.phase !== 'confirming' || action === undefined) {
      return undefined
    }
    this.pendingAction = undefined
    this.pendingActionKey = undefined
    return this.execute(action)
  }

  /** 取消确认（阶段回 `idle`，不动选中集合）。 */
  cancel(): void {
    if (this.phase !== 'confirming') {
      return
    }
    this.pendingAction = undefined
    this.pendingActionKey = undefined
    this.phase = 'idle'
    this.touch()
  }

  /**
   * 直接执行动作（跳过确认）。
   *
   * @param key 动作键。
   * @returns 动作结果；无选中 / 无权 / 执行中 / 动作不存在时返回 `undefined`。
   */
  async run(key: string): Promise<BulkActionResult | undefined> {
    const action = this.actionOf(key)
    if (action === undefined || !this.isAllowed(action) || this.running || this.phase === 'confirming') {
      return undefined
    }
    if (this.count === 0) {
      return undefined
    }
    return this.execute(action)
  }

  /**
   * 汇总结果：记最近结果、置完成阶段、按需提示与清空选择。
   *
   * @param result 动作结果。
   */
  applyResult(result: BulkActionResult): void {
    this.lastResult = result
    this.phase = 'done'
    if (this.notice !== undefined) {
      const content = result.message ?? `成功 ${result.success} 项，失败 ${result.failed} 项`
      this.notice.enqueue(content, result.failed > 0 ? 'warning' : 'success')
    }
    if (this.clearAfterDone) {
      this.clear()
    }
    this.touch()
  }

  /** 重置执行状态（不清选中集合）。 */
  resetAction(): void {
    this.pendingAction = undefined
    this.pendingActionKey = undefined
    this.phase = 'idle'
    this.progress = { current: 0, total: 0 }
    this.lastResult = undefined
    this.touch()
  }

  /**
   * 执行动作（内部：置运行阶段 → 执行 → 汇总；异常记为整体失败）。
   *
   * @param action 动作定义。
   */
  private async execute(action: BulkActionDef): Promise<BulkActionResult> {
    this.pendingAction = undefined
    this.pendingActionKey = undefined
    this.phase = 'running'
    this.progress = { current: 0, total: this.count }
    this.touch()

    const context: BulkActionContext = {
      keys: this.allAcrossPages ? [] : [...this.selected],
      allAcrossPages: this.allAcrossPages,
      total: this.total,
      setProgress: (current, total) => {
        this.progress = { current, total }
        if (!this.isDisposed) {
          this.notifyLifecycle('update')
        }
      },
    }

    let result: BulkActionResult
    try {
      result = await action.run(context)
    } catch (error) {
      const reason = error instanceof Error && error.message !== '' ? error.message : '执行失败'
      result = { success: 0, failed: this.count, message: reason }
    }
    this.applyResult(result)
    return result
  }
}
