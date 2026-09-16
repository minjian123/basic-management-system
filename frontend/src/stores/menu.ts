/**
 * 菜单 store：菜单树来源（占位 loader 可注入）、展开集（持久化）、搜索过滤。
 *
 * 口径（《组件设计 · 侧边菜单》§4 / 布局设计导航节）：
 * - **占位先行**：未注入 `loader` 时 `load()` 不发请求、置空清单（对齐占位语义），
 *   真实菜单树（`GET /menus/my`，按权限过滤 + i18n）随阶段七 ~ 八由宿主注入 `configureMenuLoader`；
 * - 展开集持久化键 `bms_menu_expanded`（规范 §8.1 localStorage 前缀口径；远端偏好随后续任务）；
 * - 菜单项唯一键 = `path ?? name`（`menuKey`）。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'

import { defineStore } from 'pinia'

import {
  filterMenuTree,
  findAncestorKeys,
  menuKey,
  type MenuItem,
} from '@/components/menu/types'

/** 展开集持久化键（规范 §8.1：localStorage key 统一 bms_ 前缀） */
export const MENU_EXPANDED_KEY = 'bms_menu_expanded'

/** 菜单加载器（认证 / 菜单任务接入真实接口后注入） */
export interface MenuLoader {
  load: () => Promise<MenuItem[]>
}

/** 读取本地展开集（容错） */
function readExpanded(): string[] {
  if (typeof localStorage === 'undefined') {
    return []
  }
  try {
    const raw = localStorage.getItem(MENU_EXPANDED_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

/** 过滤（hidden）+ 排序（sort，递归） */
export function sortVisible(items: MenuItem[]): MenuItem[] {
  return [...items]
    .filter((item) => !item.hidden)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
    .map((item) => (item.children ? { ...item, children: sortVisible(item.children) } : item))
}

export const useMenuStore = defineStore('menu', () => {
  const menus = ref<MenuItem[]>([])
  const loaded = ref(false)
  const loading = ref(false)
  const keyword = ref('')
  const expandedKeys = ref<string[]>(readExpanded())

  let loader: MenuLoader | null = null

  /** 注入菜单加载器（未注入即占位：`load()` 置空清单、不发请求） */
  function configureLoader(next: MenuLoader | null): void {
    loader = next
  }

  async function load(): Promise<void> {
    loading.value = true
    try {
      menus.value = loader ? await loader.load() : []
      loaded.value = true
    } finally {
      loading.value = false
    }
  }

  const visibleMenus: ComputedRef<MenuItem[]> = computed(() => sortVisible(menus.value))

  const filteredMenus: ComputedRef<MenuItem[]> = computed(() =>
    filterMenuTree(visibleMenus.value, keyword.value),
  )

  function persistExpanded(): void {
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(MENU_EXPANDED_KEY, JSON.stringify(expandedKeys.value))
    }
  }

  function setExpanded(key: string, open: boolean): void {
    if (open) {
      if (!expandedKeys.value.includes(key)) {
        expandedKeys.value = [...expandedKeys.value, key]
        persistExpanded()
      }
      return
    }
    if (expandedKeys.value.includes(key)) {
      expandedKeys.value = expandedKeys.value.filter((item) => item !== key)
      persistExpanded()
    }
  }

  function toggleExpanded(key: string): void {
    setExpanded(key, !expandedKeys.value.includes(key))
  }

  /** 展开目标 path 的全部祖先（高亮联动） */
  function expandByPath(path: string): string[] {
    const chain = findAncestorKeys(visibleMenus.value, path) ?? []
    if (chain.length > 0) {
      expandedKeys.value = Array.from(new Set([...expandedKeys.value, ...chain]))
      persistExpanded()
    }
    return chain
  }

  function collapseAll(): void {
    expandedKeys.value = []
    persistExpanded()
  }

  function setKeyword(value: string): void {
    keyword.value = value
  }

  function reset(): void {
    menus.value = []
    loaded.value = false
    loading.value = false
    keyword.value = ''
    expandedKeys.value = []
    loader = null
  }

  return {
    menus: menus as Ref<MenuItem[]>,
    loaded: loaded as Ref<boolean>,
    loading: loading as Ref<boolean>,
    keyword: keyword as Ref<string>,
    expandedKeys: expandedKeys as Ref<string[]>,
    visibleMenus,
    filteredMenus,
    configureLoader,
    load,
    setExpanded,
    toggleExpanded,
    expandByPath,
    collapseAll,
    setKeyword,
    reset,
  }
})

export { menuKey }
