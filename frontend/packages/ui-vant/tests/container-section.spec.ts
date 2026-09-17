/** 分区容器用例（Kiwi 750）：标题 / 折叠 / 档位与令牌。 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import { SectionContainer } from '../src'

import { mountWithPlugins } from './helpers/mount'

type Wrapper = ReturnType<typeof mountWithPlugins>

function rootOf(wrapper: Wrapper): HTMLElement {
  return wrapper.find('.bms-section-container').element as HTMLElement
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('分区容器（Kiwi 750）', () => {
  it('标题 / 描述 / 插槽渲染；divider 开关', () => {
    const wrapper = mountWithPlugins(SectionContainer, {
      props: { title: '基本信息', description: '账号与联系方式' },
    })
    expect(wrapper.find('.bms-section-container-title').text()).toBe('基本信息')
    expect(wrapper.find('.bms-section-container-description').text()).toBe('账号与联系方式')
    expect(wrapper.find('.bms-section-container-header--divider').exists()).toBe(true)

    const custom = mountWithPlugins(SectionContainer, {
      slots: {
        title: '<div class="my-title">自定义标题</div>',
        extra: '<div class="my-extra">工具区</div>',
        default: '<div class="my-body">内容</div>',
        footer: '<div class="my-footer">页脚</div>',
      },
    })
    expect(custom.find('.bms-section-container-title .my-title').exists()).toBe(true)
    expect(custom.find('.bms-section-container-extra .my-extra').exists()).toBe(true)
    expect(custom.find('[data-testid="section-content"] .my-body').exists()).toBe(true)
    expect(custom.find('.bms-section-container-footer .my-footer').exists()).toBe(true)

    const plain = mountWithPlugins(SectionContainer, { props: { title: '无分隔线', divider: false } })
    expect(plain.find('.bms-section-container-header--divider').exists()).toBe(false)
  })

  it('padding 档位类与区域属性透传', () => {
    const large = mountWithPlugins(SectionContainer, { props: { title: 'x', padding: 'large' } })
    expect(large.find('.bms-section-container--padding-large').exists()).toBe(true)

    const none = mountWithPlugins(SectionContainer, { props: { title: 'x', padding: 'none' } })
    expect(none.find('.bms-section-container--padding-none').exists()).toBe(true)

    const small = mountWithPlugins(SectionContainer, { props: { title: 'x', padding: 'small' } })
    expect(rootOf(small).getAttribute('data-padding')).toBe('compact')
    expect(rootOf(small).getAttribute('data-collapsed')).toBe('false')
  })

  it('折叠（非受控）：toggle 切换、内容 v-if、标题保留、事件通知', async () => {
    const wrapper = mountWithPlugins(SectionContainer, {
      props: { title: '分组', collapsible: true },
      slots: { default: '<div class="my-body">内容</div>' },
    })
    expect(wrapper.find('[data-testid="section-content"]').exists()).toBe(true)

    await wrapper.find('[data-testid="section-toggle"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-testid="section-content"]').exists()).toBe(false)
    expect(wrapper.find('.bms-section-container-title').text()).toBe('分组')
    expect(wrapper.emitted('collapse-change')?.[0]).toEqual([true])
    expect(wrapper.emitted('update:collapsed')?.[0]).toEqual([true])
    expect(rootOf(wrapper).getAttribute('data-collapsed')).toBe('true')

    await wrapper.find('[data-testid="section-toggle"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-testid="section-content"]').exists()).toBe(true)
    expect(wrapper.emitted('collapse-change')?.at(-1)).toEqual([false])
  })

  it('折叠（受控）：点击只回写、由外部切换；collapsible=false 无开关', async () => {
    const wrapper = mountWithPlugins(SectionContainer, {
      props: { title: '受控分组', collapsible: true, collapsed: false },
      slots: { default: '<div class="my-body">内容</div>' },
    })
    await wrapper.find('[data-testid="section-toggle"]').trigger('click')
    await nextTick()
    expect(wrapper.emitted('update:collapsed')?.[0]).toEqual([true])
    // 受控：未回写前内容仍在
    expect(wrapper.find('[data-testid="section-content"]').exists()).toBe(true)

    await wrapper.setProps({ collapsed: true })
    await nextTick()
    expect(wrapper.find('[data-testid="section-content"]').exists()).toBe(false)

    const plain = mountWithPlugins(SectionContainer, { props: { title: '不可折叠' } })
    expect(plain.find('[data-testid="section-toggle"]').exists()).toBe(false)
  })
})
