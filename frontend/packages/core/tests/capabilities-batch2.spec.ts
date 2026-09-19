/** 能力基类族批二用例（02-3）：交互与上下文类。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseClickable,
  BaseDesignToken,
  BaseDragDrop,
  BaseLocale,
  BaseModuleContext,
  BaseMounted,
  BasePersistedState,
  BaseTabs,
  validateCapabilityGraph,
} from '../src'

class DemoPersisted extends BasePersistedState {}
class DemoMounted extends BaseMounted {}
class DemoToken extends BaseDesignToken {}
class DemoClickable extends BaseClickable {}
class DemoDragDrop extends BaseDragDrop {}
class DemoTabs extends BaseTabs {}
class DemoLocale extends BaseLocale {}
class DemoAccess extends BaseAccess {}
class DemoContext extends BaseModuleContext {}

describe('批二能力键与登记表', () => {
  it('9 个能力键均登记且依赖合规', () => {
    expect(validateCapabilityGraph()).toEqual([])
    const keys = [
      'persisted-state',
      'mounted',
      'design-token',
      'clickable',
      'drag-drop',
      'tabs',
      'locale',
      'access',
      'module-context',
    ]
    for (const key of keys) {
      expect(validateCapabilityGraph({ [key]: [] })).toEqual([])
    }
  })
})

describe('BasePersistedState 偏好持久化能力', () => {
  it('本地状态 / 版本比对 / 远端占位', async () => {
    const state = new DemoPersisted()
    expect(state.identifier).toBe('persisted-state')
    state.setLocal({ theme: 'dark' })
    expect(state.local).toEqual({ theme: 'dark' })
    expect(await state.loadRemote()).toEqual({ theme: 'dark' })
    expect(state.needsRemoteRefresh(1)).toBe(true)
    state.remoteVersion = 5
    expect(state.needsRemoteRefresh(3)).toBe(false)
  })

  it('本地存储读写 / 快照回滚 / 保存与待同步 / 恢复默认', async () => {
    const store = new Map<string, string>()
    const state = new DemoPersisted()
    expect(state.persist()).toBe(false)

    state.stateKey = 'bms_preferences'
    state.storage = {
      getItem: (key: string): string | null => store.get(key) ?? null,
      setItem: (key: string, value: string): void => {
        store.set(key, value)
      },
      removeItem: (key: string): void => {
        store.delete(key)
      },
    }

    state.setLocal({ themeMode: 'dark' })
    expect(state.hasLocal).toBe(true)
    expect(state.persist()).toBe(true)
    expect(store.get('bms_preferences')).toBe('{"themeMode":"dark"}')

    state.snapshot()
    state.setLocal({ themeMode: 'light' })
    expect(state.dirty).toBe(true)
    expect(state.rollback()).toBe(true)
    expect(state.local).toEqual({ themeMode: 'dark' })
    expect(state.dirty).toBe(false)

    store.set('bms_preferences', '{"themeMode":"system"}')
    expect(state.restore()).toBe(true)
    expect(state.local).toEqual({ themeMode: 'system' })

    store.set('bms_preferences', '{oops')
    expect(state.restore()).toBe(false)

    state.setLocal({ themeMode: 'dark' })
    await expect(state.save()).resolves.toBe(false)
    expect(state.pendingSync).toBe(true)

    const sent: unknown[] = []
    state.remoteSaver = async (value): Promise<void> => {
      sent.push(value)
    }
    await expect(state.save()).resolves.toBe(true)
    expect(state.pendingSync).toBe(false)
    expect(sent).toEqual([{ themeMode: 'dark' }])

    state.remoteSaver = async (): Promise<void> => {
      throw new Error('network')
    }
    await expect(state.save()).resolves.toBe(false)
    expect(state.pendingSync).toBe(true)

    state.remoteSaver = undefined
    await state.reset({ themeMode: 'light' })
    expect(state.local).toEqual({ themeMode: 'light' })

    state.clear()
    expect(state.hasLocal).toBe(false)
    expect(state.local).toBeUndefined()
    expect(store.has('bms_preferences')).toBe(false)
  })
})

describe('BaseMounted 可挂载能力', () => {
  it('挂载 / 卸载逆序释放 / 幂等', () => {
    const mounted = new DemoMounted()
    expect(mounted.identifier).toBe('mounted')
    const order: string[] = []
    mounted.registerRelease(() => order.push('a'))
    mounted.registerRelease(() => order.push('b'))
    const events: boolean[] = []
    mounted.onMountChange((value) => events.push(value))

    mounted.mount()
    mounted.mount()
    expect(mounted.mounted).toBe(true)

    mounted.unmount()
    mounted.unmount()
    expect(mounted.mounted).toBe(false)
    expect(order).toEqual(['b', 'a'])
    expect(events).toEqual([true, false])
  })
})

describe('BaseDesignToken 设计令牌能力', () => {
  it('注入令牌 / 主题订阅', () => {
    const token = new DemoToken()
    expect(token.identifier).toBe('design-token')
    token.setTokens({ spacing: { sm: '4px' } })
    expect(token.tokens.spacing).toEqual({ sm: '4px' })
    const themes: string[] = []
    token.onThemeChange((theme) => themes.push(theme))
    token.setTheme('dark')
    token.setTheme('dark')
    expect(token.theme).toBe('dark')
    expect(themes).toEqual(['dark'])
  })
})

describe('BaseClickable 可点击能力', () => {
  it('禁用 / 防抖 / 埋点', () => {
    const clickable = new DemoClickable()
    expect(clickable.identifier).toBe('clickable')
    clickable.debounceMs = 100
    expect(clickable.tryTrigger('save', 1000)).toBe(true)
    expect(clickable.tryTrigger('save', 1050)).toBe(false)
    expect(clickable.tryTrigger('save', 1200)).toBe(true)
    expect(clickable.tracked).toEqual(['save', 'save'])

    clickable.setProps({ disabled: true })
    expect(clickable.tryTrigger('save', 2000)).toBe(false)
  })
})

describe('BaseDragDrop 拖拽能力', () => {
  it('拖拽阶段与监听', () => {
    const drag = new DemoDragDrop()
    expect(drag.identifier).toBe('drag-drop')
    const events: string[] = []
    drag.onDrag((payload) => events.push(`${payload.phase}:${payload.target ?? ''}`))
    drag.emitDrag({ phase: 'start', source: 'a' })
    expect(drag.dragging).toBe(true)
    drag.emitDrag({ phase: 'drop', source: 'a', target: 'b', crossZone: true })
    expect(drag.dragging).toBe(false)
    expect(events).toEqual(['start:', 'drop:b'])
  })
})

describe('BaseTabs 页签能力', () => {
  it('打开 / 关闭激活相邻 / 固定 / 缓存键清单', () => {
    const tabs = new DemoTabs()
    tabs.open({ key: 'a', title: 'A' })
    tabs.open({ key: 'b', title: 'B' })
    expect(tabs.activeKey).toBe('b')
    tabs.pin('a')
    expect(tabs.tabs[0]?.pinned).toBe(true)
    tabs.close('b')
    expect(tabs.activeKey).toBe('a')
    expect(tabs.cacheKeys).toEqual(['a'])
  })
})

describe('BaseLocale 语言上下文能力', () => {
  it('语言 / 时区 / 格式上下文', () => {
    const locale = new DemoLocale()
    expect(locale.formatContext).toEqual({ locale: 'zh-CN', timezone: 'Asia/Shanghai' })
    locale.setLocale('en-US')
    locale.setTimezone('UTC')
    expect(locale.formatContext).toEqual({ locale: 'en-US', timezone: 'UTC' })
  })
})

describe('BaseAccess 权限上下文能力', () => {
  it('权限码判定', () => {
    const access = new DemoAccess()
    access.setCodes(['user:read', 'user:write'])
    expect(access.codes).toEqual(['user:read', 'user:write'])
    expect(access.has('user:read')).toBe(true)
    expect(access.hasAny(['x', 'user:write'])).toBe(true)
    expect(access.hasAll(['user:read', 'user:write'])).toBe(true)
    expect(access.hasAll(['user:read', 'user:delete'])).toBe(false)
  })
})

describe('BaseModuleContext 上下文能力', () => {
  it('注入只读上下文', () => {
    const context = new DemoContext()
    context.inject({ router: { name: 'r' }, tenant: 't1' })
    expect(context.has('router')).toBe(true)
    expect(context.has('store')).toBe(false)
    expect(context.get<{ name: string }>('router')?.name).toBe('r')
    expect(Object.isFrozen(context.snapshot)).toBe(true)
  })
})
