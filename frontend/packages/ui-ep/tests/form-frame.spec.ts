/** 表单框架件用例（02_03 角色管理）：页签契约（列表固定 / 记录可关）+ 脏标记 + 关闭拦截 + 插槽分派。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { FormFrame, type FormFrameTab } from '../src'

const TABS: FormFrameTab[] = [
  { key: 'list', title: '角色列表', type: 'list' },
  { key: 'r1', title: '运维管理员', type: 'record', dirty: true },
  { key: 'r2', title: '只读角色', type: 'record' },
]

/**
 * 挂载件。
 *
 * @param props 覆盖属性。
 */
function mountFrame(props: Record<string, unknown> = {}) {
  return mount(FormFrame, {
    props: { modelValue: 'list', tabs: TABS, ...props },
    slots: { list: '<p data-test="slot-list">列表</p>', record: '<p data-test="slot-record">记录</p>' },
    global: { stubs: {} },
  })
}

describe('FormFrame（02_03）', () => {
  it('页签契约：列表页签不可关、记录页签可关；脏标记仅脏页签出现', () => {
    const wrapper = mountFrame()

    expect(wrapper.find('[data-test="form-frame-tab-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="form-frame-close-list"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="form-frame-close-r1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="form-frame-dirty-r1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="form-frame-dirty-r2"]').exists()).toBe(false)
  })

  it('激活页签：emit `update:modelValue` 与 `activate`（受控：同键不重复发）', async () => {
    const wrapper = mountFrame()

    await wrapper.find('[data-test="form-frame-tab-r1"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['r1']])
    expect(wrapper.emitted('activate')).toEqual([['r1']])

    // 受控件：父级回写激活键后再点击同键不再触发
    await wrapper.setProps({ modelValue: 'r1' })
    await wrapper.find('[data-test="form-frame-tab-r1"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['r1']])
  })

  it('内容区按激活页签类型分派插槽（列表 / 记录）', async () => {
    const wrapper = mountFrame()
    expect(wrapper.find('[data-test="slot-list"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="slot-record"]').exists()).toBe(false)

    await wrapper.setProps({ modelValue: 'r1' })
    expect(wrapper.find('[data-test="slot-record"]').exists()).toBe(true)
  })

  it('关闭页签：emit `close`；`beforeClose` 返回 false 即取消', async () => {
    const wrapper = mountFrame()
    await wrapper.find('[data-test="form-frame-close-r1"]').trigger('click')
    expect(wrapper.emitted('close')).toEqual([['r1']])

    const blocked = mountFrame({ beforeClose: () => false })
    await blocked.find('[data-test="form-frame-close-r1"]').trigger('click')
    expect(blocked.emitted('close')).toBeUndefined()
  })

  it('关闭拦截：异步回调（脏数据确认）允许后仍 emit `close`', async () => {
    const beforeClose = vi.fn(async () => true)
    const wrapper = mountFrame({ beforeClose })

    await wrapper.find('[data-test="form-frame-close-r2"]').trigger('click')
    await Promise.resolve()
    expect(beforeClose).toHaveBeenCalledWith('r2')
    expect(wrapper.emitted('close')).toEqual([['r2']])
  })

  it('新增入口：emit `open`；`openText` 为空不渲染按钮', async () => {
    const wrapper = mountFrame()
    await wrapper.find('[data-test="form-frame-open"]').trigger('click')
    expect(wrapper.emitted('open')).toEqual([[]])

    expect(mountFrame({ openText: '' }).find('[data-test="form-frame-open"]').exists()).toBe(false)
  })
})
