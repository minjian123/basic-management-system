/** 页面容器用例（Kiwi 741）：标题 / 插槽 / 返回与刷新。 */

import { describe, expect, it } from 'vitest'

import PageContainer from '@/components/layout/PageContainer.vue'

import { mountWithPlugins } from './helpers/mount'

function mountPage(props: Record<string, unknown> = {}, slots: Record<string, string> = {}) {
  return mountWithPlugins(PageContainer, {
    props: { title: '设置页', description: '描述文本', ...props },
    slots: { default: '<div class="body">内容</div>', ...slots },
  })
}

describe('页面容器（Kiwi 741）', () => {
  it('标题 / 描述 / 面包屑 / extra 插槽 / 默认内容', () => {
    const wrapper = mountPage(
      { breadcrumb: [{ label: '系统' }, { label: '设置' }] },
      { extra: '<button class="extra">操作</button>' },
    )
    expect(wrapper.text()).toContain('设置页')
    expect(wrapper.text()).toContain('描述文本')
    expect(wrapper.text()).toContain('系统')
    expect(wrapper.find('.extra').exists()).toBe(true)
    expect(wrapper.find('.body').exists()).toBe(true)
  })

  it('back 按钮与事件；刷新按钮与 refresh 事件', async () => {
    const wrapper = mountPage({ back: true })
    const buttons = wrapper.findAll('button')
    const back = buttons.find((button) => button.text().includes('←'))
    expect(back).toBeTruthy()
    await back?.trigger('click')
    expect(wrapper.emitted('back')).toBeTruthy()

    const refresh = buttons.find((button) => button.text().includes('⟳'))
    expect(refresh).toBeTruthy()
    await refresh?.trigger('click')
    expect(wrapper.emitted('refresh')).toBeTruthy()
  })

  it('sticky 类与底部操作栏', () => {
    const sticky = mountPage({ sticky: true })
    expect(sticky.find('.bms-page-container-header.is-sticky').exists()).toBe(true)

    const plain = mountPage({ sticky: false })
    expect(plain.find('.bms-page-container-header.is-sticky').exists()).toBe(false)

    const withFooter = mountPage({ footer: true }, { footer: '<div class="footer-actions">保存</div>' })
    expect(withFooter.find('.bms-page-container-footer').text()).toContain('保存')
  })
})
