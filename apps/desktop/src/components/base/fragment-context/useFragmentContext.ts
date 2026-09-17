/**
 * 片段上下文片段（`fragment-context`）：宿主注入 router / store / i18n / 用户 / 租户的统一只读入口。
 *
 * 契约见《组件设计 · 片段上下文片段》：`get()` / `has()` + **只读约束**（片段不得改写宿主上下文）。
 * 用途：让片段与具体工程解耦——片段从上下文取宿主能力（路由跳转、状态读取、取词、当前用户 / 租户），
 * 而不是直接 import 宿主模块；未注入时 `has()` 为 `false`，片段按缺省行为降级。
 */

import { computed, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 当前用户上下文（片段只读使用） */
export interface ContextUser {
  id: string | number
  name: string
  deptId?: string | number
  [key: string]: unknown
}

/** 当前租户上下文 */
export interface ContextTenant {
  id: string | number
  name: string
  [key: string]: unknown
}

/** 片段上下文（全部只读；`router` / `store` / `i18n` 为宿主实例的窄接口） */
export interface FragmentContext {
  router?: { push?: (target: unknown) => unknown; currentRoute?: unknown }
  store?: unknown
  i18n?: { t?: (key: string, params?: Record<string, unknown>) => string }
  user?: ContextUser
  tenant?: ContextTenant
}

/** 上下文键 */
export type FragmentContextKey = keyof FragmentContext

/** 片段上下文片段参数 */
export interface UseFragmentContextOptions {
  /** 宿主注入的上下文（缺省即空上下文：`has()` 全为 false） */
  host?: MaybeRefOrGetter<FragmentContext>
  /** 严格模式：`require()` 取不到时抛错（默认返回 `undefined`） */
  strict?: boolean
}

/** 片段上下文片段返回值 */
export interface UseFragmentContextReturn {
  /** 只读上下文快照（冻结） */
  readonly context: FragmentContext
  readonly isPlaceholder: boolean
  get: <K extends FragmentContextKey>(key: K) => FragmentContext[K]
  has: (key: FragmentContextKey) => boolean
  /** 取必需上下文：严格模式缺失即抛错，否则等同 `get` */
  require: <K extends FragmentContextKey>(key: K) => FragmentContext[K]
  update: (patch: FragmentContext) => void
}

/**
 * 获取片段上下文能力。
 *
 * 用法：`const ctx = useFragmentContext({ host: { router, store, i18n, user, tenant } })`；
 * 片段内一律经 `ctx.get('router')` 取用，保证只读与可替换。
 */
export function useFragmentContext(options: UseFragmentContextOptions = {}): UseFragmentContextReturn {
  const capability = declareFragment('fragment-context')

  const host = computed(() => toValue(options.host) ?? {})
  const context = shallowRef<FragmentContext>(Object.freeze({ ...host.value }))

  // 宿主更新上下文（如登录后注入用户 / 租户）时以新快照替换
  watch(host, (next) => {
    context.value = Object.freeze({ ...next })
  })

  const get = <K extends FragmentContextKey>(key: K): FragmentContext[K] => context.value[key] as FragmentContext[K]

  return {
    get context() {
      return context.value
    },
    get isPlaceholder() {
      return Object.keys(context.value).length === 0
    },
    get,
    has: (key) => context.value[key] !== undefined,
    require: <K extends FragmentContextKey>(key: K): FragmentContext[K] => {
      const value = get(key)
      if (value === undefined && options.strict) {
        throw new Error(`[fragment-context] 缺少必需上下文：${key}`)
      }
      if (value === undefined) {
        capability.log('debug', `fragment-context 缺省上下文：${key}（按降级行为继续）`)
      }
      return value
    },
    update: (patch) => {
      // 只读约束：以新对象替换（冻结），不原地改写
      context.value = Object.freeze({ ...context.value, ...patch })
    },
  }
}
