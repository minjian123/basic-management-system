/**
 * 权限上下文片段（`access`）：权限码集合、路由 / 菜单过滤与按钮显隐。
 *
 * 契约见《组件设计 · 权限上下文片段》：`codes` / `version` / `has` / `hasAny` / `hasAll` /
 * `filterRoutes` / `refresh`（动作权限与动态菜单共用）。
 * **权威边界**：字段级权限归字段权限片段（`field-perm`），动作权限指令归 `02_06` 权限指令；
 * 本片段只提供**权限码集合与过滤能力**，不做指令与字段判定。
 * **占位先行**：未注入 `loader`（权限接口未接入）时集合为空集、`version` 为 `0`，
 * `has()` 返回 `false`（界面按无权限降级），不请求、不报错。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 权限码集合加载器（后端权限上下文接入后注入） */
export type AccessLoader = () => Promise<{ codes: string[]; version?: string | number }>

/** 可过滤的菜单 / 路由节点（最小形状） */
export interface AccessFilterableNode {
  key: string
  /** 所需权限码（任一命中即可见；缺省视为公开） */
  permission?: string | string[]
  public?: boolean
  children?: AccessFilterableNode[]
}

/** 权限上下文片段参数 */
export interface UseAccessOptions {
  /** 初始权限码（登录响应或后端下发的权限上下文） */
  codes?: MaybeRefOrGetter<string[]>
  /** 权限版本（后端下发；变化即刷新） */
  version?: MaybeRefOrGetter<string | number>
  /** 加载器（缺省即占位：不请求） */
  loader?: AccessLoader
  /** 变更通知（供指令 / 菜单重算） */
  onChange?: (codes: string[]) => void
}

/** 权限上下文片段返回值 */
export interface UseAccessReturn {
  readonly codes: string[]
  readonly version: string | number
  readonly isPlaceholder: boolean
  /** 是否已从后端加载过权限码（占位态恒为 false） */
  readonly loaded: boolean
  readonly size: number
  has: (code: string) => boolean
  hasAny: (codes: string | string[]) => boolean
  hasAll: (codes: string | string[]) => boolean
  /** 菜单 / 路由过滤（无权限节点剔除；`public` 与无 `permission` 节点保留） */
  filterRoutes: <T extends AccessFilterableNode>(nodes: T[]) => T[]
  refresh: () => Promise<void>
}

/** 归一为数组 */
function toArray(codes: string | string[]): string[] {
  return Array.isArray(codes) ? codes : [codes]
}

/**
 * 获取权限上下文能力。
 *
 * 用法：`const access = useAccess({ codes, loader })`；按钮显隐用 `access.has('sys:user:create')`，
 * 菜单用 `access.filterRoutes(menuTree)`。
 */
export function useAccess(options: UseAccessOptions = {}): UseAccessReturn {
  const capability = declareFragment('access')

  const innerCodes = ref<string[]>(toValue(options.codes) ?? [])
  const innerVersion = ref<string | number>(toValue(options.version) ?? 0)
  const loaded = ref(false)
  const isPlaceholder = computed(() => options.loader === undefined)

  const codes = computed(() => toValue(options.codes) ?? innerCodes.value)
  const version = computed(() => toValue(options.version) ?? innerVersion.value)

  const has = (code: string): boolean => codes.value.includes(code)

  const filterRoutes = <T extends AccessFilterableNode>(nodes: T[]): T[] =>
    nodes
      .filter((node) => {
        if (node.public || node.permission === undefined) {
          return true
        }
        return codes.value.length > 0 && toArray(node.permission).some((code) => codes.value.includes(code))
      })
      .map((node) => {
        if (!node.children || node.children.length === 0) {
          return node
        }
        return { ...node, children: filterRoutes(node.children) }
      })

  return {
    get codes() {
      return [...codes.value]
    },
    get version() {
      return version.value
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get loaded() {
      return loaded.value
    },
    get size() {
      return codes.value.length
    },
    has,
    hasAny: (target) => toArray(target).some((code) => has(code)),
    hasAll: (target) => toArray(target).every((code) => has(code)),
    filterRoutes,
    refresh: async () => {
      if (!options.loader) {
        capability.log('debug', 'access 占位：权限码加载器未接入，保持空集')
        return
      }
      try {
        const result = await options.loader()
        innerCodes.value = result.codes
        innerVersion.value = result.version ?? Date.now()
        loaded.value = true
        options.onChange?.(result.codes)
      } catch (error) {
        capability.reportError(error, { scope: 'access.refresh' })
      }
    },
  }
}
