/**
 * 工具栏组件基类（布局族）：动作合并 / 左右分组 / 权限显隐 / 分态 / 溢出 / 帮助位 / 加载态。
 *
 * 继承链：`BaseComponent → BaseSized → BaseLayout → BaseToolbar → BaseListToolbar / BaseFormToolbar`。
 * 具体件（`ListToolbar` / `FormToolbar`）只做渲染与动作回传；页面只传覆盖与新增动作，不改基类。
 * **不含渲染语义**（按钮排布、文案、下拉收纳由具体件与宿主决定），不请求后端。
 */

import { BaseLayout } from './layout'
import {
  TOOLBAR_HELP_KEY,
  TOOLBAR_HELP_ORDER,
  TOOLBAR_MAX_RIGHT,
  filterToolbarActions,
  groupToolbarActions,
  isToolbarActionDisabled,
  mergeToolbarActions,
  visibleToolbarActions,
  type ToolbarAction,
  type ToolbarActionOverride,
  type ToolbarGroups,
  type ToolbarMode,
} from '../domain/toolbar'

/** 帮助入口形态（`header` 顶栏常驻 / `toolbar` 页内按锚点显隐）。 */
export type ToolbarHelpMode = 'toolbar' | 'header'

/** 权限判定（权限码 → 是否具备；未注入不过滤）。 */
export type ToolbarPermChecker = (permission: string) => boolean

/** 通用工具栏基类（抽象）。 */
export abstract class BaseToolbar extends BaseLayout {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'toolbar'
  /** 派生默认动作集（由列表 / 表单派生提供）。 */
  protected defaultActions: ToolbarAction[] = []
  /** 页面覆盖（按 `key`）。 */
  overrides: ToolbarActionOverride[] = []
  /** 页面新增动作。 */
  extras: ToolbarAction[] = []
  /** 权限判定（未注入不过滤）。 */
  permChecker: ToolbarPermChecker | undefined
  /** 右侧组直显数（其余进「更多」）。 */
  maxRight = TOOLBAR_MAX_RIGHT
  /** 表单分态（列表恒按常规，不使用）。 */
  editing = false
  /** 当前选中数（批量动作据此启用）。 */
  selectedCount = 0
  /** 帮助入口可用（元数据锚点或解析结果判定）。 */
  helpAnchorAvailable = false
  /** 帮助入口形态。 */
  helpMode: ToolbarHelpMode = 'toolbar'
  /** 帮助入口文案。 */
  helpLabel = '帮助'
  /** 帮助入口图标名。 */
  helpIcon = 'question'

  /** 帮助动作（基类内建；固定右组末位、永不进溢出、不挂权限码）。 */
  get helpAction(): ToolbarAction {
    return {
      key: TOOLBAR_HELP_KEY,
      label: this.helpLabel,
      icon: this.helpIcon,
      group: 'right',
      order: TOOLBAR_HELP_ORDER,
      type: 'default',
      testId: 'toolbar-help',
    }
  }

  /** 帮助入口是否可见（顶栏常驻；页内按锚点）。 */
  get helpVisible(): boolean {
    return this.helpMode === 'header' || this.helpAnchorAvailable
  }

  /** 当前分态。 */
  get mode(): ToolbarMode {
    return this.editing ? 'editing' : 'readonly'
  }

  /**
   * 设置页面覆盖（整体替换）。
   *
   * @param overrides 覆盖项（按 `key`）。
   */
  setOverrides(overrides: readonly ToolbarActionOverride[]): void {
    this.overrides = [...overrides]
    this.touch()
  }

  /**
   * 追加页面动作（同键时合并到已有动作）。
   *
   * @param actions 新增动作。
   */
  addActions(actions: readonly ToolbarAction[]): void {
    this.extras = [...actions]
    this.touch()
  }

  /**
   * 设置派生默认动作集（子类或页面重置用）。
   *
   * @param actions 默认动作。
   */
  setDefaultActions(actions: readonly ToolbarAction[]): void {
    this.defaultActions = [...actions]
    this.touch()
  }

  /**
   * 设置右侧组直显数。
   *
   * @param value 直显数（0 表示全部收纳）。
   */
  setMaxRight(value: number): void {
    this.maxRight = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : TOOLBAR_MAX_RIGHT
    this.touch()
  }

  /**
   * 注入权限判定（`undefined` 表示不过滤）。
   *
   * @param checker 权限判定。
   */
  setPermChecker(checker: ToolbarPermChecker | undefined): void {
    this.permChecker = checker
    this.touch()
  }

  /**
   * 切换表单分态（列表调用无副作用）。
   *
   * @param value 是否编辑态。
   */
  setEditing(value: boolean): void {
    if (this.editing === value) {
      return
    }
    this.editing = value
    this.touch()
  }

  /**
   * 设置当前选中数（批量动作启用判据）。
   *
   * @param count 选中数（负数归零）。
   */
  setSelectedCount(count: number): void {
    const next = Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0
    if (this.selectedCount === next) {
      return
    }
    this.selectedCount = next
    this.touch()
  }

  /**
   * 设置帮助入口可用性（页内按元数据锚点；顶栏忽略）。
   *
   * @param available 是否可用。
   */
  setHelpAvailable(available: boolean): void {
    if (this.helpAnchorAvailable === available) {
      return
    }
    this.helpAnchorAvailable = available
    this.touch()
  }

  /**
   * 设置帮助入口形态。
   *
   * @param mode 形态（顶栏 / 页内）。
   */
  setHelpMode(mode: ToolbarHelpMode): void {
    if (this.helpMode === mode) {
      return
    }
    this.helpMode = mode
    this.touch()
  }

  /**
   * 合并后的动作集（默认 + 覆盖 + 新增；已排序并剔除隐藏项）。
   *
   * @returns ToolbarAction[]: 合并动作。
   */
  mergedActions(): ToolbarAction[] {
    return mergeToolbarActions(this.defaultActions, this.overrides, this.extras)
  }

  /**
   * 当前可见动作（分态 → 权限过滤；不含帮助动作）。
   *
   * @returns ToolbarAction[]: 可见动作。
   */
  visibleActions(): ToolbarAction[] {
    const merged = this.mergedActions()
    const byMode = filterToolbarActions(merged, this.mode)
    const filtered = visibleToolbarActions(byMode, this.permChecker)
    return filtered.filter((action) => action.key !== TOOLBAR_HELP_KEY)
  }

  /**
   * 分组结果（帮助动作按可见性追加到右组末位，永不进溢出）。
   *
   * @returns ToolbarGroups: 左组 / 右组直显 / 溢出。
   */
  groups(): ToolbarGroups {
    const split = groupToolbarActions(this.visibleActions(), this.maxRight)
    if (!this.helpVisible) {
      return split
    }
    return { left: split.left, right: [...split.right, this.helpAction], overflow: split.overflow }
  }

  /**
   * 取动作定义（含隐藏项；帮助动作不在内）。
   *
   * @param key 动作键。
   * @returns ToolbarAction | undefined: 动作。
   */
  actionOf(key: string): ToolbarAction | undefined {
    return this.mergedActions().find((action) => action.key === key)
  }

  /**
   * 动作是否可见（分态 + 权限）。
   *
   * @param action 动作。
   * @returns boolean: 是否可见。
   */
  isAllowed(action: ToolbarAction): boolean {
    if (action.permission === undefined || action.permission === '' || this.permChecker === undefined) {
      return true
    }
    return this.permChecker(action.permission)
  }

  /**
   * 动作是否禁用（加载 / 显式禁用 / 单动作加载 / 批量无选中）。
   *
   * @param action 动作。
   * @returns boolean: 是否禁用。
   */
  isDisabled(action: ToolbarAction): boolean {
    return isToolbarActionDisabled(action, { loading: this.loading, selectedCount: this.selectedCount })
  }

  /**
   * 动作是否可触发（存在、可见、有权限、未禁用、未加载）。
   *
   * @param key 动作键。
   * @returns boolean: 是否可触发。
   */
  canRun(key: string): boolean {
    const action = this.actionOf(key)
    if (action === undefined || action.hidden === true || !this.isAllowed(action)) {
      return false
    }
    const allowedByMode = action.showIn === undefined || action.showIn.includes(this.mode)
    return allowedByMode && !this.isDisabled(action)
  }

  /** 广播更新（已释放则忽略）。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}

/** 列表工具栏默认动作集（页面按 `key` 覆盖文案 / 权限 / 顺序）。 */
export const LIST_TOOLBAR_DEFAULTS: readonly ToolbarAction[] = [
  { key: 'create', label: '新增', group: 'left', order: 10, type: 'primary' },
  { key: 'refresh', label: '刷新', group: 'left', order: 20 },
  { key: 'batch-toggle', label: '启用 / 停用', group: 'left', order: 30, batch: true },
  { key: 'batch-delete', label: '删除', group: 'left', order: 40, danger: true, batch: true, confirm: true },
  { key: 'close', label: '关闭', group: 'left', order: 50 },
]

/** 列表工具栏基类（抽象）：默认动作集 + 选中态批量动作。 */
export abstract class BaseListToolbar extends BaseToolbar {
  /** 能力键。 */
  override readonly identifier: string = 'list_toolbar'

  constructor() {
    super()
    this.defaultActions = LIST_TOOLBAR_DEFAULTS.map((action) => ({ ...action }))
  }
}

/** 表单工具栏默认动作集（只读 / 编辑分态由 `showIn` 声明）。 */
export const FORM_TOOLBAR_DEFAULTS: readonly ToolbarAction[] = [
  { key: 'edit', label: '修改', group: 'left', order: 10, type: 'primary', showIn: ['readonly'] },
  { key: 'save', label: '保存', group: 'left', order: 20, type: 'primary', showIn: ['editing'] },
  { key: 'cancel', label: '取消', group: 'left', order: 30, showIn: ['editing'] },
  { key: 'delete', label: '删除', group: 'left', order: 40, danger: true, confirm: true, showIn: ['readonly'] },
  { key: 'refresh', label: '刷新', group: 'left', order: 50 },
  { key: 'close', label: '关闭', group: 'left', order: 60 },
]

/** 表单工具栏基类（抽象）：默认动作集 + 只读 / 编辑分态（保存为编辑态唯一主操作）。 */
export abstract class BaseFormToolbar extends BaseToolbar {
  /** 能力键。 */
  override readonly identifier: string = 'form_toolbar'

  constructor() {
    super()
    this.defaultActions = FORM_TOOLBAR_DEFAULTS.map((action) => ({ ...action }))
  }
}
