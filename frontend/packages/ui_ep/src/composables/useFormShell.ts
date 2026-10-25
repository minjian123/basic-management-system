/** 表单框架壳组合式：列表固定页签 + 详情多开页签（基于 `useTabNav`，不重复造页签逻辑）。 */

import { computed, ref, type Ref } from 'vue'

import { useTabNav, type TabNavItem } from './useTabNav'

/** 详情记录。 */
export interface DetailRecord {
  /** 记录标识。 */
  id: string
  /** 标题（取自记录标识字段）。 */
  title: string
  /** 是否脏数据。 */
  dirty?: boolean
}

/** 选项。 */
export interface UseFormShellOptions {
  /** 列表页签键。 */
  listKey?: string
  /** 列表页签标题。 */
  listTitle?: string
  /** 详情页签是否参与缓存。 */
  cacheDetail?: boolean
}

/** `useFormShell` 返回面。 */
export interface UseFormShellResult {
  /** 列表页签（固定不可关）。 */
  listTab: TabNavItem
  /** 详情页签（不含列表）。 */
  detailTabs: Ref<TabNavItem[]>
  /** 激活页签键（列表或详情）。 */
  activeKey: Ref<string>
  /** 详情缓存键清单。 */
  cachedDetailKeys: Ref<string[]>
  /** 打开详情（已开激活 / 不同记录新开）。 */
  openDetail: (record: DetailRecord) => string
  /** 关闭详情（脏数据经二次确认）。 */
  closeDetail: (key: string) => Promise<boolean>
  /** 标记详情脏数据。 */
  markDirty: (key: string, dirty?: boolean) => void
  /** 当前激活详情页签。 */
  activeDetail: () => TabNavItem | undefined
  /** 列表刷新信号（保存 / 删除后自增）。 */
  refreshToken: Ref<number>
  /** 请求刷新列表。 */
  requestRefresh: () => void
}

/**
 * 使用表单框架壳。
 *
 * @param options 选项。
 * @returns 列表 / 详情页签与操作方法。
 */
export function useFormShell(options: UseFormShellOptions = {}): UseFormShellResult {
  const listKey = options.listKey ?? 'list'
  const listTab: TabNavItem = { key: listKey, title: options.listTitle ?? '列表', path: listKey, closable: false }
  const nav = useTabNav()
  nav.open(listTab)

  const refreshToken = ref(0)
  const detailTabs = computed(() => nav.tabs.value.filter((item) => item.key !== listKey))
  const cachedDetailKeys = computed(() => nav.cachedKeys.value.filter((key) => key !== listKey))

  function openDetail(record: DetailRecord): string {
    const key = `detail:${record.id}`
    nav.open({ key, title: record.title, path: key, keepAlive: options.cacheDetail === true, dirty: record.dirty })
    return key
  }

  async function closeDetail(key: string): Promise<boolean> {
    return nav.close(key)
  }

  function activeDetail(): TabNavItem | undefined {
    const active = nav.activeKey.value
    return active === listKey ? undefined : detailTabs.value.find((item) => item.key === active)
  }

  return {
    listTab,
    detailTabs,
    activeKey: nav.activeKey,
    cachedDetailKeys,
    openDetail,
    closeDetail,
    markDirty: (key, dirty = true) => nav.markDirty(key, dirty),
    activeDetail,
    refreshToken,
    requestRefresh: () => {
      refreshToken.value += 1
    },
  }
}
