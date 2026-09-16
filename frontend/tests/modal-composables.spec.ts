/** 弹窗组合式用例（Kiwi 725）：useFormModal 状态机 / 脏数据 / 409 与 useConfirm。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/error'
import { useConfirm } from '@/utils/useConfirm'
import { useFormModal } from '@/utils/useFormModal'

const confirmMock = vi.hoisted(() => vi.fn())

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return { ...actual, ElMessageBox: { ...actual.ElMessageBox, confirm: confirmMock } }
})

beforeEach(() => {
  confirmMock.mockReset()
})

function makeApi() {
  return {
    create: vi.fn(async () => ({ ok: true })),
    update: vi.fn(async () => ({ ok: true })),
    detail: vi.fn(async () => ({ name: '张三', version: 3 })),
  }
}

describe('弹窗组合式（Kiwi 725）', () => {
  it('openCreate：默认值合并 / 基线 / 脏数据计算 / close', () => {
    const modal = useFormModal<Record<string, unknown>>({
      api: {},
      defaultData: () => ({ name: '' }),
    })
    modal.openCreate({ name: 'A' })
    expect(modal.visible.value).toBe(true)
    expect(modal.mode.value).toBe('create')
    expect(modal.formData.value).toEqual({ name: 'A' })
    expect(modal.dirty.value).toBe(false)

    modal.setFormData({ name: 'B' })
    expect(modal.dirty.value).toBe(true)
    modal.setFormData({ name: 'A' })
    expect(modal.dirty.value).toBe(false)

    modal.close()
    expect(modal.visible.value).toBe(false)
  })

  it('openEdit / openView：详情回填、version 记录、基线重建', async () => {
    const api = makeApi()
    const modal = useFormModal<Record<string, unknown>>({ api })
    modal.formRef.value = {
      validate: vi.fn().mockResolvedValue(undefined),
      resetFields: vi.fn(),
    } as never

    await modal.openEdit(7, '用户')
    expect(api.detail).toHaveBeenCalledWith(7)
    expect(modal.mode.value).toBe('edit')
    expect(modal.title.value).toBe('用户')
    expect(modal.formData.value).toEqual({ name: '张三', version: 3 })
    expect(modal.version.value).toBe(3)
    expect(modal.dirty.value).toBe(false)

    await modal.openView(8)
    expect(modal.mode.value).toBe('view')
    expect(modal.id.value).toBe(8)

    expect(modal.detailLoading.value).toBe(false)
    expect(modal.detailError.value).toBeNull()
  })

  it('submit：校验失败不调 API；成功后关闭并回调 onSuccess', async () => {
    const api = makeApi()
    const onSuccess = vi.fn()
    const modal = useFormModal<Record<string, unknown>>({ api, onSuccess })
    const validate = vi.fn()
    modal.formRef.value = { validate, resetFields: vi.fn() } as never

    modal.openCreate({ name: 'A' })
    validate.mockRejectedValueOnce(new Error('invalid'))
    expect(await modal.submit()).toBe(false)
    expect(api.create).not.toHaveBeenCalled()

    validate.mockResolvedValue(undefined)
    expect(await modal.submit()).toBe(true)
    expect(api.create).toHaveBeenCalledWith({ name: 'A' })
    expect(modal.visible.value).toBe(false)
    expect(onSuccess).toHaveBeenCalledWith({ ok: true }, 'create')
    expect(modal.submitLoading.value).toBe(false)
  })

  it('409 冲突：重新拉详情覆盖且保留弹窗；edit 提交携带 version', async () => {
    const api = makeApi()
    api.update = vi.fn(async () => {
      throw new ApiError({ code: 10003, httpStatus: 409 })
    })
    const modal = useFormModal<Record<string, unknown>>({ api })
    modal.formRef.value = {
      validate: vi.fn().mockResolvedValue(undefined),
      resetFields: vi.fn(),
    } as never

    await modal.openEdit(7)
    expect(api.detail).toHaveBeenCalledTimes(1)

    expect(await modal.submit()).toBe(false)
    expect(api.update).toHaveBeenCalledWith(7, { name: '张三', version: 3 }, 3)
    expect(modal.visible.value).toBe(true)
    expect(api.detail).toHaveBeenCalledTimes(2)
  })

  it('详情加载失败：禁止提交（不调 API）', async () => {
    const api = makeApi()
    api.detail = vi.fn(async () => {
      throw new ApiError({ code: 10000, httpStatus: 500 })
    })
    const modal = useFormModal<Record<string, unknown>>({ api })
    modal.formRef.value = {
      validate: vi.fn().mockResolvedValue(undefined),
      resetFields: vi.fn(),
    } as never

    await modal.openEdit(7)
    expect(modal.detailError.value).toBeInstanceOf(ApiError)
    expect(await modal.submit()).toBe(false)
    expect(api.update).not.toHaveBeenCalled()
  })

  it('useConfirm：确认 true / 取消 false；onConfirm loading 与关闭时序', async () => {
    const { confirm } = useConfirm()

    confirmMock.mockResolvedValue('confirm')
    expect(await confirm({ message: '删除后不可恢复', confirmText: '删除' })).toBe(true)
    const options = confirmMock.mock.calls[0]?.[2] as Record<string, unknown>
    expect(confirmMock.mock.calls[0]?.[1]).toBe('操作确认')
    expect(options.closeOnClickModal).toBe(false)
    expect(options.closeOnPressEscape).toBe(false)
    expect(options.confirmButtonClass).toBe('el-button--danger')

    confirmMock.mockRejectedValue('cancel')
    expect(await confirm('简单确认')).toBe(false)

    const onConfirm = vi.fn(async () => {})
    confirmMock.mockResolvedValue('confirm')
    expect(await confirm({ message: 'x', onConfirm, danger: false })).toBe(true)
    const lastOptions = confirmMock.mock.calls.at(-1)?.[2] as {
      confirmButtonClass?: string
      beforeClose: (
        action: string,
        instance: { confirmButtonLoading?: boolean },
        done: () => void,
      ) => void
    }
    expect(lastOptions.confirmButtonClass).toBeUndefined()

    const instance: { confirmButtonLoading?: boolean } = { confirmButtonLoading: false }
    let doneCalled = false
    lastOptions.beforeClose('confirm', instance, () => {
      doneCalled = true
    })
    expect(instance.confirmButtonLoading).toBe(true)
    await Promise.resolve()
    await Promise.resolve()
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(instance.confirmButtonLoading).toBe(false)
    expect(doneCalled).toBe(true)
  })
})
