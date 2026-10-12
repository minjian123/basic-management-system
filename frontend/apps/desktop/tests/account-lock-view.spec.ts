// kiwi_id: 2277
/**
 * 账号锁定页（`AccountLockView`）用例（`02_02` · Kiwi 2277）：
 * 列表装载（三态行渲染 / 已解锁行不可选）/ 筛选与检索（解锁状态 → `active` 映射）/ 重置与回车 / 载入失败与缺省 /
 * 载入中提示 / 双击开记录页签（标题回落）与关闭 / 手动锁定（候选载入、两项校验、成功、失败）/ 批量解锁（空选、取消、
 * 成功、部分失败、全部失败）/ 权限缺省 / 分页。
 *
 * 说明：对话框与分页用桩件承接（透传插槽）；表格用**真实** `el-table`（jsdom 下需 `ResizeObserver` 垫片），
 * 「已解锁行不可选」经勾选框禁用态断言 `rowSelectable` 两分支。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

const listAccountLocks = vi.fn()
const getAccountLock = vi.fn()
const lockAccount = vi.fn()
const unlockAccount = vi.fn()
const listUsers = vi.fn()

vi.mock('@/api/accountLock', () => ({
  listAccountLocks: (...args: unknown[]) => listAccountLocks(...args),
  getAccountLock: (...args: unknown[]) => getAccountLock(...args),
  lockAccount: (...args: unknown[]) => lockAccount(...args),
  unlockAccount: (...args: unknown[]) => unlockAccount(...args),
}))

vi.mock('@/api/user', () => ({ listUsers: (...args: unknown[]) => listUsers(...args) }))

// 文件级放宽超时：本文件用**真实** `el-table` 渲染、用例偏重，CI 机器较慢（实测单例 ~5.4s 撞默认 5s 超时）；
// 仅本文件放宽到 15s，其余用例仍保持默认 5s 的快速失败。
vi.setConfig({ testTimeout: 15000 })

const { useSessionStore } = await import('@/stores/session')
const { useTabsStore } = await import('@/stores/tabs')
const AccountLockView = (await import('@/views/system/user/AccountLockView.vue')).default

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver（仅需存在，行为不参与断言）。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

/** 装饰性 EP 件桩：对话框透传插槽（内容常驻，供用例直接操作），分页仅承接事件。 */
const stubs = {
  ElPagination: defineComponent({ name: 'ElPagination', template: '<div />' }),
  ElDialog: defineComponent({
    name: 'ElDialog',
    props: { modelValue: { type: Boolean, default: false } },
    template: '<div><slot /><slot name="footer" /></div>',
  }),
}

/** 未解锁的锁定记录（登录失败超限，含到期时间与锁定人）。 */
const OPEN_ROW = {
  id: '1',
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

/** 未解锁的锁定记录（长期未登录，无到期时间）。 */
const OPEN_ROW2 = { ...OPEN_ROW, id: '4', user_id: '1004', username: 'wangwu', name: '王五', lock_type: 'inactive' }

/** 已解锁的锁定记录（手动解锁，解锁人为具体操作者）。 */
const DONE_ROW = {
  ...OPEN_ROW,
  id: '2',
  user_id: '1002',
  username: 'lisi',
  name: '李四',
  lock_type: 'manual',
  expire_at: null,
  unlock_at: '2026-10-10T01:02:03',
  unlock_by: 9,
  unlock_mode: 'manual',
}

/** 已解锁的锁定记录（解锁人缺省 → 系统）。 */
const SYS_ROW = {
  ...DONE_ROW,
  id: '3',
  user_id: '1003',
  username: '',
  name: '赵六',
  unlock_by: null,
  unlock_mode: null,
}

/** 列表页桩响应。 */
const PAGE = { list: [OPEN_ROW, OPEN_ROW2, DONE_ROW, SYS_ROW], total: 4, page: 1, size: 20 }

/** 候选用户桩数据。 */
const CANDIDATES = [{ id: '1001', username: 'zhangsan', name: '张三' }]

/** 用例内共享的 pinia 实例。 */
let pinia: ReturnType<typeof createPinia>

/** 组件 `setup` 暴露面（`script setup` 仅测试内可达）。 */
type SetupState = Record<string, unknown>

/**
 * 取组件 `setup` 暴露面。
 *
 * @param wrapper 挂载结果。
 * @returns 暴露面。
 */
function setup(wrapper: ReturnType<typeof mount>): SetupState {
  return (wrapper.vm as unknown as { $: { setupState: SetupState } }).$.setupState
}

/** 取第 n 个 `el-select`（0 锁定类型筛选、1 解锁状态筛选、2 弹窗用户）。 */
function selectAt(wrapper: ReturnType<typeof mount>, index: number): ReturnType<typeof mount>['vm'] {
  return wrapper.findAllComponents({ name: 'ElSelect' })[index]!.vm
}

/** 打开弹窗并填好用户与原因（候选用户载入走默认 mock）。 */
async function fillLockForm(wrapper: ReturnType<typeof mount>, reason: string): Promise<void> {
  await wrapper.find('[data-test="lock-manual"]').trigger('click')
  await flushPromises()
  selectAt(wrapper, 2).$emit('update:modelValue', '1001')
  await nextTick()
  await wrapper.find('[data-test="lock-dialog-reason"]').setValue(reason)
}

/** 挂载账号锁定页。 */
async function mountView(): Promise<ReturnType<typeof mount>> {
  const wrapper = mount(AccountLockView, { global: { plugins: [pinia], stubs } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  for (const mock of [listAccountLocks, getAccountLock, lockAccount, unlockAccount, listUsers]) {
    mock.mockReset()
  }
  listAccountLocks.mockResolvedValue({ ...PAGE })
  getAccountLock.mockResolvedValue({ ...OPEN_ROW })
  lockAccount.mockResolvedValue({ ...OPEN_ROW })
  unlockAccount.mockResolvedValue({ ...DONE_ROW })
  listUsers.mockResolvedValue({ list: CANDIDATES })
  useSessionStore().codes = ['user:lock', 'user:unlock']
  vi.spyOn(ElMessage, 'success')
    .mockClear()
    .mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error')
    .mockClear()
    .mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockClear().mockResolvedValue('confirm')
})

describe('账号锁定页（02_02）', () => {
  it('列表装载：三段式（工具栏 / 筛选 / 表格）与锁定 / 解锁两态渲染（已解锁行不可选）', async () => {
    const wrapper = await mountView()

    expect(listAccountLocks).toHaveBeenCalledWith({
      kw: undefined,
      lock_type: undefined,
      active: undefined,
      page: 1,
      size: 20,
    })
    expect(wrapper.find('[data-test="account-lock-view"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="lock-manual"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="lock-refresh"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="lock-close-page"]').exists()).toBe(true)
    // 空选时「解锁」按钮为禁用态
    expect(wrapper.find('[data-test="lock-batch-unlock"]').attributes('disabled')).toBeDefined()

    const rows = wrapper.findAll('.el-table__row')
    expect(rows).toHaveLength(4)
    expect(rows[0]!.text()).toContain('zhangsan')
    expect(rows[0]!.text()).toContain('张三')
    expect(rows[0]!.text()).toContain('登录失败超限')
    expect(rows[0]!.text()).toContain('2026-10-09 08:00:00')
    expect(rows[0]!.text()).toContain('2026-10-09 09:00:00')
    expect(rows[0]!.text()).toContain('未解锁')
    expect(rows[2]!.text()).toContain('已解锁（9）')
    expect(rows[3]!.text()).toContain('已解锁（系统）')
    expect(rows[3]!.text()).toContain('—（须手动解锁）')

    // 「已解锁行不可选」：仅未解锁行的勾选框可用
    expect(rows[0]!.find('.el-checkbox').classes()).not.toContain('is-disabled')
    expect(rows[1]!.find('.el-checkbox').classes()).not.toContain('is-disabled')
    expect(rows[2]!.find('.el-checkbox').classes()).toContain('is-disabled')
    expect(rows[3]!.find('.el-checkbox').classes()).toContain('is-disabled')
  })

  it('检索：关键字与两段筛选带上，解锁状态映射为 active 参数（含空值不传）', async () => {
    const wrapper = await mountView()

    await wrapper.find('[data-test="lock-kw"]').setValue('zhang')
    selectAt(wrapper, 0).$emit('update:modelValue', 'manual')
    selectAt(wrapper, 1).$emit('update:modelValue', 'open')
    await nextTick()
    await wrapper.find('[data-test="lock-search"]').trigger('click')
    await flushPromises()
    expect(listAccountLocks).toHaveBeenLastCalledWith({
      kw: 'zhang',
      lock_type: 'manual',
      active: true,
      page: 1,
      size: 20,
    })

    // 「已解锁（含已到期）」→ active=false
    selectAt(wrapper, 1).$emit('update:modelValue', 'done')
    await nextTick()
    await wrapper.find('[data-test="lock-search"]').trigger('click')
    await flushPromises()
    expect(listAccountLocks).toHaveBeenLastCalledWith({
      kw: 'zhang',
      lock_type: 'manual',
      active: false,
      page: 1,
      size: 20,
    })

    // 未选解锁状态 → active 不传
    selectAt(wrapper, 1).$emit('update:modelValue', '')
    await nextTick()
    await wrapper.find('[data-test="lock-search"]').trigger('click')
    await flushPromises()
    expect(listAccountLocks).toHaveBeenLastCalledWith({
      kw: 'zhang',
      lock_type: 'manual',
      active: undefined,
      page: 1,
      size: 20,
    })
  })

  it('回车检索与重置：回车触发查询；重置清空三段筛选并回第一页', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="lock-kw"]').setValue('li')
    selectAt(wrapper, 0).$emit('update:modelValue', 'inactive')
    selectAt(wrapper, 1).$emit('update:modelValue', 'done')
    await nextTick()

    await wrapper.find('[data-test="lock-kw"]').trigger('keyup.enter')
    await flushPromises()
    expect(listAccountLocks).toHaveBeenLastCalledWith({
      kw: 'li',
      lock_type: 'inactive',
      active: false,
      page: 1,
      size: 20,
    })

    await wrapper.find('[data-test="lock-reset"]').trigger('click')
    await flushPromises()
    expect(listAccountLocks).toHaveBeenLastCalledWith({
      kw: undefined,
      lock_type: undefined,
      active: undefined,
      page: 1,
      size: 20,
    })
    expect((wrapper.find('[data-test="lock-kw"]').element as HTMLInputElement).value).toBe('')
  })

  it('列表载入失败：按 Error / 非 Error 分别提示；响应缺省按空集与 0 处理并渲染空态', async () => {
    listAccountLocks.mockRejectedValueOnce(new Error('锁定服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('锁定服务不可用')

    listAccountLocks.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('锁定记录加载失败')

    listAccountLocks.mockResolvedValueOnce({})
    const wrapper = await mountView()
    expect(wrapper.findAll('.el-table__row')).toHaveLength(0)
    expect(wrapper.text()).toContain('暂无锁定记录')
  })

  it('载入中：工具栏展示「载入中…」提示，载入完成后隐藏', async () => {
    let resolveLoad: (value: unknown) => void = () => undefined
    listAccountLocks.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveLoad = resolve
        }),
    )
    const wrapper = mount(AccountLockView, { global: { plugins: [pinia], stubs } })
    await nextTick()
    expect(wrapper.find('.lock-view__hint').exists()).toBe(true)

    resolveLoad({ ...PAGE })
    await flushPromises()
    expect(wrapper.find('.lock-view__hint').exists()).toBe(false)
  })

  it('刷新：重新载入列表', async () => {
    const wrapper = await mountView()

    await wrapper.find('[data-test="lock-refresh"]').trigger('click')
    await flushPromises()

    expect(listAccountLocks).toHaveBeenCalledTimes(2)
  })

  it('双击行：打开记录页签、渲染记录页（锁定主键透传），关闭后回到列表页签', async () => {
    const wrapper = await mountView()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabs.map((tab) => tab.key)).toEqual(['list', 'record:1'])
    expect(tabs.tabOf('record:1')?.title).toBe('zhangsan')
    expect(tabs.active).toBe('record:1')
    const record = wrapper.findComponent({ name: 'AccountLockRecordTab' })
    expect(record.props('lockId')).toBe('1')
    expect(getAccountLock).toHaveBeenCalledWith('1')

    await wrapper.find('[data-test="lock-record-close"]').trigger('click')
    await flushPromises()
    expect(tabs.tabs.map((tab) => tab.key)).toEqual(['list'])
    expect(tabs.active).toBe('list')
  })

  it('双击行：用户名缺省时记录页签标题回落用户主键', async () => {
    const wrapper = await mountView()

    await wrapper.findAll('.el-table__row')[3]!.trigger('dblclick')
    await flushPromises()

    expect(useTabsStore().tabOf('record:3')?.title).toBe('1003')
  })

  it('记录插槽：激活页签不在清单内（tab 为空）时不渲染记录页', async () => {
    const wrapper = await mountView()
    useTabsStore().active = 'ghost'
    await nextTick()

    expect(wrapper.find('[data-test="account-lock-record"]').exists()).toBe(false)
  })

  it('页签交互：点击列表页签切回列表；记录页签经关闭拦截后关闭', async () => {
    const wrapper = await mountView()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(useTabsStore().active).toBe('record:1')

    await wrapper.find('[data-test="form-frame-tab-list"]').trigger('click')
    await flushPromises()
    expect(useTabsStore().active).toBe('list')

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(useTabsStore().tabs.map((tab) => tab.key)).toEqual(['list'])
  })

  it('关闭按钮：重置为仅列表页签', async () => {
    const wrapper = await mountView()
    useTabsStore().active = 'ghost'

    await wrapper.find('[data-test="lock-close-page"]').trigger('click')

    expect(useTabsStore().tabs.map((tab) => tab.key)).toEqual(['list'])
    expect(useTabsStore().active).toBe('list')
  })

  it('分页：翻页携带新页码重新载入', async () => {
    const wrapper = await mountView()
    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    pagination.vm.$emit('update:currentPage', 3)
    await nextTick()
    pagination.vm.$emit('current-change', 3)
    await flushPromises()

    expect(listAccountLocks).toHaveBeenLastCalledWith({
      kw: undefined,
      lock_type: undefined,
      active: undefined,
      page: 3,
      size: 20,
    })
  })

  it('手动锁定：打开弹窗载入候选用户；载入失败静默降级为空集', async () => {
    const wrapper = await mountView()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)

    await wrapper.find('[data-test="lock-manual"]').trigger('click')
    await flushPromises()
    expect(listUsers).toHaveBeenCalledWith({ status: 'enabled', size: 50 })
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(true)
    expect(setup(wrapper).candidates).toHaveLength(1)

    // 弹窗自身关闭（遮罩 / ESC）经 `v-model` 回写
    wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('update:modelValue', false)
    await nextTick()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)

    // 取消按钮直接关闭弹窗
    await wrapper.find('[data-test="lock-dialog-cancel"]').trigger('click')
    await nextTick()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)

    listUsers.mockRejectedValueOnce(new Error('用户服务不可用'))
    await wrapper.find('[data-test="lock-manual"]').trigger('click')
    await flushPromises()
    expect(setup(wrapper).candidates).toHaveLength(0)
  })

  it('手动锁定：候选用户响应缺省（无 list）与姓名 / 账号缺省时逐项回落', async () => {
    listUsers.mockResolvedValueOnce({})
    const wrapper = await mountView()

    await wrapper.find('[data-test="lock-manual"]').trigger('click')
    await flushPromises()
    // `data.list ?? []` 回退分支
    expect(setup(wrapper).candidates).toHaveLength(0)

    listUsers.mockResolvedValueOnce({ list: [{ id: '2002' }] })
    await wrapper.find('[data-test="lock-manual"]').trigger('click')
    await flushPromises()
    // 选项文案的 `item.name ?? ''` / `item.username ?? ''` 回退分支
    expect(wrapper.findAllComponents({ name: 'ElOption' }).at(-1)!.props('label')).toBe('（）')
  })

  it('手动锁定：未选用户 / 未填原因（含纯空白）逐项拦截', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="lock-manual"]').trigger('click')
    await flushPromises()

    await wrapper.find('[data-test="lock-dialog-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('请选择用户')
    expect(lockAccount).not.toHaveBeenCalled()

    selectAt(wrapper, 2).$emit('update:modelValue', '1001')
    await nextTick()
    await wrapper.find('[data-test="lock-dialog-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('请填写锁定原因')

    await wrapper.find('[data-test="lock-dialog-reason"]').setValue('   ')
    await wrapper.find('[data-test="lock-dialog-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('请填写锁定原因')
    expect(lockAccount).not.toHaveBeenCalled()
  })

  it('手动锁定：提交成功关闭弹窗、提示并刷新列表', async () => {
    const wrapper = await mountView()
    await fillLockForm(wrapper, '连续违规')

    await wrapper.find('[data-test="lock-dialog-confirm"]').trigger('click')
    await flushPromises()

    expect(lockAccount).toHaveBeenCalledWith({ user_id: '1001', reason: '连续违规' })
    expect(ElMessage.success).toHaveBeenCalledWith('已手动锁定（无期限，须手动解锁）')
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
    expect(listAccountLocks).toHaveBeenCalledTimes(2)
  })

  it('手动锁定失败：按 Error / 非 Error 分别提示（弹窗保持打开）', async () => {
    const wrapper = await mountView()
    await fillLockForm(wrapper, '连续违规')

    lockAccount.mockRejectedValueOnce(new Error('该用户已锁定'))
    await wrapper.find('[data-test="lock-dialog-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('该用户已锁定')

    lockAccount.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="lock-dialog-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('锁定失败')
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(true)
  })

  it('批量解锁：空选（或仅选中已解锁行）时短路提示', async () => {
    const wrapper = await mountView()

    // 空选时按钮为禁用态（原生 disabled 不派发 click）：直接调用处理函数覆盖短路分支
    await (setup(wrapper).batchUnlock as () => Promise<void>)()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('请选择未解锁的锁定记录')
    expect(unlockAccount).not.toHaveBeenCalled()

    // 仅选中已解锁行：过滤后目标为空，同样短路
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [DONE_ROW])
    await nextTick()
    await wrapper.find('[data-test="lock-batch-unlock"]').trigger('click')
    await flushPromises()
    expect(unlockAccount).not.toHaveBeenCalled()
  })

  it('批量解锁：取消确认时不调用解锁端点', async () => {
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [OPEN_ROW])
    await nextTick()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')

    await wrapper.find('[data-test="lock-batch-unlock"]').trigger('click')
    await flushPromises()

    expect(unlockAccount).not.toHaveBeenCalled()
    expect(listAccountLocks).toHaveBeenCalledTimes(1)
  })

  it('批量解锁：确认后逐条解锁、清空多选并刷新列表', async () => {
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [OPEN_ROW])
    await nextTick()

    await wrapper.find('[data-test="lock-batch-unlock"]').trigger('click')
    await flushPromises()

    expect(unlockAccount).toHaveBeenCalledWith('1')
    expect(ElMessage.success).toHaveBeenCalledWith('已解锁 1 个账号')
    expect(listAccountLocks).toHaveBeenCalledTimes(2)
    // 解锁后清空多选：按钮回到禁用态
    expect(wrapper.find('[data-test="lock-batch-unlock"]').attributes('disabled')).toBeDefined()
  })

  it('批量解锁：部分失败时逐条提示错误并汇总已成功数', async () => {
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [OPEN_ROW, OPEN_ROW2])
    await nextTick()
    unlockAccount.mockResolvedValueOnce({ ...DONE_ROW }).mockRejectedValueOnce(new Error('锁定记录已解锁'))

    await wrapper.find('[data-test="lock-batch-unlock"]').trigger('click')
    await flushPromises()

    expect(unlockAccount).toHaveBeenCalledTimes(2)
    expect(ElMessage.error).toHaveBeenCalledWith('锁定记录已解锁')
    expect(ElMessage.success).toHaveBeenCalledWith('已解锁 1 个账号')
    expect(listAccountLocks).toHaveBeenCalledTimes(2)
  })

  it('批量解锁：全部失败时仅提示错误（不汇总成功、不刷新列表）', async () => {
    const wrapper = await mountView()
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [OPEN_ROW, OPEN_ROW2])
    await nextTick()
    unlockAccount.mockRejectedValue('boom')

    await wrapper.find('[data-test="lock-batch-unlock"]').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('解锁失败')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(listAccountLocks).toHaveBeenCalledTimes(1)
  })

  it('权限缺省：隐藏「手动锁定」与「解锁」按钮（刷新 / 关闭保留）', async () => {
    useSessionStore().codes = []
    const wrapper = await mountView()

    expect(wrapper.find('[data-test="lock-manual"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="lock-batch-unlock"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="lock-refresh"]').exists()).toBe(true)
  })
})
