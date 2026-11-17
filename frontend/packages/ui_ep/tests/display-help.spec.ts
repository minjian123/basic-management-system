// kiwi_id: 2525
/** 帮助入口（09_02）：显隐 / 五态 / 分类 / 重试 / 关闭后不再显示。 */

import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import HelpEntry from '../src/components/display/HelpEntry.vue'

/** 长文对话框桩（就地渲染插槽并回传关闭）。 */
const longTextStub = {
  props: ['modelValue', 'title'],
  emits: ['update:modelValue', 'close'],
  template:
    '<div v-if="modelValue" data-test="long-text-stub"><span data-test="stub-title">{{ title }}</span><button data-test="stub-close" @click="$emit(\'close\'); $emit(\'update:modelValue\', false)">关闭</button><slot /></div>',
}

/**
 * 挂载帮助入口。
 *
 * @param props 覆盖属性。
 * @returns 测试装配。
 */
function mountEntry(props: Record<string, unknown> = {}) {
  return mount(HelpEntry, {
    props: { descriptor: { context: { moduleKey: 'm1' }, anchorAvailable: true }, ...props },
    global: { stubs: { LongTextDialog: longTextStub } },
  })
}

describe('HelpEntry 帮助入口（09_02）', () => {
  it('页内按锚点显示；命中文章渲染层级与清洗后的正文', async () => {
    const fetcher = vi.fn(async () => ({
      matched: true,
      anchor_found: true,
      level: 'module',
      article: {
        id: '1',
        title: '模块帮助',
        content: '<p>正文</p><script>alert(1)</script>',
        source: 'product',
      },
      related: [{ id: '2', title: '更多帮助', source: 'builtin' }],
      categories: [{ id: '9', name: '快速上手', path: '快速上手' }],
    }))
    const wrapper = mountEntry({ fetcher })
    expect(wrapper.find('[data-test="help-entry"]').text()).toBe('帮助')

    await wrapper.find('[data-test="help-entry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="stub-title"]').text()).toBe('模块帮助')
    expect(wrapper.find('[data-test="help-level"]').text()).toBe('模块帮助')
    expect(wrapper.find('[data-test="help-source"]').text()).toBe('产品包')
    const content = wrapper.find('[data-test="help-article-content"]').html()
    expect(content).toContain('正文')
    expect(content).not.toContain('script')
    expect(wrapper.find('[data-test="help-related"]').text()).toContain('更多帮助')
    expect(wrapper.find('[data-test="help-categories"]').exists()).toBe(true)
    expect(wrapper.emitted('open')).toHaveLength(1)
  })

  it('无锚点不显示；顶栏常驻', () => {
    const hidden = mountEntry({ descriptor: { context: {}, anchorAvailable: false }, fetcher: vi.fn() })
    expect(hidden.find('[data-test="help-entry"]').exists()).toBe(false)

    const header = mount(HelpEntry, { props: { mode: 'header' }, global: { stubs: { LongTextDialog: longTextStub } } })
    expect(header.find('[data-test="header-help"]').exists()).toBe(true)
  })

  it('有锚点无文章：提示暂无帮助内容并给分类', async () => {
    const wrapper = mountEntry({
      fetcher: vi.fn(async () => ({
        matched: false,
        anchor_found: true,
        categories: [{ id: '9', name: '快速上手', path: '快速上手' }],
      })),
    })
    await wrapper.find('[data-test="help-entry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="help-no-article"]').text()).toContain('暂无帮助内容')
    const category = wrapper.find('[data-test="help-no-article"] button')
    await category.trigger('click')
    expect(wrapper.emitted('category')?.[0]).toEqual(['9'])
  })

  it('失败给错误与重试；重试成功后渲染文章', async () => {
    let first = true
    const fetcher = vi.fn(async () => {
      if (first) {
        first = false
        throw new Error('帮助服务不可用')
      }
      return { matched: true, anchor_found: true, article: { id: '2', title: '帮助', content: '<p>ok</p>' } }
    })
    const wrapper = mountEntry({ fetcher })
    await wrapper.find('[data-test="help-entry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="help-error"]').text()).toContain('帮助服务不可用')
    expect(wrapper.emitted('error')).toHaveLength(1)

    await wrapper.find('[data-test="help-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="help-article-content"]').html()).toContain('ok')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })

  it('元数据有锚点但解析无锚点：按暂无帮助呈现，关闭后不再显示', async () => {
    const wrapper = mountEntry({ fetcher: vi.fn(async () => ({ matched: false, anchor_found: false, categories: [] })) })
    await wrapper.find('[data-test="help-entry"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="help-empty"]').text()).toContain('暂无帮助')

    await wrapper.find('[data-test="stub-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="help-entry"]').exists()).toBe(false)
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
