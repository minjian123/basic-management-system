/**
 * 菜单展开状态持久化（`localStorage` 键 `bms_menu_expanded`）。
 *
 * 与 `MainLayout` / `SideMenu` 的 `default-openeds`（初始展开）与 `open` / `close` 事件配套：
 * 宿主把持久化集合传给 `default-openeds`，并在展开 / 收起时回写集合，实现刷新后恢复展开态。
 */

import { ref, type Ref } from 'vue'

/** 持久化键。 */
export const MENU_EXPANDED_STORAGE_KEY = 'bms_menu_expanded'

/** `useMenuExpanded` 返回面。 */
export interface UseMenuExpandedResult {
  /** 已展开的子菜单路径集合。 */
  expandedKeys: Ref<string[]>
  /**
   * 记录展开 / 收起。
   *
   * @param key 子菜单路径。
   * @param open 是否展开。
   */
  toggleOpen: (key: string, open: boolean) => void
  /** 清空展开态。 */
  reset: () => void
}

/**
 * 读取持久化的展开集合（不可用 / 脏值按空集合处理）。
 *
 * @returns 已展开路径清单。
 */
function readExpanded(): string[] {
  try {
    const raw = localStorage.getItem(MENU_EXPANDED_STORAGE_KEY)
    if (raw === null) {
      return []
    }
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter((item): item is string => typeof item === 'string')
  } catch {
    return []
  }
}

/**
 * 写入展开集合（失败不阻断交互）。
 *
 * @param keys 已展开路径清单。
 */
function writeExpanded(keys: readonly string[]): void {
  try {
    localStorage.setItem(MENU_EXPANDED_STORAGE_KEY, JSON.stringify(keys))
  } catch {
    // 存储不可用（隐私模式 / 配额）时仅保留内存态
  }
}

/**
 * 使用菜单展开状态持久化。
 *
 * @returns 展开集合与读写操作。
 */
export function useMenuExpanded(): UseMenuExpandedResult {
  const expandedKeys = ref<string[]>(readExpanded())

  function toggleOpen(key: string, open: boolean): void {
    const next = open
      ? [...new Set([...expandedKeys.value, key])]
      : expandedKeys.value.filter((item) => item !== key)
    expandedKeys.value = next
    writeExpanded(next)
  }

  function reset(): void {
    expandedKeys.value = []
    writeExpanded([])
  }

  return { expandedKeys, toggleOpen, reset }
}
