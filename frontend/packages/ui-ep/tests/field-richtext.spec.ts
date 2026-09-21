// kiwi_id: 970
/** 富文本字段用例（06_03_01）。 */

import { mount } from '@vue/test-utils'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { RichTextField, sanitizeHtml, sanitizeToText } from '../src'

/** 编辑器内核宿主替身（避免 jsdom 中初始化 TipTap）。 */
const RichTextEditorStub = {
  name: 'RichTextEditor',
  props: {
    modelValue: { type: String, default: '' },
    readOnly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
  },
  emits: ['update:modelValue'],
  template: '<div class="bms-rich-text-editor" data-test="rich-editor" />',
}

const stubs = { RichTextEditor: RichTextEditorStub }

beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  })
})

describe('sanitizeHtml 白名单清洗', () => {
  it('移除脚本 / 事件属性 / 危险协议，保留白名单', () => {
    const dirty = '<p>安全</p><script>alert(1)</script><img src="x" onerror="alert(2)" /><a href="javascript:alert(3)">x</a>'
    const clean = sanitizeHtml(dirty)
    expect(clean).toContain('<p>安全</p>')
    expect(clean).not.toContain('<script')
    expect(clean).not.toContain('onerror')
    expect(clean.toLowerCase()).not.toContain('javascript:')
  })

  it('纯文本提取用于字数统计', () => {
    expect(sanitizeToText('<p>你好 <strong>世界</strong></p>')).toBe('你好 世界')
  })
})

describe('RichTextField', () => {
  it('源码模式输入经清洗后派发', async () => {
    const wrapper = mount(RichTextField, { props: { modelValue: '', mode: 'source' }, global: { stubs } })
    const textarea = wrapper.find('[data-test="rich-source"]')
    await textarea.setValue('<p>正文</p><script>bad()</script>')
    const emitted = wrapper.emitted('update:modelValue')?.at(-1) as string[]
    expect(emitted[0]).toContain('<p>正文</p>')
    expect(emitted[0]).not.toContain('<script')
  })

  it('富文本模式挂载内核宿主（替身）', async () => {
    const wrapper = mount(RichTextField, { props: { modelValue: '<p>x</p>', mode: 'rich' }, global: { stubs } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="rich-editor"]').exists()).toBe(true)
    expect(wrapper.attributes('data-mode')).toBe('rich')
  })

  it('只读渲染清洗后的 HTML', () => {
    const wrapper = mount(RichTextField, {
      props: { modelValue: '<p>只读</p><script>bad()</script>', readOnly: true },
      global: { stubs },
    })
    const readonly = wrapper.find('[data-test="rich-readonly"]')
    expect(readonly.html()).toContain('<p>只读</p>')
    expect(readonly.html()).not.toContain('<script')
    expect(wrapper.find('[data-test="rich-editor"]').exists()).toBe(false)
  })

  it('超最大字数发 invalid 且不写值', async () => {
    const wrapper = mount(RichTextField, { props: { modelValue: '', mode: 'source', maxLength: 3 }, global: { stubs } })
    await wrapper.find('[data-test="rich-source"]').setValue('<p>一二三四</p>')
    expect(wrapper.emitted('invalid')?.[0]).toEqual(['最多 3 字'])
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.find('[data-test="field-error"]').text()).toBe('最多 3 字')
  })

  it('图片上传降级与成功插入', async () => {
    const degraded = mount(RichTextField, { props: { modelValue: '', mode: 'source' }, global: { stubs } })
    expect(await degraded.vm.uploadAndInsert(new File([''], 'a.png'))).toBeUndefined()
    expect(degraded.emitted('upload-error')?.[0]).toEqual(['上传未就绪'])

    const fine = mount(RichTextField, {
      props: { modelValue: '', mode: 'source', uploadImage: async () => 'https://cdn/x.png' },
      global: { stubs },
    })
    expect(await fine.vm.uploadAndInsert(new File([''], 'a.png'))).toBe('https://cdn/x.png')
    expect(String(fine.emitted('update:modelValue')?.at(-1)?.[0])).toContain('<img src="https://cdn/x.png"')
  })
})
