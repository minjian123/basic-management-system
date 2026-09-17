/**
 * 组件契约用例工厂（框架无关）：容器件与权限按钮的跨实现不变量。
 *
 * 插件以 mount adapter（`ComponentContractKit`，实现见 `@bms/vue/testing`）传入，
 * `ui-ep` / `ui-vant` 跑同一套断言；细粒度行为仍保留在各插件自有 spec。
 *
 * 断言面：类名钩子与插槽渲染、关键 props 语义（尺寸解析 / 比例变量 / 撑高）、
 * 关键事件（滚动度量 / 触底 / 折叠 / 重试）、权限按钮显隐与点击拦截。
 */

import { describe, expect, it } from 'vitest'

import type { PermissionChecker } from '../src/contracts/permission'

export interface ComponentMountOptions {
  props?: Record<string, unknown>
  slots?: Record<string, unknown>
}

export interface ScrollMetricsStub {
  scrollHeight?: number
  clientHeight?: number
  scrollTop?: number
}

export interface ComponentViewHandle {
  html(): string
  text(): string
  has(selector: string): boolean
  count(selector: string): number
  attr(selector: string, name: string): string | undefined
  trigger(selector: string, event: string): Promise<void>
  /** 输入类组件赋值（`@vue/test-utils` setValue 适配）；输入控件契约需要，未实现即报错 */
  setValue?(selector: string, value: string): Promise<void>
  /** 注入滚动度量（jsdom 无布局）并等一次渲染 */
  stubMetrics(selector: string, metrics: ScrollMetricsStub): Promise<void>
  /** 等一帧 + 渲染（rAF 合并类组件如 VirtualList 用） */
  flushRender(): Promise<void>
  emitted(event: string): unknown[][]
  exposed<T = Record<string, unknown>>(): T
  unmount(): void
}

export interface ComponentContractKit {
  /** 按插件出口名挂载组件（`ScrollContainer` / `VirtualList` / `PermButton` …） */
  mount(name: string, options?: ComponentMountOptions): ComponentViewHandle
  configurePermissionChecker(next: PermissionChecker | undefined): void
}

const SCROLL_SLUGS = [
  'ScrollContainer',
  'SectionContainer',
  'LoadingContainer',
  'LazyContainer',
  'AutoHeight',
  'AspectRatio',
  'VirtualList',
  'FullscreenContainer',
] as const

function probeSlot(name: string): string {
  return `<div class="probe-${name}">${name}</div>`
}

export function describeContainerComponentsContract(kit: ComponentContractKit): void {
  describe('容器件契约（同一套断言）', () => {
    it('八件共同不变量：类名钩子 + 默认插槽渲染', () => {
      for (const name of SCROLL_SLUGS) {
        const view = kit.mount(name, {
          props: minimalProps(name),
          slots: { default: probeSlot('default') },
        })
        expect(view.has(`.${slugClass(name)}`), `${name} 根类名钩子`).toBe(true)
        expect(view.has('.probe-default'), `${name} 默认插槽`).toBe(true)
        view.unmount()
      }
    })

    it('ScrollContainer：三区插槽与尺寸解析', () => {
      const view = kit.mount('ScrollContainer', {
        props: { height: 240, maxHeight: '50vh' },
        slots: {
          header: probeSlot('header'),
          default: probeSlot('default'),
          footer: probeSlot('footer'),
        },
      })
      expect(view.has('.bms-scroll-container-header .probe-header')).toBe(true)
      expect(view.has('.bms-scroll-container-body .probe-default')).toBe(true)
      expect(view.has('.bms-scroll-container-footer .probe-footer')).toBe(true)
      const style = view.attr('.bms-scroll-container-body', 'style') ?? ''
      expect(style).toContain('height: 240px')
      expect(style).toContain('max-height: 50vh')
      view.unmount()
    })

    it('ScrollContainer：滚动度量与触底事件', async () => {
      const view = kit.mount('ScrollContainer', {
        props: { throttle: 0, threshold: 10 },
        slots: { default: '<div style="height: 1000px" />' },
      })
      await view.stubMetrics('.bms-scroll-container-body', {
        scrollHeight: 1000,
        clientHeight: 200,
        scrollTop: 810,
      })
      await view.trigger('.bms-scroll-container-body', 'scroll')
      expect(view.emitted('scroll')[0]?.[0]).toMatchObject({
        scrollTop: 810,
        scrollHeight: 1000,
        clientHeight: 200,
      })
      expect(view.emitted('reach-bottom')).toHaveLength(1)
      view.unmount()
    })

    it('AspectRatio：比例变量与内容插槽', () => {
      const view = kit.mount('AspectRatio', {
        props: { ratio: 2 },
        slots: { default: probeSlot('default') },
      })
      const style = view.attr('.bms-aspect-ratio', 'style') ?? ''
      expect(style).toContain('--bms-aspect-ratio-number')
      expect(view.has('.bms-aspect-ratio-content .probe-default')).toBe(true)
      view.unmount()
    })

    it('AutoHeight：根钩子与默认插槽', () => {
      const view = kit.mount('AutoHeight', {
        props: { maxHeight: 120 },
        slots: { default: probeSlot('default') },
      })
      expect(view.has('.bms-auto-height .probe-default')).toBe(true)
      view.unmount()
    })

    it('LazyContainer：无 IO 环境直接渲染（降级）', () => {
      const view = kit.mount('LazyContainer', {
        slots: { default: probeSlot('default') },
      })
      expect(view.has('.probe-default')).toBe(true)
      expect(view.has('.bms-lazy-container-placeholder')).toBe(false)
      view.unmount()
    })

    it('LoadingContainer：内容 / 加载 / 错误 / 空态互斥与重试', async () => {
      const view = kit.mount('LoadingContainer', {
        props: { delay: 0 },
        slots: { default: probeSlot('default') },
      })
      expect(view.has('.probe-default')).toBe(true)

      const loading = kit.mount('LoadingContainer', { props: { delay: 0, loading: true } })
      expect(loading.has('[data-testid="loading-state"]')).toBe(true)
      loading.unmount()

      const empty = kit.mount('LoadingContainer', { props: { delay: 0, empty: true } })
      expect(empty.has('[data-testid="empty-state"]')).toBe(true)
      empty.unmount()

      const failed = kit.mount('LoadingContainer', { props: { delay: 0, error: '出错了' } })
      expect(failed.has('[data-testid="error-state"]')).toBe(true)
      expect(failed.text()).toContain('出错了')
      await failed.trigger('[data-testid="retry-button"]', 'click')
      expect(failed.emitted('retry')).toHaveLength(1)
      failed.unmount()
    })

    it('SectionContainer：标题与折叠事件', async () => {
      const view = kit.mount('SectionContainer', {
        props: { title: '基本信息', collapsible: true },
        slots: { default: probeSlot('default') },
      })
      expect(view.has('.bms-section-container-title')).toBe(true)
      expect(view.text()).toContain('基本信息')
      expect(view.has('.bms-section-container-content .probe-default')).toBe(true)
      await view.trigger('[data-testid="section-toggle"]', 'click')
      expect(view.emitted('update:collapsed')[0]).toEqual([true])
      expect(view.emitted('collapse-change')[0]).toEqual([true])
      view.unmount()
    })

    it('VirtualList：撑高与可视切片', async () => {
      const items = Array.from({ length: 100 }, (_, index) => ({ id: index + 1 }))
      const view = kit.mount('VirtualList', {
        props: { items, itemHeight: 20, height: 100, buffer: 2, throttle: 0 },
      })
      expect(view.attr('.bms-virtual-list-spacer', 'style')).toContain('height: 2000px')
      const initial = view.count('.bms-virtual-list-item')
      expect(initial).toBeGreaterThan(0)
      expect(initial).toBeLessThan(items.length)

      await view.stubMetrics('.bms-virtual-list', { scrollHeight: 4000, clientHeight: 100, scrollTop: 400 })
      await view.trigger('.bms-virtual-list', 'scroll')
      await view.flushRender()
      const metrics = view.emitted('scroll')[0]?.[0] as { startIndex: number; endIndex: number } | undefined
      expect(metrics?.startIndex).toBe(18)
      expect(metrics?.endIndex).toBe(28)
      view.unmount()
    })

    it('FullscreenContainer：暴露 enter / exit / toggle 与根钩子', () => {
      const view = kit.mount('FullscreenContainer', { slots: { default: probeSlot('default') } })
      const exposed = view.exposed<{ enter?: unknown; exit?: unknown; toggle?: unknown }>()
      expect(typeof exposed.enter).toBe('function')
      expect(typeof exposed.exit).toBe('function')
      expect(typeof exposed.toggle).toBe('function')
      expect(view.has('.bms-fullscreen-container .probe-default')).toBe(true)
      view.unmount()
    })
  })
}

export function describePermButtonContract(kit: ComponentContractKit): void {
  describe('权限按钮契约（同一套断言）', () => {
    it('无权限码视为不限制：渲染并透传点击', async () => {
      const view = kit.mount('PermButton', { slots: { default: '新建' } })
      expect(view.has('.bms-perm-button')).toBe(true)
      await view.trigger('.bms-perm-button', 'click')
      expect(view.emitted('click')).toHaveLength(1)
      view.unmount()
    })

    it('无权限：默认隐藏；disable 兜底渲染禁用态并拦截点击', async () => {
      kit.configurePermissionChecker(() => false)
      try {
        const hidden = kit.mount('PermButton', { props: { perm: 'user:create' }, slots: { default: '新建' } })
        expect(hidden.has('.bms-perm-button')).toBe(false)
        hidden.unmount()

        const disabled = kit.mount('PermButton', {
          props: { perm: 'user:create', fallback: 'disable' },
          slots: { default: '新建' },
        })
        expect(disabled.has('.bms-perm-button')).toBe(true)
        expect(disabled.attr('.bms-perm-button', 'disabled')).toBeDefined()
        expect(disabled.attr('.bms-perm-button', 'title')).toBeTruthy()
        await disabled.trigger('.bms-perm-button', 'click')
        expect(disabled.emitted('click')).toHaveLength(0)
        disabled.unmount()
      } finally {
        kit.configurePermissionChecker(undefined)
      }
    })

    it('有权限：渲染并透传点击', async () => {
      kit.configurePermissionChecker((codes) => codes.includes('user:create'))
      try {
        const view = kit.mount('PermButton', { props: { perm: 'user:create' }, slots: { default: '新建' } })
        expect(view.has('.bms-perm-button')).toBe(true)
        await view.trigger('.bms-perm-button', 'click')
        expect(view.emitted('click')).toHaveLength(1)
        view.unmount()
      } finally {
        kit.configurePermissionChecker(undefined)
      }
    })
  })
}

export function describeFeedbackComponentsContract(kit: ComponentContractKit): void {
  describe('反馈件契约（同一套断言）', () => {
    it('EmptyState：场景缺省标题 / small 修饰类 / 引导按钮与权限', async () => {
      const view = kit.mount('EmptyState', { props: { type: 'search' } })
      expect(view.has('.bms-empty-state')).toBe(true)
      expect(view.has('.bms-empty-state-title')).toBe(true)
      expect(view.text()).toContain('未找到相关内容')
      view.unmount()

      const small = kit.mount('EmptyState', { props: { type: 'list', size: 'small' } })
      expect(small.has('.bms-empty-state--small')).toBe(true)
      small.unmount()

      kit.configurePermissionChecker(() => false)
      try {
        const blocked = kit.mount('EmptyState', {
          props: { type: 'list', action: { key: 'create' }, actionPerm: 'user:create' },
        })
        expect(blocked.has('.bms-empty-state-action')).toBe(false)
        blocked.unmount()
      } finally {
        kit.configurePermissionChecker(undefined)
      }

      const allowed = kit.mount('EmptyState', {
        props: { type: 'list', action: { key: 'create' } },
      })
      expect(allowed.has('.bms-empty-state-action')).toBe(true)
      await allowed.trigger('.bms-empty-state-action button', 'click')
      expect(allowed.emitted('action')).toHaveLength(1)
      allowed.unmount()
    })

    it('ErrorPage：code 决定动作集；[data-action] 点击 emit 对应事件', async () => {
      const notFound = kit.mount('ErrorPage', { props: { code: 404 } })
      expect(notFound.has('.bms-error-page-title')).toBe(true)
      expect(notFound.count('.bms-error-page-actions button')).toBe(1)
      await notFound.trigger('[data-action="home"]', 'click')
      expect(notFound.emitted('home')).toHaveLength(1)
      notFound.unmount()

      const server = kit.mount('ErrorPage', { props: { code: 500 } })
      expect(server.count('.bms-error-page-actions button')).toBe(2)
      expect(server.has('[data-action="retry"]')).toBe(true)
      await server.trigger('[data-action="home"]', 'click')
      expect(server.emitted('home')).toHaveLength(1)
      server.unmount()

      const forbidden = kit.mount('ErrorPage', { props: { code: 403 } })
      expect(forbidden.count('.bms-error-page-actions button')).toBe(2)
      await forbidden.trigger('[data-action="contact"]', 'click')
      expect(forbidden.emitted('contact')).toHaveLength(1)
      forbidden.unmount()

      const custom = kit.mount('ErrorPage', {
        props: { code: 403, actions: [{ key: 'custom', text: '自定义', handler: () => {} }] },
      })
      expect(custom.count('.bms-error-page-actions button')).toBe(1)
      expect(custom.text()).toContain('自定义')
      custom.unmount()
    })

    it('SkeletonBlock：variant 修饰类 / 行数 / loading=false 渲染插槽', () => {
      const table = kit.mount('SkeletonBlock', { props: { variant: 'table', rows: 3 } })
      expect(table.has('.bms-skeleton--table')).toBe(true)
      expect(table.count('.bms-skeleton-row')).toBe(4)
      table.unmount()

      const list = kit.mount('SkeletonBlock', { props: { variant: 'list', rows: 4 } })
      expect(list.has('.bms-skeleton--list')).toBe(true)
      expect(list.count('.bms-skeleton-line')).toBe(4)
      list.unmount()

      const loaded = kit.mount('SkeletonBlock', {
        props: { loading: false },
        slots: { default: '<div class="probe-content">内容</div>' },
      })
      expect(loaded.has('.probe-content')).toBe(true)
      expect(loaded.has('.bms-skeleton')).toBe(false)
      loaded.unmount()
    })

    it('LoadingMask：delay=0 显示遮罩 / 关闭移除 / fullscreen 修饰类', async () => {
      const shown = kit.mount('LoadingMask', { props: { loading: true, delay: 0 } })
      expect(shown.has('.bms-loading-mask-overlay')).toBe(true)
      expect(shown.attr('.bms-loading-mask-overlay', 'role')).toBe('status')
      shown.unmount()

      const hidden = kit.mount('LoadingMask', { props: { loading: false, delay: 0 } })
      expect(hidden.has('.bms-loading-mask-overlay')).toBe(false)
      hidden.unmount()

      const fullscreen = kit.mount('LoadingMask', {
        props: { loading: true, delay: 0, fullscreen: true },
      })
      expect(fullscreen.has('.bms-loading-mask--fullscreen')).toBe(true)
      fullscreen.unmount()
    })
  })
}

/** 组件名 → 共同不变量所需的最小 props（VirtualList 需数据源才渲染项） */
function minimalProps(name: string): Record<string, unknown> {
  if (name === 'VirtualList') {
    return { items: [{ id: 1 }] }
  }
  return {}
}

/** 组件名 → 根类名钩子（`bms-` + kebab-case） */
function slugClass(name: string): string {
  const slug = name
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .toLowerCase()
  return `bms-${slug}`
}
