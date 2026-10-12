/** 顶栏全局搜索入口用例（07-06_01 补修，按原型置于折叠按钮旁）：入口渲染、占位文案与回车提交占位提示。 */
// kiwi_id: 2241

import { mount } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AppHeaderSearch from '@/components/AppHeaderSearch.vue'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('AppHeaderSearch（顶栏全局搜索）', () => {
  it('渲染搜索入口与占位提示，业务侧零裸原生件', () => {
    const wrapper = mount(AppHeaderSearch)
    const input = wrapper.find('[data-test="header-search"]')

    expect(input.exists()).toBe(true)
    expect(input.attributes('placeholder')).toBe('全局搜索：模块 / 单据')
    expect(wrapper.findAll('input').length).toBe(1)
  })

  it('输入关键词双向绑定；回车触发占位提示（命令面板接线归后续任务）', async () => {
    const info = vi.spyOn(ElMessage, 'info').mockImplementation(() => ({}) as never)
    const wrapper = mount(AppHeaderSearch)
    const input = wrapper.find('input')

    await input.setValue('用户')
    expect(wrapper.vm.keyword).toBe('用户')

    await input.trigger('keyup.enter')
    expect(info).toHaveBeenCalledWith('全局搜索：功能开发中，见后续任务')
  })
})
