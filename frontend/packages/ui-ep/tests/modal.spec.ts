/** 弹窗表单件用例（03_01）：三态 / 尺寸 / 脏数据拦截 / 提交。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FormDialog from '../src/components/modal/FormDialog.vue'
import FormDrawer from '../src/components/modal/FormDrawer.vue'
import { useModalShell } from '../src'

const stubs = {
  ElDialog: {
    props: ['title', 'closeOnClickModal', 'closeOnPressEscape'],
    template: '<div><span>{{ title }}</span><slot /><slot name="footer" /></div>',
  },
  ElDrawer: {
    props: ['title', 'closeOnClickModal', 'closeOnPressEscape'],
    template: '<div><span>{{ title }}</span><slot /><slot name="footer" /></div>',
  },
  ElButton: { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
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

describe('关闭规则（原型：表单类禁遮罩关闭；提交中禁关）', () => {
  it('对话框 / 抽屉向底层件传 `close-on-click-modal=false`（禁点遮罩关闭）', () => {
    expect(mountDialog({}).findComponent(stubs.ElDialog).props('closeOnClickModal')).toBe(false)

    const drawer = mount(FormDrawer, { props: { modelValue: true }, global: { stubs } })
    expect(drawer.findComponent(stubs.ElDrawer).props('closeOnClickModal')).toBe(false)
  })

  it('提交中：对话框取消按钮禁用且关闭被拦截', async () => {
    const wrapper = mountDialog({ loading: true })
    expect(wrapper.find('[data-test="form-cancel"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="form-cancel"]').trigger('click')
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).not.toContain(false)
  })

  it('提交中：抽屉关闭同口径被拦截', async () => {
    const wrapper = mount(FormDrawer, {
      props: { modelValue: true, loading: true },
      global: { stubs },
    })
    expect(wrapper.find('[data-test="drawer-cancel"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="drawer-cancel"]').trigger('click')
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).not.toContain(false)
  })

  it('提交中结束（loading 复位）：关闭恢复放行', async () => {
    const wrapper = mountDialog({ loading: true })
    await wrapper.setProps({ loading: false })
    await wrapper.find('[data-test="form-cancel"]').trigger('click')
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).toContain(false)
  })

  it('禁用底层件自行处理 Esc（`close-on-press-escape=false`，改由件内统一走拦截链）', () => {
    expect(mountDialog({}).findComponent(stubs.ElDialog).props('closeOnPressEscape')).toBe(false)

    const drawer = mount(FormDrawer, { props: { modelValue: true }, global: { stubs } })
    expect(drawer.findComponent(stubs.ElDrawer).props('closeOnPressEscape')).toBe(false)
  })

  it('Esc 走拦截链：非脏数据放行关闭', async () => {
    const wrapper = mountDialog({ dirty: false })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).toContain(false)
  })

  it('Esc 走拦截链：脏数据被拦截（不发出 update:modelValue=false）', async () => {
    const wrapper = mountDialog({ dirty: true })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    const updates = (wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])
    expect(updates).not.toContain(false)
  })

  it('Esc 走拦截链：提交中被拦截；非 Esc 键不触发关闭', async () => {
    const wrapper = mountDialog({ loading: true })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect((wrapper.emitted('update:modelValue') ?? []).map((args) => args[0])).not.toContain(false)

    const another = mountDialog({ dirty: false })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await another.vm.$nextTick()
    expect((another.emitted('update:modelValue') ?? []).map((args) => args[0])).not.toContain(false)
  })

  it('关闭后解除 Esc 订阅（再按 Esc 不产生关闭事件）', async () => {
    const wrapper = mountDialog({})
    await wrapper.setProps({ modelValue: false })
    await wrapper.vm.$nextTick()
    const before = (wrapper.emitted('update:modelValue') ?? []).length
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect((wrapper.emitted('update:modelValue') ?? []).length).toBe(before)
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
