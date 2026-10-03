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

  // kiwi_id: 2238
  it('tabs 形态：每项一个页签（标题取展示名、缺省取键），按顺序提示稳定排序', () => {
    const registries = createRegistries()
    registries.pageArea.register(
      new PageAreaProvider('demo:extension', 'sys.user.detail.tabs', textComponent('ext', '扩展示例内容'), 20, {
        title: '用户扩展示例',
      }),
    )
    registries.pageArea.register(
      new PageAreaProvider('demo:basic', 'sys.user.detail.tabs', textComponent('basic', '基本信息内容'), 10, {
        title: '基本信息',
      }),
    )
    registries.pageArea.register(
      new PageAreaProvider('demo:raw', 'sys.user.detail.tabs', textComponent('raw', '无名内容'), 30),
    )

    const wrapper = mount(ModuleAreaOutlet, {
      props: { area: 'sys.user.detail.tabs', registries, variant: 'tabs' },
    })

    expect(wrapper.attributes('data-variant')).toBe('tabs')
    expect(wrapper.findAll('.el-tabs__item').map((item) => item.text())).toEqual([
      '基本信息',
      '用户扩展示例',
      'demo:raw',
    ])
    expect(wrapper.find('.el-tabs__item').classes()).toContain('is-active')
  })

  it('tabs 形态：权限码不满足的项不渲染；未知插槽渲染为空', () => {
    const registries = createRegistries()
    registries.pageArea.register(
      new PageAreaProvider('demo:open', 'sys.user.detail.tabs', textComponent('open', '公开'), 10, { title: '公开' }),
    )
    registries.pageArea.register(
      new PageAreaProvider('demo:gated', 'sys.user.detail.tabs', textComponent('gated', '受限'), 20, {
        title: '受限',
        perm: 'sys:user-extension:update',
      }),
    )

    const wrapper = mount(ModuleAreaOutlet, {
      props: { area: 'sys.user.detail.tabs', registries, variant: 'tabs', permissionCodes: [] },
    })
    expect(wrapper.findAll('.el-tabs__item').map((item) => item.text())).toEqual(['公开'])

    const empty = mount(ModuleAreaOutlet, { props: { area: 'unknown.area', registries, variant: 'tabs' } })
    expect(empty.findAll('.el-tabs__item')).toEqual([])
  })

  it('权限码变化后重算（inline 形态按权限显隐）', async () => {
    const registries = createRegistries()
    registries.pageArea.register(
      new PageAreaProvider('demo:gated', 'layout.header', textComponent('gated', '受限项'), 10, {
        perm: 'demo:edit',
      }),
    )

    const wrapper = mount(ModuleAreaOutlet, {
      props: { area: 'layout.header', registries, permissionCodes: [] },
    })
    expect(wrapper.findAll('span')).toEqual([])

    await wrapper.setProps({ permissionCodes: ['demo:edit'] })
    expect(wrapper.findAll('span').map((item) => item.text())).toEqual(['受限项'])
  })
})
