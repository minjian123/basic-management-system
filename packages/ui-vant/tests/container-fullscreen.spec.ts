/** 全屏容器用例（Kiwi 746）：请求 / 降级 / 状态同步 / 首次提示。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { FullscreenContainer } from '../src'

import { mountWithPlugins } from './helpers/mount'

type Wrapper = ReturnType<typeof mountWithPlugins>

interface FullscreenStub {
  state: { element: Element | null }
  request: ReturnType<typeof vi.fn>
  exit: ReturnType<typeof vi.fn>
}

let stub: FullscreenStub

function stubFullscreen(supported = true): void {
  const state: { element: Element | null } = { element: null }
  Object.defineProperty(document, 'fullscreenElement', {
    configurable: true,
    get: () => state.element,
  })
  const request = vi.fn(function (this: Element) {
    if (!supported) {
      return Promise.reject(new Error('denied'))
    }
    state.element = this
    document.dispatchEvent(new Event('fullscreenchange'))
    return Promise.resolve()
  })
  Object.defineProperty(HTMLElement.prototype, 'requestFullscreen', {
    configurable: true,
    writable: true,
    value: request,
  })
  const exit = vi.fn(() => {
    state.element = null
    document.dispatchEvent(new Event('fullscreenchange'))
    return Promise.resolve()
  })
  Object.defineProperty(document, 'exitFullscreen', {
    configurable: true,
    writable: true,
    value: exit,
  })
  stub = { state, request, exit }
}

function vmOf(wrapper: Wrapper): {
  enter: () => Promise<void>
  exit: () => Promise<void>
  toggle: () => void
  isFullscreen: boolean
  isFallback: boolean
} {
  return wrapper.vm as unknown as {
    enter: () => Promise<void>
    exit: () => Promise<void>
    toggle: () => void
    isFullscreen: boolean
    isFallback: boolean
  }
}

async function flush(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
  await nextTick()
}

beforeEach(() => {
  stubFullscreen()
})

afterEach(() => {
  Reflect.deleteProperty(HTMLElement.prototype, 'requestFullscreen')
  Reflect.deleteProperty(document, 'exitFullscreen')
  Reflect.deleteProperty(document, 'fullscreenElement')
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('全屏容器（Kiwi 746）', () => {
  it('enter / exit / toggle：请求目标与状态同步', async () => {
    const wrapper = mountWithPlugins(FullscreenContainer, {
      props: { showTip: false },
      slots: { default: '<div class="fs-content">内容</div>' },
    })
    const vm = vmOf(wrapper)
    const root = wrapper.find('.bms-fullscreen-container').element

    await vm.enter()
    await flush()
    expect(stub.request).toHaveBeenCalledTimes(1)
    expect(vm.isFullscreen).toBe(true)
    expect(wrapper.emitted('fullscreen-change')?.[0]).toEqual([true])
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([true])

    await vm.exit()
    await flush()
    expect(stub.exit).toHaveBeenCalledTimes(1)
    expect(vm.isFullscreen).toBe(false)
    expect(wrapper.emitted('fullscreen-change')?.at(-1)).toEqual([false])

    vm.toggle()
    await flush()
    expect(stub.request).toHaveBeenCalledTimes(2)
    expect(stub.request.mock.instances[0]).toBe(root)
  })

  it('target=document：请求文档根元素', async () => {
    const wrapper = mountWithPlugins(FullscreenContainer, {
      props: { target: 'document', showTip: false },
    })
    await vmOf(wrapper).enter()
    await flush()
    expect(stub.request.mock.instances[0]).toBe(document.documentElement)
  })

  it('失败降级：fullscreen-error + 固定铺满 + 降级态 Esc 退出', async () => {
    stubFullscreen(false)
    const wrapper = mountWithPlugins(FullscreenContainer, { props: { showTip: false } })
    const vm = vmOf(wrapper)

    await vm.enter()
    await flush()
    expect(vm.isFullscreen).toBe(true)
    expect(vm.isFallback).toBe(true)
    expect(wrapper.emitted('fullscreen-error')?.[0]?.[0]).toContain('denied')
    expect(wrapper.find('.bms-fullscreen-container--fallback').exists()).toBe(true)

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flush()
    expect(vm.isFullscreen).toBe(false)
    expect(wrapper.find('.bms-fullscreen-container--fallback').exists()).toBe(false)
    expect(wrapper.emitted('fullscreen-change')?.at(-1)).toEqual([false])
  })

  it('首次提示：显示 i18n 文案、3 秒隐藏、二次进入不再显示、showTip=false 关闭', async () => {
    vi.useFakeTimers()
    const wrapper = mountWithPlugins(FullscreenContainer)
    const vm = vmOf(wrapper)

    await vm.enter()
    await flush()
    expect(wrapper.find('[data-testid="fullscreen-tip"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="fullscreen-tip"]').text()).toContain('已进入全屏')

    vi.advanceTimersByTime(3000)
    await nextTick()
    expect(wrapper.find('[data-testid="fullscreen-tip"]').exists()).toBe(false)

    await vm.exit()
    await flush()
    await vm.enter()
    await flush()
    expect(wrapper.find('[data-testid="fullscreen-tip"]').exists()).toBe(false)

    const muted = mountWithPlugins(FullscreenContainer, { props: { showTip: false } })
    await vmOf(muted).enter()
    await flush()
    expect(muted.find('[data-testid="fullscreen-tip"]').exists()).toBe(false)
  })

  it('卸载清理：全屏中卸载退出并移除监听', async () => {
    const wrapper = mountWithPlugins(FullscreenContainer, { props: { showTip: false } })
    await vmOf(wrapper).enter()
    await flush()
    wrapper.unmount()
    expect(stub.exit).toHaveBeenCalled()
  })
})
