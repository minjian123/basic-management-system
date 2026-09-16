/** 弹窗抽屉表单用例：渲染 / 页脚动作 / 关闭拦截链 / 确认对话框。 */

import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createI18n } from 'vue-i18n'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ConfirmDialog, configureConfirm, FormDialog, FormDrawer } from '../src'

const confirmMock = vi.fn<(options: unknown) => Promise<boolean>>(async () => true)

const i18n = createI18n({
  legacy: false,
  locale: 'zh-CN',
  messages: {
    'zh-CN': {
      modal: {
        titleCreate: '新增{name}',
        titleEdit: '编辑{name}',
        titleView: '查看{name}',
        unsavedTitle: '未保存的修改',
        unsavedMessage: '有未保存的修改，确定放弃吗？',
        abandon: '放弃修改',
        continueEdit: '继续编辑',
        confirmTitle: '操作确认',
        deleteConfirm: '删除后不可恢复，确定继续？',
        detailFailed: '数据加载失败，请关闭后重试',
      },
      common: { save: '保存', cancel: '取消', delete: '删除', confirm: '确定' },
    },
  },
})

beforeEach(() => {
  confirmMock.mockReset().mockResolvedValue(true)
  configureConfirm((options) => confirmMock(options))
})

afterEach(() => {
  configureConfirm(undefined)
})

async function mountModal(
  component: Parameters<typeof mount>[0],
  props: Record<string, unknown>,
) {
  // EP 弹窗：Teleport stub（内容留在 wrapper 内）+ 首次以 visible=true 挂载不渲染（懒渲染）→ 先关后开
  const wrapper = mount(component, {
    props: { ...props, modelValue: false } as never,
    global: { plugins: [i18n], stubs: { teleport: true } },
  })
  await wrapper.setProps({ modelValue: true } as never)
  await nextTick()
  return wrapper
}

const baseDialogProps = {
  modelValue: true,
  mode: 'create' as const,
  title: '用户',
  width: 'md' as const,
}

describe('FormDialog（迁移）', () => {
  it('三态标题与页脚动作（提交 emit）', async () => {
    const wrapper = await mountModal(FormDialog, baseDialogProps)
    expect(wrapper.find('.bms-form-dialog').exists()).toBe(true)
    expect(wrapper.find('.bms-modal-title').text()).toBe('新增用户')

    const edit = await mountModal(FormDialog, { ...baseDialogProps, mode: 'edit' })
    expect(edit.find('.bms-modal-title').text()).toBe('编辑用户')

    const view = await mountModal(FormDialog, { ...baseDialogProps, mode: 'view' })
    expect(view.find('.bms-modal-title').text()).toBe('查看用户')

    const buttons = wrapper.findAll('.bms-modal-footer-actions button')
    const labels = buttons.map((button) => button.text())
    expect(labels).toContain('保存')
    expect(labels).toContain('取消')
    const submit = buttons.find((button) => button.text() === '保存')
    await submit?.trigger('click')
    expect(wrapper.emitted('submit')).toBeTruthy()
  })

  it('关闭拦截链：dirty + 确认拒绝 -> 不关闭；确认放行 -> cancel', async () => {
    confirmMock.mockResolvedValue(false)
    const blocked = await mountModal(FormDialog, { ...baseDialogProps, dirty: true, confirmOnClose: true })
    ;(blocked.vm as unknown as { close: () => void }).close()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(blocked.emitted('cancel')).toBeUndefined()

    confirmMock.mockResolvedValue(true)
    const allowed = await mountModal(FormDialog, { ...baseDialogProps, dirty: true, confirmOnClose: true })
    ;(allowed.vm as unknown as { close: () => void }).close()
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(allowed.emitted('cancel')).toBeTruthy()
  })

  it('权限控制：submitPerm 未注入（空集）隐藏提交', async () => {
    const wrapper = await mountModal(FormDialog, { ...baseDialogProps, submitPerm: 'user:create' })
    const labels = wrapper.findAll('.bms-modal-footer-actions button').map((button) => button.text())
    expect(labels).not.toContain('保存')
    expect(labels).toContain('取消')
  })
})

describe('FormDrawer / ConfirmDialog（迁移）', () => {
  it('FormDrawer：渲染与标题（edit）', async () => {
    const wrapper = await mountModal(FormDrawer, {
      modelValue: true,
      mode: 'edit',
      title: '用户',
      width: 'lg',
    })
    expect(wrapper.find('.bms-form-drawer').exists()).toBe(true)
    expect(wrapper.find('.bms-modal-title').text()).toBe('编辑用户')
  })

  it('ConfirmDialog：缺省标题 / 强制禁遮罩 / confirm 与 cancel 事件', async () => {
    const wrapper = await mountModal(ConfirmDialog, { modelValue: true })
    expect(wrapper.find('.bms-confirm-dialog').exists()).toBe(true)
    expect(wrapper.find('.bms-modal-title').text()).toBe('操作确认')

    const buttons = wrapper.findAll('.bms-modal-footer-actions button')
    expect(buttons.map((button) => button.text())).toContain('确定')
    await buttons.find((button) => button.text() === '取消')?.trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
    await buttons.find((button) => button.text() === '确定')?.trigger('click')
    expect(wrapper.emitted('confirm')).toBeTruthy()
  })
})
