/**
 * 页签状态片段（`tabs`）：多标签导航、表单框架双层 Tab、内容页签共用的开闭与缓存口径。
 *
 * 契约见《组件设计 · 页签状态片段》：`open` / `close` / `closeOthers` / `closeAll` / `pin` /
 * `unpin` / `activate` / `find` / `has` + 缓存键清单（`cachedNames`，供 `keep-alive` 消费）。
 * 与动态路由 / 权限上下文的协作（无权限路由不建签）由调用方判定后调用 `open`，本片段不做权限判定。
 */

import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 页签项 */
export interface TabItem {
  /** 页签标识（通常为路由名） */
  key: string
  title: string
  /** 路由名 / 组件名（`keep-alive` 缓存匹配用；缺省取 `key`） */
  name?: string
  /** 是否可关闭（默认 true） */
  closable?: boolean
  /** 固定页签（不可关闭、排在最前） */
  pinned?: boolean
}

/** 页签片段参数 */
export interface UseTabsOptions {
  /** 受控页签清单（传入即受控：内部只回调，不自行改值） */
  tabs?: MaybeRefOrGetter<TabItem[]>
  /** 受控激活项 */
  activeKey?: MaybeRefOrGetter<string>
  /** 是否生成缓存键（默认 true） */
  cacheable?: MaybeRefOrGetter<boolean>
  /** 变更通知（受控模式下由宿主写回） */
  onChange?: (payload: { tabs: TabItem[]; activeKey: string }) => void
}

/** 页签片段返回值 */
export interface UseTabsReturn {
  readonly tabs: TabItem[]
  readonly activeKey: string
  /** keep-alive 缓存键清单（固定页签优先，其后按打开顺序） */
  readonly cachedNames: string[]
  open: (tab: TabItem) => void
  close: (key: string) => void
  closeOthers: (key: string) => void
  closeAll: () => void
  pin: (key: string) => void
  unpin: (key: string) => void
  activate: (key: string) => void
  find: (key: string) => TabItem | undefined
  has: (key: string) => boolean
}

/** 排序：固定页签在前，其余保持打开顺序 */
function sortTabs(items: TabItem[]): TabItem[] {
  const pinned = items.filter((item) => item.pinned)
  const rest = items.filter((item) => !item.pinned)
  return [...pinned, ...rest]
}

/**
 * 获取页签状态能力。
 *
 * 用法：`const tabs = useTabs({ tabs, activeKey, onChange })`；缓存键清单直接喂给 `keep-alive` 的 `include`。
 */
export function useTabs(options: UseTabsOptions = {}): UseTabsReturn {
  declareFragment('tabs')

  const isControlled = computed(() => options.tabs !== undefined)
  const innerTabs = ref<TabItem[]>([...(toValue(options.tabs) ?? [])])
  const innerActive = ref<string>(String(toValue(options.activeKey) ?? ''))

  watch(
    () => toValue(options.tabs),
    (next) => {
      if (next !== undefined) {
        innerTabs.value = [...next]
      }
    },
    { immediate: true },
  )
  watch(
    () => toValue(options.activeKey),
    (next) => {
      if (next !== undefined) {
        innerActive.value = String(next)
      }
    },
    { immediate: true },
  )

  const emitChange = (): void => {
    options.onChange?.({ tabs: innerTabs.value, activeKey: innerActive.value })
  }

  const tabs = computed(() => (isControlled.value ? [...(toValue(options.tabs) ?? [])] : innerTabs.value))
  const activeKey = computed(() => (isControlled.value ? String(toValue(options.activeKey) ?? '') : innerActive.value))

  const update = (next: TabItem[], nextActive?: string): void => {
    if (!isControlled.value) {
      innerTabs.value = sortTabs(next)
      if (nextActive !== undefined) {
        innerActive.value = nextActive
      }
    }
    emitChange()
  }

  return {
    get tabs() {
      return tabs.value
    },
    get activeKey() {
      return activeKey.value
    },
    get cachedNames() {
      if (!(toValue(options.cacheable) ?? true)) {
        return []
      }
      return tabs.value.map((item) => item.name ?? item.key)
    },
    open: (tab) => {
      const exists = tabs.value.some((item) => item.key === tab.key)
      const next = exists
        ? tabs.value.map((item) => (item.key === tab.key ? { ...item, ...tab } : item))
        : [...tabs.value, tab]
      update(next, tab.key)
    },
    close: (key) => {
      const target = tabs.value.find((item) => item.key === key)
      if (!target || target.pinned || target.closable === false) {
        return
      }
      const next = tabs.value.filter((item) => item.key !== key)
      const nextActive = activeKey.value === key ? (next[next.length - 1]?.key ?? '') : activeKey.value
      update(next, nextActive)
    },
    closeOthers: (key) => {
      const next = tabs.value.filter((item) => item.key === key || item.pinned)
      update(next, key)
    },
    closeAll: () => {
      const next = tabs.value.filter((item) => item.pinned)
      update(next, next[0]?.key ?? '')
    },
    pin: (key) => update(tabs.value.map((item) => (item.key === key ? { ...item, pinned: true } : item))),
    unpin: (key) => update(tabs.value.map((item) => (item.key === key ? { ...item, pinned: false } : item))),
    activate: (key) => {
      if (!tabs.value.some((item) => item.key === key)) {
        return
      }
      update(tabs.value, key)
    },
    find: (key) => tabs.value.find((item) => item.key === key),
    has: (key) => tabs.value.some((item) => item.key === key),
  }
}
