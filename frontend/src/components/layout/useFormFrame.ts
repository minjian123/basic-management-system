/**
 * 表单框架状态（组件级组合式）：详情 Tab 打开 / 关闭 / 激活 / 缓存键 / 上限。
 *
 * 契约见《组件设计 · 表单框架壳》§4：列表 Tab 固定（`{title}:list`）+ 详情 Tab 多开
 * （不同记录各自新开、已开激活）；关闭激活相邻；`cacheLimit` 超出按最久未激活释放。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'

import type { TabNavItem } from '@/components/tabs'

/** 列表 Tab key 后缀 */
export const LIST_TAB_SUFFIX = ':list'

/** 详情 Tab key 前缀 */
export const DETAIL_TAB_PREFIX = 'detail:'

export interface UseFormFrameOptions {
  title?: string
  /** 详情缓存上限（超出释放最久未激活；缺省 8） */
  cacheLimit?: number
}

export interface UseFormFrameReturn {
  listKey: string
  detailTabs: Ref<TabNavItem[]>
  activeKey: Ref<string>
  /** 详情缓存键（keep-alive include） */
  cachedNames: ComputedRef<string[]>
  openDetail: (id: string | number, title?: string) => string
  closeDetail: (key: string) => void
  activate: (key: string) => void
  setDetailDirty: (key: string, dirty: boolean) => void
}

/**
 * 获取表单框架状态能力。
 *
 * 用法：`const frame = useFormFrame({ title: '用户' })`，绑定 `FormFrameTabs` 与内容区。
 */
export function useFormFrame(options: UseFormFrameOptions = {}): UseFormFrameReturn {
  const cacheLimit = options.cacheLimit ?? 8
  const listKey = `${options.title ?? 'form'}${LIST_TAB_SUFFIX}`

  const detailTabs = ref<TabNavItem[]>([])
  const activeKey = ref(listKey)
  const lastActiveAt = ref<Record<string, number>>({})

  function mark(key: string): void {
    lastActiveAt.value[key] = Date.now()
  }

  function openDetail(id: string | number, title?: string): string {
    const key = `${DETAIL_TAB_PREFIX}${String(id)}`
    if (!detailTabs.value.some((tab) => tab.key === key)) {
      detailTabs.value = [...detailTabs.value, { key, title: title ?? String(id), dirty: false }]
      if (detailTabs.value.length > cacheLimit) {
        const victim = [...detailTabs.value].sort(
          (a, b) => (lastActiveAt.value[a.key] ?? 0) - (lastActiveAt.value[b.key] ?? 0),
        )[0]
        if (victim) {
          closeDetail(victim.key)
        }
      }
    }
    activeKey.value = key
    mark(key)
    return key
  }

  function closeDetail(key: string): void {
    const index = detailTabs.value.findIndex((tab) => tab.key === key)
    if (index < 0) {
      return
    }
    detailTabs.value = detailTabs.value.filter((tab) => tab.key !== key)
    if (activeKey.value === key) {
      activeKey.value =
        detailTabs.value[index]?.key ?? detailTabs.value[index - 1]?.key ?? listKey
    }
  }

  function activate(key: string): void {
    if (key === listKey || detailTabs.value.some((tab) => tab.key === key)) {
      activeKey.value = key
      mark(key)
    }
  }

  function setDetailDirty(key: string, dirty: boolean): void {
    detailTabs.value = detailTabs.value.map((tab) => (tab.key === key ? { ...tab, dirty } : tab))
  }

  const cachedNames = computed(() => detailTabs.value.map((tab) => tab.key))

  return {
    listKey,
    detailTabs,
    activeKey,
    cachedNames,
    openDetail,
    closeDetail,
    activate,
    setDetailDirty,
  }
}
