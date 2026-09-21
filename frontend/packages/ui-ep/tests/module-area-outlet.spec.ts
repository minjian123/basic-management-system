// kiwi_id: 977
/** 模块区域插槽用例（按区域标识只读消费区域项：保序渲染、空区域为空、装配变化重算）。 */

import { createRegistries, PageAreaProvider } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { h, ref } from 'vue'

import { ModuleAreaOutlet } from '../src'

/** 具名文本组件（渲染期渲染自身标题）。 */
function textComponent(name: string, text: string): { name: string; setup: () => () => unknown } {
  return { name, setup: () => () => h('span', { class: `probe-${name}` }, text) }
}

describe('ModuleAreaOutlet（Kiwi 977）', () => {
  it('按区域标识渲染已登记项（顺序提示升序，同值保持登记序）', () => {
    const registries = createRegistries()
    registries.pageArea.register(new PageAreaProvider('demo:late', 'layout.header', textComponent('late', '后'), 20))
    registries.pageArea.register(new PageAreaProvider('demo:first', 'layout.header', textComponent('first', '先'), 5))
    registries.pageArea.register(new PageAreaProvider('demo:other', 'page.top', textComponent('other', '其它区')))

    const wrapper = mount(ModuleAreaOutlet, {
      props: { area: 'layout.header', registries },
    })

    expect(wrapper.attributes('data-area')).toBe('layout.header')
    expect(wrapper.findAll('span').map((item) => item.text())).toEqual(['先', '后'])
  })

  it('空区域与未知区域渲染为空（不兜底）', () => {
    const registries = createRegistries()
    const wrapper = mount(ModuleAreaOutlet, { props: { area: 'layout.header', registries } })
    expect(wrapper.findAll('span')).toEqual([])

    registries.pageArea.register(new PageAreaProvider('demo:hero', 'layout.header', textComponent('hero', '顶栏')))
    const unknown = mount(ModuleAreaOutlet, { props: { area: 'unknown.area', registries } })
    expect(unknown.findAll('span')).toEqual([])
  })

  it('异步加载的挂接组件按需解析并渲染', async () => {
    const registries = createRegistries()
    // 模块声明的挂接内容为异步加载器（`() => import('...')` 形态由 Vue 自动解包 ES 模块）
    registries.pageArea.register(
      new PageAreaProvider('demo:hero', 'layout.header', () => Promise.resolve(textComponent('hero', '顶栏')), 10),
    )

    const wrapper = mount(ModuleAreaOutlet, { props: { area: 'layout.header', registries } })
    expect(wrapper.findAll('span')).toEqual([])

    await flushPromises()
    expect(wrapper.findAll('span').map((item) => item.text())).toEqual(['顶栏'])
  })

  it('装配版本号变化后重算（释放登记项后区域内容消失）', async () => {
    const registries = createRegistries()
    registries.pageArea.register(new PageAreaProvider('demo:hero', 'layout.header', textComponent('hero', '顶栏')))
    const revision = ref(0)

    const wrapper = mount(ModuleAreaOutlet, { props: { area: 'layout.header', registries, revision: revision.value } })
    expect(wrapper.findAll('span').map((item) => item.text())).toEqual(['顶栏'])

    registries.pageArea.unregister('demo:hero')
    revision.value += 1
    await wrapper.setProps({ revision: revision.value })

    expect(wrapper.findAll('span')).toEqual([])
  })
})
