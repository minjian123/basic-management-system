/** Tab 核心（模块级单例）：增删激活、白名单过滤、localStorage 持久化；UI/路由联动随布局阶段接入。 */

import { ref } from 'vue'

export interface TabItem {
  path: string
  title: string
}

export const TABS_STORAGE_KEY = 'bms_open_tabs'

/** 允许建 Tab 的路径白名单（布局阶段按菜单配置扩展）。 */
export const ALLOWED_PATHS = ['/', '/home']

const tabs = ref<TabItem[]>([])
const active = ref('')

function persist(): void {
  localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify(tabs.value))
}

export function useTabs(options: { navigate?: (path: string) => void } = {}) {
  function activate(path: string): void {
    active.value = path
    options.navigate?.(path)
  }

  function openTab(path: string, title: string): void {
    if (!ALLOWED_PATHS.includes(path)) {
      return
    }
    if (!tabs.value.some((tab) => tab.path === path)) {
      tabs.value.push({ path, title })
      persist()
    }
    activate(path)
  }

  function closeTab(path: string): void {
    tabs.value = tabs.value.filter((tab) => tab.path !== path)
    persist()
    if (active.value === path) {
      const last = tabs.value[tabs.value.length - 1]
      if (last) {
        activate(last.path)
      } else {
        active.value = ''
      }
    }
  }

  function restore(): void {
    const raw = localStorage.getItem(TABS_STORAGE_KEY)
    if (!raw) {
      return
    }
    try {
      tabs.value = JSON.parse(raw) as TabItem[]
    } catch {
      tabs.value = []
    }
  }

  return { tabs, active, openTab, closeTab, activate, restore }
}
