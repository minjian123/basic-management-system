/** 顶栏全局搜索入口用例（07-06_01 补修，按原型置于折叠按钮旁）：入口渲染与占位文案。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppHeaderSearch from '@/components/AppHeaderSearch.vue'

describe('AppHeaderSearch（顶栏全局搜索）', () => {
  it('渲染搜索入口与占位提示，业务侧零裸原生件', () => {
    const wrapper = mount(AppHeaderSearch)
    const input = wrapper.find('[data-test="header-search"]')

    expect(input.exists()).toBe(true)
    expect(input.attributes('placeholder')).toBe('全局搜索：模块 / 单据')
    expect(wrapper.findAll('input').length).toBe(1)
  })
})
