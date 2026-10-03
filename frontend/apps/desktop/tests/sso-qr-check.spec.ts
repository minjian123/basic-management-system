// kiwi_id: 2233
/** 扫码登录核对页用例（05_04）：四组自检程序化跑通、页面渲染无失败项。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SsoQrCheck from '@/dev/SsoQrCheck.vue'

describe('扫码登录核对页（Kiwi 2233）', () => {
  it('渲染四组自检且全部通过（无失败项）', () => {
    const wrapper = mount(SsoQrCheck)

    const groups = wrapper.findAll('[data-check-group]')
    expect(groups).toHaveLength(4)

    const items = wrapper.findAll('[data-check]')
    expect(items.length).toBeGreaterThanOrEqual(8)

    const failed = wrapper.findAll('[data-ok="false"]')
    expect(failed.map((item) => item.text())).toEqual([])

    expect(wrapper.find('[data-check-passed]').text()).toBe(String(items.length))
  })

  it('含状态源与状态机口径章节', () => {
    const wrapper = mount(SsoQrCheck)
    expect(wrapper.text()).toContain('状态源与占位口径')
    expect(wrapper.text()).toContain('状态机与体验口径')
  })
})
