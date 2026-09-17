/**
 * 页签状态投影（Vue 绑定插件）：核心 `BaseTabs` ↔ Vue。
 *
 * 语义与旧片段同构：受控（传入 `tabs` / `activeKey`）时只经 `onChange` 回写、不自行改；
 * 非受控时内部维护（核心状态）并经 `onChange` 通知；`cachedNames` 供 keep-alive 消费。
 */

import { getCurrentScope, onScopeDispose, shallowRef, toValue, type MaybeRefOrGetter } from 'vue'

import { createCapability, type BaseTabs, type TabEntry } from '@bms/core'

export type TabItem = TabEntry

export interface UseTabsOptions {
  /** 受控页签列表（传入即受控） */
  tabs?: MaybeRefOrGetter<readonly TabEntry[] | null>
  /** 受控激活键（传入即受控） */
  activeKey?: MaybeRefOrGetter<string | null>
  maxOpen?: number
  /** 变更通知（受控回写 / 非受控通知） */
  onChange?: (payload: { tabs: readonly TabEntry[]; activeKey: string }) => void
}

export interface UseTabsReturn {
  readonly tabs: readonly TabEntry[]
  readonly activeKey: string
  readonly cachedNames: string[]
  open: (tab: TabEntry) => void
  close: (key: string) => void
  find: (key: string) => TabEntry | undefined
  has: (key: string) => boolean
  activate: (key: string) => void
}

export function useTabs(options: UseTabsOptions = {}): UseTabsReturn {
  const instance = createCapability<BaseTabs>('tabs', { maxOpen: options.maxOpen })
  const innerTabs = shallowRef<readonly TabEntry[]>(instance.tabs.get())
  const innerActive = shallowRef(instance.activeKey.get())

  const unsubscribeTabs = instance.tabs.subscribe((next) => {
    innerTabs.value = next
  })
  const unsubscribeActive = instance.activeKey.subscribe((next) => {
    innerActive.value = next
  })

  if (getCurrentScope()) {
    onScopeDispose(() => {
      unsubscribeTabs()
      unsubscribeActive()
      instance.dispose()
    })
  }

  const controlledTabs = (): boolean => options.tabs !== undefined
  const controlledActive = (): boolean => options.activeKey !== undefined

  const list = (): readonly TabEntry[] => {
    if (controlledTabs()) {
      return toValue(options.tabs as MaybeRefOrGetter<readonly TabEntry[] | null>) ?? []
    }
    return innerTabs.value
  }

  const active = (): string => {
    if (controlledActive()) {
      return toValue(options.activeKey as MaybeRefOrGetter<string | null>) ?? ''
    }
    return innerActive.value
  }

  /** 固定签排前（稳定排序；与核心 `BaseTabs` 同口径） */
  const sortTabs = (list: readonly TabEntry[]): readonly TabEntry[] =>
    [...list].sort((a, b) => Number(Boolean(b.pinned)) - Number(Boolean(a.pinned)))

  /** 计算下一态并通知（受控时不写内部） */
  const update = (next: readonly TabEntry[], nextActive: string): void => {
    if (!controlledTabs()) {
      instance.tabs.set(next)
    }
    if (!controlledActive()) {
      instance.activeKey.set(nextActive)
    }
    options.onChange?.({ tabs: next, activeKey: nextActive })
  }

  const close = (key: string): void => {
    const current = [...list()]
    const target = current.find((item) => item.key === key)
    if (!target || target.pinned || target.closable === false) {
      return
    }
    const next = current.filter((item) => item.key !== key)
    const nextActive = active() === key ? (next[next.length - 1]?.key ?? '') : active()
    update(next, nextActive)
  }

  return {
    get tabs() {
      return list()
    },
    get activeKey() {
      return active()
    },
    get cachedNames() {
      return list().map((item) => item.name ?? item.key)
    },
    open: (tab: TabEntry) => {
      const current = [...list()]
      const index = current.findIndex((item) => item.key === tab.key)
      if (index >= 0) {
        current[index] = { ...current[index], ...tab }
        update(sortTabs(current), tab.key)
        return
      }
      if (current.length >= (options.maxOpen ?? 12)) {
        const victim = current.findIndex((item) => !item.pinned && item.closable !== false)
        if (victim >= 0) {
          current.splice(victim, 1)
        }
      }
      update(sortTabs([...current, tab]), tab.key)
    },
    close,
    find: (key: string) => list().find((item) => item.key === key),
    has: (key: string) => list().some((item) => item.key === key),
    activate: (key: string) => {
      if (list().some((item) => item.key === key)) {
        update([...list()], key)
      }
    },
  }
}
