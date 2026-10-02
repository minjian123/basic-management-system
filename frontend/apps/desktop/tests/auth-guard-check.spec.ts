/** 路由守卫核对页用例（05_03 / Kiwi 2231）：五组自检程序化跑通、页面渲染无失败项。 */
// kiwi_id: 2231

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AuthGuardCheck from '@/dev/AuthGuardCheck.vue'

describe('路由守卫核对页（Kiwi 2231）', () => {
  it('渲染五组自检且全部通过（无失败项）', () => {
    const wrapper = mount(AuthGuardCheck)

    const groups = wrapper.findAll('[data-check-group]')
    expect(groups).toHaveLength(5)

    const items = wrapper.findAll('[data-check]')
    expect(items).toHaveLength(20)

    const failed = wrapper.findAll('[data-ok="false"]')
    expect(failed.map((item) => item.text())).toEqual([])

    const passed = wrapper.find('[data-check-passed]')
    expect(passed.text()).toBe('20')
  })

  it('含等待态说明与接线口径章节', () => {
    const wrapper = mount(AuthGuardCheck)
    expect(wrapper.text()).toContain('等待态说明（刷新不闪登录页）')
    expect(wrapper.text()).toContain('守卫接线口径')
  })
})
