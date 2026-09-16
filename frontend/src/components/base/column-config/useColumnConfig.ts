/**
 * 列配置片段（`column-config`）：列的显隐、顺序、宽度、冻结与持久化。
 *
 * 契约见《组件设计 · 列配置片段》：`visibleColumns` / `toggle` / `move` / `setWidth` / `freeze` /
 * `reset` / `save` / `restore`（通用表格与明细区共用）。
 * **组合依赖**：`persisted-state`（本地即时 + 远端偏好同步）。
 */

import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'
import { usePersistedState } from '../persisted-state/usePersistedState'

/** 列定义（表格列的最小形状） */
export interface ColumnConfigItem {
  /** 列标识（持久化键） */
  key: string
  title: string
  /** 默认宽度（px） */
  width?: number
  /** 是否默认隐藏 */
  hidden?: boolean
  /** 冻结方向（`left` / `right`） */
  fixed?: 'left' | 'right'
  /** 是否允许隐藏（如操作列常驻） */
  lockVisible?: boolean
  [key: string]: unknown
}

/** 列配置片段参数 */
export interface UseColumnConfigOptions {
  /** 列定义（业务给定，作为默认态） */
  columns?: MaybeRefOrGetter<ColumnConfigItem[]>
  /** 持久化键（缺省 `column-config`；建议按表标识区分） */
  storageKey?: string
  minWidth?: MaybeRefOrGetter<number>
  maxWidth?: MaybeRefOrGetter<number>
  /** 作用域（多租户 / 多模块） */
  scope?: MaybeRefOrGetter<string | undefined>
}

/** 列配置片段返回值 */
export interface UseColumnConfigReturn {
  readonly allColumns: ColumnConfigItem[]
  readonly visibleColumns: ColumnConfigItem[]
  readonly hiddenKeys: string[]
  readonly isDirty: boolean
  toggle: (key: string, visible?: boolean) => void
  move: (from: number, to: number) => void
  setWidth: (key: string, width: number) => void
  freeze: (key: string, position: 'left' | 'right' | false) => void
  reset: () => void
  /** 保存到本地 / 远端（`persisted-state` 的 `set`） */
  save: () => void
  /** 从本地 / 远端恢复 */
  restore: () => Promise<void>
}

/** 持久化的列状态 */
interface ColumnState {
  hidden: string[]
  widths: Record<string, number>
  order: string[]
  fixed: Record<string, 'left' | 'right'>
}

/**
 * 获取列配置能力。
 *
 * 用法：`const columnConfig = useColumnConfig({ columns, storageKey: 'sys-user-table' })`；
 * 表格渲染 `columnConfig.visibleColumns`，用户改动后 `save()` 落本地（远端偏好在接入后自动同步）。
 */
export function useColumnConfig(options: UseColumnConfigOptions = {}): UseColumnConfigReturn {
  const capability = declareFragment('column-config')

  const baseColumns = computed(() => toValue(options.columns) ?? [])
  const defaultState: ColumnState = {
    hidden: baseColumns.value.filter((item) => item.hidden).map((item) => item.key),
    widths: {},
    order: baseColumns.value.map((item) => item.key),
    fixed: {},
  }

  const persisted = usePersistedState<ColumnState>({
    key: options.storageKey ?? 'column-config',
    ...(options.scope !== undefined ? { scope: options.scope } : {}),
    defaultValue: defaultState,
  })

  const state = ref<ColumnState>(persisted.get() ?? defaultState)
  watch(persisted.state, (next) => {
    if (next) {
      state.value = next
    }
  })

  // 列定义变化（新增 / 删除列）时并入顺序与默认值，避免出现未登记列
  watch(
    baseColumns,
    (next) => {
      const knownKeys = new Set(next.map((item) => item.key))
      const order = [
        ...state.value.order.filter((key) => knownKeys.has(key)),
        ...next.map((item) => item.key).filter((key) => !state.value.order.includes(key)),
      ]
      state.value = { ...state.value, order }
    },
    { immediate: true },
  )

  const applyPatch = (patch: Partial<ColumnState>): void => {
    state.value = { ...state.value, ...patch }
  }

  const clampWidth = (width: number): number => {
    const min = Number(toValue(options.minWidth) ?? 60)
    const max = Number(toValue(options.maxWidth) ?? 800)
    return Math.min(Math.max(width, min), max)
  }

  const allColumns = computed<ColumnConfigItem[]>(() =>
    state.value.order
      .map((key) => baseColumns.value.find((item) => item.key === key))
      .filter((item): item is ColumnConfigItem => item !== undefined)
      .map((item) => {
        const width = state.value.widths[item.key]
        const fixed = state.value.fixed[item.key] ?? item.fixed
        return {
          ...item,
          ...(width !== undefined ? { width } : {}),
          ...(fixed !== undefined ? { fixed } : {}),
          hidden: state.value.hidden.includes(item.key),
        }
      }),
  )

  const visibleColumns = computed(() => allColumns.value.filter((item) => item.hidden !== true))

  return {
    get allColumns() {
      return allColumns.value
    },
    get visibleColumns() {
      return visibleColumns.value
    },
    get hiddenKeys() {
      return [...state.value.hidden]
    },
    get isDirty() {
      return JSON.stringify(state.value) !== JSON.stringify(persisted.get() ?? defaultState)
    },
    toggle: (key, visible) => {
      const target = baseColumns.value.find((item) => item.key === key)
      const nextVisible = visible ?? state.value.hidden.includes(key)
      if (!nextVisible && target?.lockVisible) {
        capability.log('warn', `column-config 列「${key}」不允许隐藏`)
        return
      }
      const hidden = nextVisible ? state.value.hidden.filter((item) => item !== key) : [...state.value.hidden, key]
      applyPatch({ hidden })
    },
    move: (from, to) => {
      const order = [...state.value.order]
      const [moved] = order.splice(from, 1)
      if (moved === undefined) {
        return
      }
      order.splice(to, 0, moved)
      applyPatch({ order })
    },
    setWidth: (key, width) => applyPatch({ widths: { ...state.value.widths, [key]: clampWidth(width) } }),
    freeze: (key, position) => {
      const fixed = { ...state.value.fixed }
      if (position === false) {
        delete fixed[key]
      } else {
        fixed[key] = position
      }
      applyPatch({ fixed })
    },
    reset: () => {
      const fresh: ColumnState = {
        hidden: baseColumns.value.filter((item) => item.hidden).map((item) => item.key),
        widths: {},
        order: baseColumns.value.map((item) => item.key),
        fixed: {},
      }
      state.value = fresh
      persisted.set(fresh)
    },
    save: () => persisted.set(state.value),
    restore: async () => {
      await persisted.syncFromRemote()
      state.value = persisted.get() ?? defaultState
    },
  }
}
