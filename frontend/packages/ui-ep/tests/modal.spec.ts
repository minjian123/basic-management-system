/** 弹窗表单件用例（03_01）：三态 / 尺寸 / 脏数据拦截 / 提交。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FormDialog from '../src/components/modal/FormDialog.vue'
import FormDrawer from '../src/components/modal/FormDrawer.vue'
import { useModalShell } from '../src'

const stubs = {
  ElDialog: { props: ['title'], template: '<div><span>{{ title }}</span><slot /><slot name="footer" /></div>' },
  ElDrawer: { props: ['title'], template: '<div><span>{{ title }}</span><slot /><slot name="footer" /></div>' },
  ElButton: { template: '<button><slot /></button>' },
}

function mountDialog(props: Record<string, unknown>) {
  return mount(FormDialog, {
    props: { modelValue: true, objectName: '用户', ...props },
    global: { stubs },
  })
}

describe('FormDialog 三态', () => {
  it('标题按三态与对象名组合', () => {
    expect(mountDialog({ mode: 'create' }).text()).toContain('新增用户')
    expect(mountDialog({ mode: 'edit' }).text()).toContain('编辑用户')
    expect(mountDialog({ mode: 'detail' }).text()).toContain('用户详情')
  })

  it('详情态隐藏提交按钮', async () => {
    const detail = mountDialog({ mode: 'detail' })
    expect(detail.find('[data-test="form-submit"]').exists()).toBe(false)

    const edit = mountDialog({ mode: 'edit' })
    await edit.find('[data-test="form-submit"]').trigger('click')
    expect(edit.emitted('submit')).toHaveLength(1)
  })
})

describe('脏数据拦截', () => {
  it('脏数据时取消被拦截（不发出 update:modelValue=false）', async () => {
    const wrapper = mountDialog({ dirty: true })
    await wrapper.find('[data-test="form-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).not.toContain(false)
  })

  it('非脏数据时取消关闭', async () => {
    const wrapper = mountDialog({ dirty: false })
    await wrapper.find('[data-test="form-cancel"]').trigger('click')
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).toContain(false)
  })
})

describe('FormDrawer', () => {
  it('与 FormDialog 同契约（三态标题 + 提交）', async () => {
    const wrapper = mount(FormDrawer, {
      props: { modelValue: true, mode: 'edit', objectName: '订单' },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('编辑订单')
    await wrapper.find('[data-test="drawer-submit"]').trigger('click')
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })
})

describe('useModalShell', () => {
  it('打开 / 关闭 / 拦截', () => {
    const { visible, open, close, requestClose, setBeforeClose } = useModalShell()
    expect(visible.value).toBe(false)
    open()
    expect(visible.value).toBe(true)

    setBeforeClose(() => false)
    expect(requestClose()).toBe(false)
    expect(visible.value).toBe(true)

    setBeforeClose(undefined)
    expect(requestClose('ok')).toBe(true)
    expect(visible.value).toBe(false)

    open()
    close()
    expect(visible.value).toBe(false)
  })
})
