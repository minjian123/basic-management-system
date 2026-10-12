/** 工作台首页用例（04-1-1）：骨架页以页面容器承载标题 / 描述与占位提示。 */

import { PageContainer } from '@bms/ui-ep'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import HomeView from '@/views/HomeView.vue'

describe('工作台首页（04-1-1）', () => {
  it('以页面容器承载工作台标题 / 描述与占位提示', () => {
    const wrapper = mount(HomeView)

    const container = wrapper.findComponent(PageContainer)
    expect(container.exists()).toBe(true)
    expect(container.props('title')).toBe('工作台')
    expect(container.props('description')).toBe('BMS 基础管理系统')

    const hint = wrapper.find('.home__hint')
    expect(hint.exists()).toBe(true)
    expect(hint.text()).toContain('本页为前端组件库阶段的骨架首页')

    wrapper.unmount()
  })
})
