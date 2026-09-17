/**
 * `@bms/vue/testing`：Vue 侧契约挂载适配（仅测试消费）。
 *
 * 把 `@vue/test-utils` 的 wrapper 适配为 `@bms/core/testing` 的 `ComponentContractKit`
 * 结构接口——核心契约用例工厂不引入 Vue 类型；本入口只做结构桥接。
 */

import { nextTick } from 'vue'

import type { PermissionChecker } from '@bms/core'
import type {
  ComponentContractKit,
  ComponentMountOptions,
  ComponentViewHandle,
  ScrollMetricsStub,
} from '@bms/core/testing'

interface ElementLike {
  exists(): boolean
  attributes(name: string): string | undefined
  trigger(event: string): Promise<void>
  element: unknown
}

interface WrapperLike {
  html(): string
  text(): string
  find(selector: string): ElementLike
  findAll(selector: string): ElementLike[]
  emitted(event: string): unknown[][]
  vm: unknown
  unmount(): void
}

export interface MountLike {
  (component: unknown, options?: Record<string, unknown>): WrapperLike
}

export interface CreateContractKitOptions {
  /** `@vue/test-utils` 的 `mount`（结构兼容即可） */
  mount: MountLike
  /** 插件出口对象（按名取组件：`ScrollContainer` / `PermButton` …） */
  components: Record<string, unknown>
  /** 插件的 `configurePermissionChecker`（权限按钮契约注入判定器） */
  configurePermissionChecker(next: PermissionChecker | undefined): void
  /** 全局挂载选项（i18n 等插件；各实现按需注入） */
  global?: Record<string, unknown>
}

export function createContractKit(options: CreateContractKitOptions): ComponentContractKit {
  const nextFrame = async (): Promise<void> => {
    const raf = (globalThis as { requestAnimationFrame?: (callback: () => void) => number })
      .requestAnimationFrame
    if (raf) {
      await new Promise<void>((resolve) => raf(() => resolve()))
    }
    await nextTick()
  }
  return {
    mount(name: string, mountOptions: ComponentMountOptions = {}): ComponentViewHandle {
      const component = options.components[name]
      if (!component) {
        throw new Error(`契约套件：插件未导出组件「${name}」`)
      }
      const wrapper = options.mount(component, {
        props: mountOptions.props,
        slots: mountOptions.slots,
        ...(options.global ? { global: options.global } : {}),
      })
      return {
        html: () => wrapper.html(),
        text: () => wrapper.text(),
        has: (selector: string) => wrapper.find(selector).exists(),
        count: (selector: string) => wrapper.findAll(selector).length,
        attr: (selector: string, attribute: string) =>
          wrapper.find(selector).attributes(attribute),
        trigger: (selector: string, event: string) => wrapper.find(selector).trigger(event),
        emitted: (event: string) => wrapper.emitted(event) ?? [],
        flushRender: nextFrame,
        stubMetrics: async (selector: string, metrics: ScrollMetricsStub) => {
          const element = wrapper.find(selector).element as Record<string, unknown>
          if (metrics.scrollHeight !== undefined) {
            Object.defineProperty(element, 'scrollHeight', {
              value: metrics.scrollHeight,
              configurable: true,
            })
          }
          if (metrics.clientHeight !== undefined) {
            Object.defineProperty(element, 'clientHeight', {
              value: metrics.clientHeight,
              configurable: true,
            })
          }
          if (metrics.scrollTop !== undefined) {
            element.scrollTop = metrics.scrollTop
          }
          await nextFrame()
        },
        exposed: <T = Record<string, unknown>,>() => wrapper.vm as T,
        unmount: () => wrapper.unmount(),
      }
    },
    configurePermissionChecker: options.configurePermissionChecker,
  }
}
