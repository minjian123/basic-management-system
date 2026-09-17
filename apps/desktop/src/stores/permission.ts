/**
 * 权限应用态 store：汇聚权限码集合 / 菜单树 / 权限版本与加载编排。
 *
 * **唯一来源**：权限码集合、判定（`has` / `hasAny` / `hasAll`）与菜单过滤（`filterRoutes`）
 * 全部经 `useAccess` 片段（`src/components/base/access/useAccess.ts`）提供，本 store 只做
 * 应用态汇聚与加载编排，不重复实现判定。
 * **占位先行**：未注入 `loader` 时不请求、保持空集（界面按无权限降级）。
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useFrontendBase } from '@/base/useFrontendBase'
import { useAccess, type AccessFilterableNode } from '@/components/base/access/useAccess'

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
  const base = useFrontendBase({ ns: 'store', identifier: 'permission' })

  const codes = ref<string[]>([])
  const permVersion = ref<string | number>(0)
  const menus = ref<AccessFilterableNode[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const loader = ref<PermissionLoader | undefined>(undefined)

  /** 权限片段：判定与过滤的唯一实现（集合以响应式入参传入） */
  const access = useAccess({ codes, version: permVersion })

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

  return {
    codes: computed(() => access.codes),
    menus,
    loaded,
    loading,
    isPlaceholder,
    permissions,
    /** 权限版本（指令重评依据） */
    permVersion: computed(() => access.version),
    has: (code: string) => access.has(code),
    hasAny: (target: string | string[]) => access.hasAny(target),
    hasAll: (target: string | string[]) => access.hasAll(target),
    filterRoutes: <T extends AccessFilterableNode>(nodes: T[]): T[] => access.filterRoutes(nodes),
    configureLoader,
    load,
    reset,
    setCodes,
  }
})
