// kiwi_id: 2525
/** 长文阅读对话框（09_02）：640 档 / 宽度下限 / 正文插槽 / 页脚关闭。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import LongTextDialog from '../src/components/modal/LongTextDialog.vue'

/** 弹窗桩（暴露宽度与标题，就地渲染插槽）。 */
const dialogStub = {
  props: ['modelValue', 'title', 'width', 'closeOnClickModal', 'closeOnPressEscape'],
  template:
    '<div data-test="dialog-stub" :data-width="width" :data-title="title" :data-modal="String(closeOnClickModal)" :data-esc="String(closeOnPressEscape)"><slot /><slot name="footer" /></div>',
}

/**
 * 挂载长文对话框。
 *
 * @param props 覆盖属性。
 * @returns 测试装配。
 */
function mountDialog(props: Record<string, unknown> = {}) {
  return mount(LongTextDialog, {
    props: { modelValue: true, title: '帮助', ...props },
    slots: { default: '<p data-test="long-text-content">正文</p>' },
    global: { stubs: { ElDialog: dialogStub } },
  })
}

describe('LongTextDialog 长文阅读对话框（09_02）', () => {
  it('缺省 640 宽、标题与正文渲染、正文独立滚动容器', () => {
    const wrapper = mountDialog()
    const dialog = wrapper.find('.bms-long-text-dialog')
    expect(dialog.attributes('data-width')).toBe('640')
    expect(dialog.attributes('data-title')).toBe('帮助')
    expect(wrapper.find('[data-test="long-text-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="long-text-content"]').text()).toBe('正文')
    expect(wrapper.find('[data-test="long-text-footer"]').exists()).toBe(true)
  })

  it('宽度低于 480 时夹取下限；阅读型允许遮罩 / Esc 关闭', () => {
    const wrapper = mountDialog({ width: 400 })
    expect(wrapper.find('.bms-long-text-dialog').attributes('data-width')).toBe('480')
    expect(wrapper.find('.bms-long-text-dialog').attributes('data-modal')).toBe('true')
    expect(wrapper.find('.bms-long-text-dialog').attributes('data-esc')).toBe('true')
  })

  it('页脚关闭发出 close 与 update:modelValue=false', async () => {
    const wrapper = mountDialog()
    await wrapper.find('[data-test="long-text-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).toContain(false)
  })
})
