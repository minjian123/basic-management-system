/**
 * 查询方案片段（`query-scheme`）：查询条件模型与方案的保存 / 应用。
 *
 * 契约见《组件设计 · 查询方案片段》：`conditions` / `schemes` / `saveAs` / `apply` / `remove` /
 * `setDefault` / `clear` / `toParams`（后端 `sys_query_scheme`；查询筛选区消费）。
 * **组合依赖**：`persisted-state`（方案本地即时 + 远端同步；远端接口未接入时自动占位）。
 */

import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'
import { usePersistedState } from '../persisted-state/usePersistedState'

/** 查询条件（筛选字段 → 值；空值由 `toParams` 剔除） */
export type QueryCondition = Record<string, unknown>

/** 查询方案 */
export interface QueryScheme {
  /** 方案标识 */
  id: string
  /** 方案名（用户命名） */
  name: string
  /** 是否默认方案（进入模块自动应用） */
  isDefault?: boolean
  conditions: QueryCondition
}

/** 查询方案片段参数 */
export interface UseQuerySchemeOptions {
  /** 模块标识（方案按模块隔离；缺省 `default`） */
  moduleKey?: MaybeRefOrGetter<string>
  /** 默认（初始）条件 */
  defaultScheme?: MaybeRefOrGetter<QueryCondition>
  /** 作用域（多租户区分） */
  scope?: MaybeRefOrGetter<string | undefined>
  /** 变更通知（应用方案 / 条件变化时触发，宿主据此触发查询） */
  onApply?: (payload: { conditions: QueryCondition; schemeId?: string }) => void
}

/** 查询方案片段返回值 */
export interface UseQuerySchemeReturn {
  readonly conditions: QueryCondition
  readonly schemes: QueryScheme[]
  readonly activeSchemeId: string | undefined
  readonly defaultScheme: QueryScheme | undefined
  /** 设置条件（不落方案） */
  setConditions: (patch: QueryCondition) => void
  /** 另存为新方案 */
  saveAs: (name: string) => QueryScheme
  /** 应用方案（覆盖条件 + 触发 `onApply`） */
  apply: (schemeId: string) => QueryCondition
  /** 删除方案（默认方案同删；当前应用方案被删时回落空条件） */
  remove: (schemeId: string) => void
  setDefault: (schemeId: string) => void
  /** 清空条件（应用默认方案；无默认则清空） */
  clear: () => QueryCondition
  /** 转为接口参数（剔除空值） */
  toParams: () => QueryCondition
}

/** 剔除空值（`undefined` / `null` / 空串 / 空数组） */
function pruneEmpty(conditions: QueryCondition): QueryCondition {
  const result: QueryCondition = {}
  for (const [key, value] of Object.entries(conditions)) {
    if (value === undefined || value === null || value === '') {
      continue
    }
    if (Array.isArray(value) && value.length === 0) {
      continue
    }
    result[key] = value
  }
  return result
}

/** 持久化状态 */
interface SchemeState {
  schemes: QueryScheme[]
  conditions: QueryCondition
  activeSchemeId?: string
}

/**
 * 获取查询方案能力。
 *
 * 用法：`const scheme = useQueryScheme({ moduleKey: 'sys-user', defaultScheme, onApply })`；
 * 查询按钮调 `scheme.toParams()`，条件变化后 `scheme.saveAs('我的常用')`。
 */
export function useQueryScheme(options: UseQuerySchemeOptions = {}): UseQuerySchemeReturn {
  const capability = declareFragment('query-scheme')

  const moduleKey = computed(() => String(toValue(options.moduleKey) ?? 'default'))
  const initialConditions = computed<QueryCondition>(() => ({ ...(toValue(options.defaultScheme) ?? {}) }))

  const persisted = usePersistedState<SchemeState>({
    key: `query-scheme:${moduleKey.value}`,
    ...(options.scope !== undefined ? { scope: options.scope } : {}),
    defaultValue: { schemes: [], conditions: initialConditions.value },
  })

  const state = ref<SchemeState>(persisted.get() ?? { schemes: [], conditions: initialConditions.value })
  watch(persisted.state, (next) => {
    if (next) {
      state.value = next
    }
  })

  let seed = state.value.schemes.length

  const commit = (patch: Partial<SchemeState>, notify = false): void => {
    state.value = { ...state.value, ...patch }
    persisted.set(state.value)
    if (notify) {
      options.onApply?.({
        conditions: state.value.conditions,
        ...(state.value.activeSchemeId !== undefined ? { schemeId: state.value.activeSchemeId } : {}),
      })
    }
  }

  return {
    get conditions() {
      return { ...state.value.conditions }
    },
    get schemes() {
      return [...state.value.schemes]
    },
    get activeSchemeId() {
      return state.value.activeSchemeId
    },
    get defaultScheme() {
      return state.value.schemes.find((item) => item.isDefault)
    },
    setConditions: (patch) => {
      commit({ conditions: { ...state.value.conditions, ...patch } })
    },
    saveAs: (name) => {
      seed += 1
      const scheme: QueryScheme = {
        id: `${moduleKey.value}-${seed}`,
        name,
        conditions: { ...state.value.conditions },
      }
      commit({ schemes: [...state.value.schemes, scheme], activeSchemeId: scheme.id })
      capability.log('debug', `query-scheme 已保存方案：${name}`)
      return scheme
    },
    apply: (schemeId) => {
      const scheme = state.value.schemes.find((item) => item.id === schemeId)
      if (!scheme) {
        capability.log('warn', `query-scheme 未找到方案：${schemeId}`)
        return { ...state.value.conditions }
      }
      commit({ conditions: { ...scheme.conditions }, activeSchemeId: scheme.id }, true)
      return { ...scheme.conditions }
    },
    remove: (schemeId) => {
      const schemes = state.value.schemes.filter((item) => item.id !== schemeId)
      const patch: Partial<SchemeState> = { schemes }
      if (state.value.activeSchemeId === schemeId) {
        patch.activeSchemeId = undefined
      }
      commit(patch)
    },
    setDefault: (schemeId) => {
      commit({
        schemes: state.value.schemes.map((item) => ({ ...item, isDefault: item.id === schemeId })),
      })
    },
    clear: () => {
      const fallback = state.value.schemes.find((item) => item.isDefault)
      const conditions = fallback ? { ...fallback.conditions } : {}
      commit({ conditions, ...(fallback ? { activeSchemeId: fallback.id } : {}) }, true)
      return conditions
    },
    toParams: () => pruneEmpty(state.value.conditions),
  }
}
