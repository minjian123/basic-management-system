/**
 * 工具栏领域纯函数：动作模型 / 合并与排序 / 权限显隐 / 分态 / 溢出收纳。
 *
 * 纯数据、框架无关：不触 DOM、不请求、不依赖渲染框架；同输入同输出。
 * 工具栏只消费本模型做渲染与回传，业务动作执行与校验归页面。
 */

/** 动作分组（左：主操作 / 批量；右：次要操作 / 帮助）。 */
export type ToolbarGroup = 'left' | 'right'

/** 动作按钮形态（与渲染插件的基础按钮类型对齐）。 */
export type ToolbarActionType = 'primary' | 'default' | 'danger' | 'success' | 'warning' | 'info'

/** 工具栏分态（表单用；列表恒按常规）。 */
export type ToolbarMode = 'readonly' | 'editing'

/** 帮助动作键（基类内建，固定键；永不进溢出）。 */
export const TOOLBAR_HELP_KEY = 'help'

/** 右侧组缺省直显数（其余进「更多」）。 */
export const TOOLBAR_MAX_RIGHT = 3

/** 帮助动作缺省顺序（右侧组末位；不参与业务动作排序）。 */
export const TOOLBAR_HELP_ORDER = 10_000

/** 工具栏动作（声明式数据）。 */
export interface ToolbarAction {
  /** 动作键（集合内唯一；事件回传与覆盖依据）。 */
  key: string
  /** 动作文案（走 i18n）。 */
  label: string
  /** 图标名（统一图标注册表）。 */
  icon?: string
  /** 分组（缺省左组）。 */
  group?: ToolbarGroup
  /** 组内顺序（缺省按声明次序）。 */
  order?: number
  /** 按钮形态（缺省 `default`）。 */
  type?: ToolbarActionType
  /** 朴素按钮。 */
  plain?: boolean
  /** 危险动作（红色语义；确认流程由页面注入）。 */
  danger?: boolean
  /** 禁用（保留悬停原因）。 */
  disabled?: boolean
  /** 单动作加载中。 */
  loading?: boolean
  /** 权限码（未注入权限判定或未声明时不过滤）。 */
  permission?: string
  /** 需要二次确认（语义标记；弹确认由页面完成）。 */
  confirm?: boolean
  /** 测试选择器（保留既有 `data-test`）。 */
  testId?: string
  /** 隐藏（合并后删除）。 */
  hidden?: boolean
  /** 批量动作（随选中态启用；选中数为 0 时禁用）。 */
  batch?: boolean
  /** 生效分态（缺省两态均显示）。 */
  showIn?: ToolbarMode[]
  /** 禁用原因（悬停提示）。 */
  reason?: string
}

/** 页面覆盖（按 `key` 覆盖默认动作的任意字段）。 */
export interface ToolbarActionOverride extends Partial<ToolbarAction> {
  /** 被覆盖的动作键。 */
  key: string
}

/** 工具栏分组结果（帮助动作由基类另行追加，不入本结构）。 */
export interface ToolbarGroups {
  /** 左组（不收纳）。 */
  left: ToolbarAction[]
  /** 右组直显（不含帮助）。 */
  right: ToolbarAction[]
  /** 右组收纳（进「更多」）。 */
  overflow: ToolbarAction[]
}

/** 动作运行态（禁用判定入参）。 */
export interface ToolbarActionState {
  /** 工具栏级加载（禁用全部动作）。 */
  loading?: boolean
  /** 当前选中数（批量动作用）。 */
  selectedCount?: number
}

/**
 * 取动作顺序（未声明时按声明次序）。
 *
 * @param action 动作。
 * @param index 声明次序。
 * @returns number: 排序值。
 */
function orderOf(action: ToolbarAction, index: number): number {
  return typeof action.order === 'number' && Number.isFinite(action.order) ? action.order : index
}

/**
 * 合并默认动作、页面覆盖与页面新增（按 `key` 去重，按 `order` 稳定排序，`hidden` 删除）。
 *
 * 覆盖优先级：页面覆盖 > 页面新增 > 派生默认；同键新增视为对已有动作的再覆盖。
 *
 * @param defaults 派生默认动作集。
 * @param overrides 页面覆盖（按 `key`）。
 * @param extras 页面新增动作（同键时合并到已有动作）。
 * @returns ToolbarAction[]: 合并后的动作（已排序、已剔除隐藏项）。
 */
export function mergeToolbarActions(
  defaults: readonly ToolbarAction[],
  overrides: readonly ToolbarActionOverride[] = [],
  extras: readonly ToolbarAction[] = [],
): ToolbarAction[] {
  const overrideByKey = new Map(overrides.map((entry) => [entry.key, entry]))
  const entries: { action: ToolbarAction; index: number }[] = []
  const indexByKey = new Map<string, number>()

  const append = (base: ToolbarAction): void => {
    const override = overrideByKey.get(base.key)
    const applied = override === undefined ? { ...base } : { ...base, ...override }
    const existing = indexByKey.get(base.key)
    if (existing !== undefined) {
      entries[existing] = { action: { ...entries[existing].action, ...applied }, index: entries[existing].index }
      return
    }
    indexByKey.set(base.key, entries.length)
    entries.push({ action: applied, index: entries.length })
  }

  for (const action of defaults) {
    append(action)
  }
  for (const action of extras) {
    append(action)
  }

  return entries
    .filter((entry) => entry.action.hidden !== true)
    .map((entry) => ({ action: entry.action, order: orderOf(entry.action, entry.index) }))
    .sort((left, right) => left.order - right.order)
    .map((entry) => entry.action)
}

/**
 * 按权限码过滤（无权限不渲染、不占位；未注入判定时不过滤）。
 *
 * @param actions 动作集。
 * @param hasPermission 权限判定（`undefined` 表示不过滤）。
 * @returns ToolbarAction[]: 可见动作。
 */
export function visibleToolbarActions(
  actions: readonly ToolbarAction[],
  hasPermission?: (permission: string) => boolean,
): ToolbarAction[] {
  if (hasPermission === undefined) {
    return actions.filter((action) => action.hidden !== true)
  }
  return actions.filter(
    (action) =>
      action.hidden !== true &&
      (action.permission === undefined || action.permission === '' || hasPermission(action.permission)),
  )
}

/**
 * 按分态过滤（`showIn` 缺省两态均显示）。
 *
 * @param actions 动作集。
 * @param mode 当前分态。
 * @returns ToolbarAction[]: 当前分态可见动作。
 */
export function filterToolbarActions(actions: readonly ToolbarAction[], mode: ToolbarMode): ToolbarAction[] {
  return actions.filter((action) => action.showIn === undefined || action.showIn.includes(mode))
}

/**
 * 判定动作是否禁用（加载 / 显式禁用 / 单动作加载 / 批量无选中）。
 *
 * @param action 动作。
 * @param state 运行态。
 * @returns boolean: 是否禁用。
 */
export function isToolbarActionDisabled(action: ToolbarAction, state: ToolbarActionState = {}): boolean {
  if (state.loading === true || action.disabled === true || action.loading === true) {
    return true
  }
  return action.batch === true && (state.selectedCount ?? 0) <= 0
}

/**
 * 分组并收纳右侧溢出（左组不收纳；帮助动作不参与本函数）。
 *
 * @param actions 动作集（已按权限与分态过滤）。
 * @param maxRight 右侧直显数（小于 1 表示全部收纳）。
 * @returns ToolbarGroups: 左组 / 右组直显 / 溢出。
 */
export function groupToolbarActions(
  actions: readonly ToolbarAction[],
  maxRight: number = TOOLBAR_MAX_RIGHT,
): ToolbarGroups {
  const left = actions.filter((action) => action.key !== TOOLBAR_HELP_KEY && action.group !== 'right')
  const rightAll = actions.filter((action) => action.key !== TOOLBAR_HELP_KEY && action.group === 'right')
  const limit = Number.isFinite(maxRight) ? Math.max(0, Math.floor(maxRight)) : TOOLBAR_MAX_RIGHT
  return {
    left,
    right: rightAll.slice(0, limit),
    overflow: rightAll.slice(limit),
  }
}
