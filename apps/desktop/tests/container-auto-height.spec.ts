/** 自适应高度容器用例（Kiwi 747）：父剩余空间 / 重算去抖 / 内部滚动。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { AutoHeight } from '@/components/container'

import { mountWithPlugins } from './helpers/mount'
import { ROStub } from './helpers/observers'

type Wrapper = ReturnType<typeof mountWithPlugins>

function vmOf(wrapper: Wrapper): {
  recalculate: () => void
  height: number
  el: HTMLElement | null
} {
  return wrapper.vm as unknown as {
    recalculate: () => void
    height: number
    el: HTMLElement | null
  }
}

/**
 * 挂到受控父容器。
 *
 * 说明：`@vue/test-utils` 的 `attachTo` 会在宿主内再包一层 `data-v-app` 容器，
 * 组件实际父元素是它——尺寸需定义在该层（返回的 `parent`）。
 */
function mountAttached(
  clientHeight: number,
  props: Record<string, unknown> = {},
): { wrapper: Wrapper; parent: HTMLElement } {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const wrapper = mountWithPlugins(AutoHeight, { props, attachTo: host })
  const parent = wrapper.element.parentElement as HTMLElement
  Object.defineProperty(parent, 'clientHeight', { value: clientHeight, configurable: true })
  return { wrapper, parent }
}

beforeEach(() => {
  ROStub.instances = []
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('自适应高度容器（Kiwi 747）', () => {
  it('高度 = 父高 − offset；min / max 裁剪', async () => {
    vi.stubGlobal('ResizeObserver', ROStub)
    const { wrapper } = mountAttached(600, { offset: 100 })
    vmOf(wrapper).recalculate()
    await nextTick()
    expect(vmOf(wrapper).height).toBe(500)
    expect(wrapper.attributes('style')).toContain('height: 500px')

    const { wrapper: minWrapper } = mountAttached(600, { minHeight: 700 })
    vmOf(minWrapper).recalculate()
    await nextTick()
    expect(vmOf(minWrapper).height).toBe(700)

    const { wrapper: maxWrapper } = mountAttached(600, { maxHeight: 400 })
    vmOf(maxWrapper).recalculate()
    await nextTick()
    expect(vmOf(maxWrapper).height).toBe(400)
  })

  it('父高不可测时回退窗口视口高（innerHeight）', async () => {
    vi.stubGlobal('ResizeObserver', ROStub)
    const wrapper = mountWithPlugins(AutoHeight)
    vmOf(wrapper).recalculate()
    await nextTick()
    expect(vmOf(wrapper).height).toBe(window.innerHeight)
  })

  it('ResizeObserver 观察父元素：触发后（去抖）重算；offset 变更即时重算', async () => {
    vi.stubGlobal('ResizeObserver', ROStub)
    vi.useFakeTimers()
    const { wrapper, parent } = mountAttached(600, { offset: 100, resizeDebounce: 100 })
    const vm = vmOf(wrapper)

    const ro = ROStub.instances[0]
    expect(ro).toBeDefined()
    expect(ro.observed).toContain(parent)

    Object.defineProperty(parent, 'clientHeight', { value: 800, configurable: true })
    ro.callback([{ target: parent }])
    vi.advanceTimersByTime(100)
    await nextTick()
    expect(vm.height).toBe(700)

    await wrapper.setProps({ offset: 200 })
    await nextTick()
    expect(vm.height).toBe(600)
  })

  it('scroll 类与暴露方法 / 元素', async () => {
    vi.stubGlobal('ResizeObserver', ROStub)
    const { wrapper, parent } = mountAttached(500)
    vmOf(wrapper).recalculate()
    await nextTick()
    expect(wrapper.classes()).toContain('bms-auto-height--scroll')

    const { wrapper: plain } = mountAttached(500, { scroll: false })
    expect(plain.classes()).not.toContain('bms-auto-height--scroll')

    const vm = vmOf(wrapper)
    expect(vm.el).toBe(wrapper.find('.bms-auto-height').element)
    Object.defineProperty(parent, 'clientHeight', { value: 520, configurable: true })
    vm.recalculate()
    await nextTick()
    expect(vm.height).toBe(520)
  })
})
