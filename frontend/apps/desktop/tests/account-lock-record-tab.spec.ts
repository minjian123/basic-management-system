// kiwi_id: 2277
/**
 * 账号锁定记录页（`AccountLockRecordTab`）用例（`02_02` · Kiwi 2277）：
 * 详情载入（成功 / 失败回退 / 字段缺省）/ 解锁门禁（权限码 + 未解锁）/ 解锁确认（取消 / 成功 / 失败分类提示）/
 * 解锁留痕表（解锁人 / 解锁方式）/ 刷新与关闭 / `lockId` 变化重载。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getAccountLock = vi.fn()
const unlockAccount = vi.fn()

vi.mock('@/api/accountLock', () => ({
  getAccountLock: (...args: unknown[]) => getAccountLock(...args),
  unlockAccount: (...args: unknown[]) => unlockAccount(...args),
}))

const { useSessionStore } = await import('@/stores/session')
const AccountLockRecordTab = (await import('@/views/system/user/AccountLockRecordTab.vue')).default

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver（仅需存在，行为不参与断言）。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

/** 未解锁的锁定记录（含到期时间与锁定人）。 */
const OPEN_LOCK = {
  id: '9',
  user_id: '1001',
  username: 'zhangsan',
  name: '张三',
  lock_type: 'fail_limit',
  locked_at: '2026-10-09T08:00:00',
  expire_at: '2026-10-09T09:00:00',
  locked_by: 7,
  reason: '登录失败超限',
  unlock_at: null,
  unlock_by: null,
  unlock_mode: null,
}

/** 已解锁的锁定记录（手动解锁，解锁人 / 解锁方式均有值）。 */
const DONE_LOCK = {
  ...OPEN_LOCK,
  expire_at: null,
  locked_by: null,
  reason: null,
  unlock_at: '2026-10-10T01:02:03',
  unlock_by: 9,
  unlock_mode: 'manual',
}

/** 用例内共享的 pinia 实例。 */
let pinia: ReturnType<typeof createPinia>

/**
 * 挂载锁定记录页。
 *
 * @param lockId 锁定记录主键。
 * @returns 挂载结果。
 */
async function mountTab(lockId = '9'): Promise<ReturnType<typeof mount>> {
  const wrapper = mount(AccountLockRecordTab, { props: { lockId }, global: { plugins: [pinia] } })
  await flushPromises()
  return wrapper
}

/** 取只读表单内第 n 个输入框的值。 */
function inputValue(wrapper: ReturnType<typeof mount>, index: number): string {
  return (wrapper.findAll('.el-form-item input')[index]!.element as HTMLInputElement).value
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  getAccountLock.mockReset()
  unlockAccount.mockReset()
  getAccountLock.mockResolvedValue({ ...OPEN_LOCK })
  unlockAccount.mockResolvedValue({ ...DONE_LOCK })
  useSessionStore().codes = ['user:unlock']
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
})

describe('账号锁定记录页（02_02）', () => {
  it('详情载入：回填只读表单、展示解锁按钮并给出未解锁提示与空留痕表', async () => {
    const wrapper = await mountTab()

    expect(getAccountLock).toHaveBeenCalledWith('9')
    expect(inputValue(wrapper, 0)).toBe('张三')
    expect(inputValue(wrapper, 1)).toBe('zhangsan')
    expect(inputValue(wrapper, 2)).toBe('2026-10-09 08:00:00')
    // 到期时间有值：按格式化展示（非「须手动解锁」回退）
    expect(inputValue(wrapper, 3)).toBe('2026-10-09 09:00:00')
    expect(inputValue(wrapper, 4)).toBe('7')
    expect(wrapper.find('[data-test="lock-record-form"]').text()).toContain('登录失败超限')

    expect(wrapper.find('[data-test="lock-record-unlock"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('本锁定记录尚未解锁')
    expect(wrapper.findAll('.el-table__row')).toHaveLength(0)
  })

  it('详情字段缺省：姓名 / 用户名 / 到期时间 / 锁定人 / 原因逐项回退默认值', async () => {
    getAccountLock.mockResolvedValue({
      id: '9',
      lock_type: 'manual',
      locked_at: '2026-10-09T08:00:00',
      unlock_at: null,
    })
    const wrapper = await mountTab()

    expect(inputValue(wrapper, 0)).toBe('—')
    expect(inputValue(wrapper, 1)).toBe('—')
    // 到期时间缺省（null / undefined）→ 回退「须手动解锁」文案
    expect(inputValue(wrapper, 3)).toBe('—（须手动解锁）')
    expect(inputValue(wrapper, 4)).toBe('—（系统触发）')
    expect(wrapper.find('textarea').element.value).toBe('—')
  })

  it('详情载入失败：按 Error / 非 Error 分别提示，锁定为空时不渲染解锁按钮', async () => {
    getAccountLock.mockRejectedValueOnce(new Error('锁定记录不存在'))
    const failed = await mountTab()
    expect(ElMessage.error).toHaveBeenCalledWith('锁定记录不存在')
    // 锁定为空：只读表单回退占位、无解锁按钮、不渲染已解锁提示
    expect(inputValue(failed, 0)).toBe('—')
    expect(failed.find('[data-test="lock-record-unlock"]').exists()).toBe(false)
    expect(failed.text()).toContain('本锁定记录尚未解锁')

    // 锁定为空时解锁入口短路（直接调用处理函数覆盖 `item === null` 分支）
    const state = (failed.vm as unknown as { $: { setupState: Record<string, () => Promise<void>> } }).$.setupState
    await state.unlock!()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()

    getAccountLock.mockRejectedValueOnce('boom')
    await mountTab()
    expect(ElMessage.error).toHaveBeenCalledWith('锁定记录加载失败')
  })

  it('权限缺省：不渲染解锁按钮（记录仍未解锁）', async () => {
    useSessionStore().codes = []
    const wrapper = await mountTab()

    expect(wrapper.find('[data-test="lock-record-unlock"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('本锁定记录尚未解锁')
  })

  it('已解锁记录：不渲染解锁按钮，展示解锁摘要（解锁人 / 解锁方式 / 时间）与留痕行', async () => {
    getAccountLock.mockResolvedValue({ ...DONE_LOCK })
    const wrapper = await mountTab()

    expect(wrapper.find('[data-test="lock-record-unlock"]').exists()).toBe(false)
    const alert = wrapper.find('.el-alert')
    expect(alert.text()).toContain('账号已解锁（解锁人：9')
    expect(alert.text()).toContain('2026-10-10 01:02:03')
    expect(alert.text()).toContain('手动解锁')

    expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
    expect(wrapper.find('.el-table__row').text()).toContain('9')
  })

  it('已解锁记录：解锁人与解锁方式缺省时回落「系统 / —」；自动解锁按文案映射', async () => {
    getAccountLock.mockResolvedValue({ ...DONE_LOCK, unlock_by: null, unlock_mode: null })
    const wrapper = await mountTab()
    expect(wrapper.find('.el-alert').text()).toContain('解锁人：系统')
    expect(wrapper.find('.el-alert').text()).toContain('—')
    expect(wrapper.find('.el-table__row').text()).toContain('系统')

    getAccountLock.mockResolvedValue({ ...DONE_LOCK, unlock_by: null, unlock_mode: 'auto' })
    const auto = await mountTab()
    expect(auto.find('.el-alert').text()).toContain('自动解锁')
  })

  it('解锁：确认后调用解锁端点、更新为已解锁并提示成功', async () => {
    const wrapper = await mountTab()

    await wrapper.find('[data-test="lock-record-unlock"]').trigger('click')
    await flushPromises()

    expect(unlockAccount).toHaveBeenCalledWith('9')
    expect(ElMessage.success).toHaveBeenCalledWith('已解锁')
    expect(wrapper.text()).toContain('账号已解锁')
    expect(wrapper.findAll('.el-table__row')).toHaveLength(1)
  })

  it('解锁：取消确认时不调用解锁端点', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    const wrapper = await mountTab()

    await wrapper.find('[data-test="lock-record-unlock"]').trigger('click')
    await flushPromises()

    expect(unlockAccount).not.toHaveBeenCalled()
    expect(ElMessage.success).not.toHaveBeenCalled()
  })

  it('解锁失败：按 Error / 非 Error 分别提示', async () => {
    const wrapper = await mountTab()

    unlockAccount.mockRejectedValueOnce(new Error('锁定记录已解锁'))
    await wrapper.find('[data-test="lock-record-unlock"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('锁定记录已解锁')

    unlockAccount.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="lock-record-unlock"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('解锁失败')
  })

  it('刷新：重新载入详情；载入中展示提示', async () => {
    let resolveLoad: (value: unknown) => void = () => undefined
    getAccountLock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveLoad = resolve
        }),
    )
    const wrapper = mount(AccountLockRecordTab, { props: { lockId: '9' }, global: { plugins: [pinia] } })
    await flushPromises()
    expect(wrapper.find('[data-test="lock-record-loading"]').exists()).toBe(true)

    resolveLoad({ ...OPEN_LOCK })
    await flushPromises()
    expect(wrapper.find('[data-test="lock-record-loading"]').exists()).toBe(false)

    await wrapper.find('[data-test="lock-record-refresh"]').trigger('click')
    await flushPromises()
    expect(getAccountLock).toHaveBeenCalledTimes(2)
  })

  it('关闭：点击关闭按钮上抛 close', async () => {
    const wrapper = await mountTab()

    await wrapper.find('[data-test="lock-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('lockId 变化：重新载入详情', async () => {
    const wrapper = await mountTab()

    await wrapper.setProps({ lockId: '10' })
    await flushPromises()

    expect(getAccountLock).toHaveBeenLastCalledWith('10')
  })

  it('解锁方式未知值：文案回落「—」', async () => {
    getAccountLock.mockResolvedValue({ ...DONE_LOCK, unlock_mode: 'unknown' })
    const wrapper = await mountTab()
    const logs = wrapper.find('[data-test="lock-record-logs"]')
    expect(logs.text()).toContain('—')
  })
})
