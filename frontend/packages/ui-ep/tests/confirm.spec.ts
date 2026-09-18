/** 二次确认用例（03_01）。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ConfirmDialog from '../src/components/modal/ConfirmDialog.vue'
import { useConfirm } from '../src'

describe('ConfirmDialog', () => {
  it('渲染标题与内容并发出确认 / 取消', async () => {
    const wrapper = mount(ConfirmDialog, {
      props: { modelValue: true, title: '删除确认', content: '确定删除吗？', danger: true },
      global: {
        stubs: {
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          ElButton: { template: '<button><slot /></button>' },
        },
      },
    })
    expect(wrapper.props('title')).toBe('删除确认')
    expect(wrapper.text()).toContain('确定删除吗？')
    await wrapper.find('[data-test="confirm-ok"]').trigger('click')
    await wrapper.find('[data-test="confirm-cancel"]').trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })
})

describe('useConfirm', () => {
  it('confirm() 返回 Promise 并由 resolveConfirm 结算', async () => {
    const { state, confirm, resolveConfirm } = useConfirm()
    const pending = confirm({ title: 't', content: 'c', danger: true })
    expect(state.visible.value).toBe(true)
    expect(state.title.value).toBe('t')
    expect(state.danger.value).toBe(true)

    resolveConfirm(true)
    expect(state.visible.value).toBe(false)
    await expect(pending).resolves.toBe(true)
  })

  it('取消结算为 false', async () => {
    const { confirm, resolveConfirm } = useConfirm()
    const pending = confirm()
    resolveConfirm(false)
    await expect(pending).resolves.toBe(false)
  })
})
