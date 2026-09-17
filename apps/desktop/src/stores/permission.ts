/**
 * 权限应用态 store：汇聚权限码集合 / 菜单树 / 权限版本与加载编排。
 *
 * **唯一来源**：权限码集合与判定（`has` / `hasAny` / `hasAll`）经 `@bms/vue` 的 `useAccess`
 * 投影（核心 `BaseAccess`）提供，本 store 只做应用态汇聚与加载编排，不重复实现判定。
 * **占位先行**：未注入 `loader` 时不请求、保持空集（界面按无权限降级）。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useAccess, useFrontendBase } from '@bms/vue'

import { hostBaseOptions } from '@/adapters/host-base'

/** 可过滤的菜单 / 路由节点（最小形状；移动端暂无侧边菜单，保留数据形状供菜单运行时接入） */
export interface AccessFilterableNode {
  key: string
  permission?: string | string[]
  public?: boolean
  children?: AccessFilterableNode[]
}

/** 权限装配结果（菜单接口下发） */
export interface PermissionBridge {
  codes: string[]
  version?: string | number
  menus?: AccessFilterableNode[]
}

/** 菜单 / 权限加载器（缺省不注入即占位） */
export type PermissionLoader = () => Promise<PermissionBridge>

export const usePermissionStore = defineStore('permission', () => {
  /** store 级根系组合：日志与错误上报出口 */
  const base = useFrontendBase(hostBaseOptions({ ns: 'store', identifier: 'permission' }))

  const codes = ref<string[]>([])
  const permVersion = ref<string | number>(0)
  const menus = ref<AccessFilterableNode[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const loader = ref<PermissionLoader | undefined>(undefined)

  /** 权限上下文投影：判定唯一来源（集合以响应式入参传入） */
  const access = useAccess({ codes })

  /** 权限码集合（Set，O(1) 判断展示用） */
  const permissions = computed(() => new Set(access.codes))
  const isPlaceholder = computed(() => loader.value === undefined)

  /** 注入菜单 / 权限加载器（登录装配 / 菜单接口接入后调用） */
  function configureLoader(next: PermissionLoader): void {
    loader.value = next
  }

  /** 拉取菜单与权限（登录后 / 租户切换 / 权限版本变化） */
  async function load(): Promise<void> {
    if (!loader.value) {
      base.log('debug', 'permission 占位：菜单 / 权限加载器未接入，保持空集')
      return
    }
    loading.value = true
    try {
      const bridge = await loader.value()
      codes.value = [...bridge.codes]
      permVersion.value = bridge.version ?? Date.now()
      menus.value = bridge.menus ?? []
      loaded.value = true
    } catch (error) {
      // 统一上报后原样抛出：调用方（登录流程）决定提示与回退
      base.reportError(error, { store: 'permission' })
      throw error
    } finally {
      loading.value = false
    }
  }

  /** 清空（登出 / 会话失效） */
  function reset(): void {
    codes.value = []
    permVersion.value = 0
    menus.value = []
    loaded.value = false
  }

  /** 直接装配权限码（登录响应 / 测试；版本缺省递增） */
  function setCodes(next: string[], version?: string | number): void {
    codes.value = [...next]
    permVersion.value = version ?? (typeof permVersion.value === 'number' ? permVersion.value + 1 : Date.now())
  }

  /** 归一权限码为数组 */
  function toCodes(target: string | string[]): string[] {
    return Array.isArray(target) ? target : [target]
  }

  /** 菜单 / 路由过滤（无权限节点剔除；`public` 与无 `permission` 节点保留；递归过滤子级） */
  function filterRoutes<T extends AccessFilterableNode>(nodes: T[]): T[] {
    return nodes
      .filter((node) => {
        if (node.public || node.permission === undefined) {
          return true
        }
        const granted = access.codes
        return granted.length > 0 && toCodes(node.permission).some((code) => granted.includes(code))
      })
      .map((node) => {
        if (!node.children || node.children.length === 0) {
          return node
        }
        return { ...node, children: filterRoutes(node.children) }
      })
  }

  return {
    codes: computed(() => access.codes),
    menus,
    loaded,
    loading,
    isPlaceholder,
    permissions,
    /** 权限版本（指令重评依据） */
    permVersion: computed(() => permVersion.value),
    has: (code: string) => access.has(code),
    hasAny: (target: string | string[]) => access.hasAny(Array.isArray(target) ? target : [target]),
    hasAll: (target: string | string[]) => access.hasAll(Array.isArray(target) ? target : [target]),
    filterRoutes,
    configureLoader,
    load,
    reset,
    setCodes,
  }
})
