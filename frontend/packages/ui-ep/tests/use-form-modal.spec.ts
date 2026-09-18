/** 弹窗表单组合式用例（03_01）。 */

import { describe, expect, it, vi } from 'vitest'

import { useFormModal } from '../src'

describe('useFormModal', () => {
  it('打开 / 标题 / 脏数据 / 关闭', () => {
    const modal = useFormModal()
    expect(modal.visible.value).toBe(false)

    modal.open('edit', '编辑用户')
    expect(modal.visible.value).toBe(true)
    expect(modal.mode.value).toBe('edit')
    expect(modal.title.value).toBe('编辑用户')
    expect(modal.dirty.value).toBe(false)

    modal.markDirty()
    expect(modal.dirty.value).toBe(true)
    modal.reset()
    expect(modal.dirty.value).toBe(false)

    modal.close()
    expect(modal.visible.value).toBe(false)
  })

  it('提交：加载态切换 + 清脏', async () => {
    const submit = vi.fn(async () => {})
    const modal = useFormModal<{ name: string }>({ submit })
    modal.open()
    modal.markDirty()

    expect(modal.loading.value).toBe(false)
    const pending = modal.submit({ name: 'a' })
    expect(modal.loading.value).toBe(true)
    await pending
    expect(modal.loading.value).toBe(false)
    expect(submit).toHaveBeenCalledWith({ name: 'a' })
    expect(modal.dirty.value).toBe(false)
  })
})
