// kiwi_id: 2277
/**
 * 用户管理页用例（02_02 · Kiwi 2277）：列表装载与三段式（工具栏 / 筛选 / 表格）/ 按权限显隐 /
 * 检索与分页 / 双击行开记录页签 / 新增 / 批量删除与批量启停（含失败汇总与空选短路）/
 * 状态内联切换（停用二次确认、启用直存、取消回滚）/ 重置密码弹窗（单行限制 / 空密码 / 成功与失败）/
 * 记录页签关闭（脏数据拦截）/ 记录保存回调与脏态同步。
 */

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'

import { deleteUser, listUsers, resetUserPassword, updateUserStatus } from '@/api/user'
import { useSessionStore } from '@/stores/session'
import { useTabsStore } from '@/stores/tabs'
import UserView from '@/views/system/user/UserView.vue'

vi.mock('@/api/user', () => ({
  listUsers: vi.fn(),
  deleteUser: vi.fn(),
  resetUserPassword: vi.fn(),
  updateUserStatus: vi.fn(),
  getUser: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  applyUserAssignments: vi.fn(),
  listUserRoles: vi.fn(),
  listUserIdentities: vi.fn(),
}))

const listMock = vi.mocked(listUsers)
const deleteMock = vi.mocked(deleteUser)
const resetPwdMock = vi.mocked(resetUserPassword)
const updateStatusMock = vi.mocked(updateUserStatus)

/** 用户列表桩数据（一启用一停用）。 */
const PAGE = {
  list: [
    { id: '1', username: 'zhangsan', name: '张三', status: 'enabled', last_login_at: '2026-10-01T08:00:00Z' },
    { id: '2', username: 'lisi', name: '李四', status: 'disabled', last_login_at: '2026-10-02T09:00:00Z' },
  ],
  total: 2,
  page: 1,
  size: 20,
}

/** 用户记录页桩：仅承接宿主事件（记录页自身契约由 `user-record-tab.spec.ts` 覆盖）。 */
const UserRecordTabStub = defineComponent({
  name: 'UserRecordTab',
  props: { userId: { type: String, default: '' } },
  emits: ['saved', 'dirty', 'close'],
  template: '<div class="user-record-tab-stub" />',
})

/** 装饰性 EP 件桩（对话框 / 分页透传插槽；表格用**真实** `el-table` 件，jsdom 下需 ResizeObserver）。 */
const stubs = {
  ElDialog: defineComponent({
    name: 'ElDialog',
    props: { modelValue: { type: Boolean, default: false }, title: { type: String, default: '' } },
    template: '<div><slot /><slot name="footer" /></div>',
  }),
  ElPagination: defineComponent({ name: 'ElPagination', template: '<div />' }),
  // 桩件渲染原生 `button`：禁用态据此原样透传，便于断言与真实点击语义
  ElButton: defineComponent({
    name: 'ElButton',
    props: { disabled: { type: Boolean, default: false } },
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  }),
  UserRecordTab: UserRecordTabStub,
}

/** `flushPromises` 之后的额外一拍（嵌套 promise 链对齐）。 */
const settle = (): Promise<void> => nextTick().then(() => flushPromises())

/**
 * 挂载用户管理页。
 *
 * @param codes 会话权限码。
 * @returns 挂载结果。
 */
async function mountView(codes: string[] = []): Promise<{ wrapper: VueWrapper; pinia: Pinia }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  useSessionStore(pinia).setCodes(codes)
  const wrapper = mount(UserView, { global: { plugins: [pinia], stubs } })
  await flushPromises()
  return { wrapper, pinia }
}

/**
 * 行内状态开关（`InlineSwitchCell` 内的 `TriStateSwitch`，宿主切换经其 `update:modelValue` 触发）。
 *
 * 迁移说明（11_03）：三态承载由 Element Plus `el-switch` 改自绘 `TriStateSwitch`
 * （EP 2.14.7 无 `indeterminate`，无法呈现「未设置」态）。
 */
function switchOf(wrapper: VueWrapper, index = 0) {
  return wrapper.findAllComponents({ name: 'InlineSwitchCell' })[index]!.findComponent({ name: 'TriStateSwitch' })
}

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver（仅需存在，行为不参与断言）。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

beforeEach(() => {
  listMock.mockReset()
  deleteMock.mockReset()
  resetPwdMock.mockReset()
  updateStatusMock.mockReset()
  listMock.mockResolvedValue(PAGE)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('UserView（02_02）', () => {
  it('列表装载：三段式（工具栏 / 筛选 / 表格）与状态列内联开关', async () => {
    const { wrapper } = await mountView(['user:create', 'user:delete', 'user:reset_pwd'])

    expect(listMock).toHaveBeenCalledWith({ kw: undefined, status: undefined, page: 1, size: 20 })
    expect(wrapper.find('[data-test="user-create"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-refresh"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-kw"]').exists()).toBe(true)

    const rows = wrapper.findAll('.el-table__row')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('zhangsan')
    expect(rows[0]!.text()).toContain('张三')
    expect(rows[1]!.text()).toContain('lisi')
    // 状态列：启用 / 停用各一行内联开关
    expect(wrapper.findAllComponents({ name: 'InlineSwitchCell' })).toHaveLength(2)
  })

  it('按权限显隐：无权限时不渲染新增 / 删除 / 重置密码按钮', async () => {
    const { wrapper } = await mountView()

    expect(wrapper.find('[data-test="user-create"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="user-batch-delete"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="user-reset-pwd"]').exists()).toBe(false)
  })

  it('载入中提示：请求未落地时呈现「载入中…」', async () => {
    let release: (value: typeof PAGE) => void = () => undefined
    listMock.mockImplementation(
      () =>
        new Promise((resolve) => {
          release = resolve
        }),
    )
    const { wrapper } = await mountView()

    expect(wrapper.find('.user-view__hint').text()).toBe('载入中…')
    release(PAGE)
    await flushPromises()
    expect(wrapper.find('.user-view__hint').exists()).toBe(false)
  })

  it('列表载入失败：按 Error / 非 Error 分别提示', async () => {
    listMock.mockRejectedValueOnce(new Error('用户服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('用户服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('用户列表加载失败')
  })

  it('列表缺省：`list` / `total` 缺失按空集与 0 处理', async () => {
    listMock.mockResolvedValue({})
    const { wrapper } = await mountView()

    expect(wrapper.findAll('.el-table__row')).toHaveLength(0)
    expect(wrapper.find('[data-test="user-table"]').exists()).toBe(true)
  })

  it('检索：关键字与状态带上（空值不传），并回第一页', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('[data-test="user-kw"]').setValue('zhang')
    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'enabled')
    await nextTick()
    await wrapper.find('[data-test="user-search"]').trigger('click')
    await flushPromises()

    expect(listMock).toHaveBeenLastCalledWith({ kw: 'zhang', status: 'enabled', page: 1, size: 20 })
  })

  it('检索：关键字回车触发查询', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('[data-test="user-kw"]').trigger('keyup.enter')
    await flushPromises()

    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('分页：翻页触发重新载入（页码带入查询）', async () => {
    const { wrapper } = await mountView()
    const pagination = wrapper.findComponent({ name: 'ElPagination' })
    pagination.vm.$emit('update:currentPage', 3)
    await nextTick()
    pagination.vm.$emit('current-change', 3)
    await flushPromises()

    expect(listMock).toHaveBeenLastCalledWith({ kw: undefined, status: undefined, page: 3, size: 20 })
  })

  it('刷新 / 关闭页签：均重新载入列表并重置为仅列表页签', async () => {
    const { wrapper } = await mountView()

    await wrapper.find('[data-test="user-refresh"]').trigger('click')
    await flushPromises()
    expect(listMock).toHaveBeenCalledTimes(2)

    await wrapper.find('[data-test="user-close-page"]').trigger('click')
    await flushPromises()
    expect(useTabsStore().tabs.map((tab) => tab.key)).toEqual(['list'])
  })

  it('双击行打开记录页签（列表页签固定、记录页签可关）', async () => {
    const { wrapper } = await mountView()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabs.map((tab) => tab.key)).toEqual(['list', 'record:1'])
    expect(tabs.active).toBe('record:1')
    expect(wrapper.find('.user-record-tab-stub').exists()).toBe(true)
    expect(wrapper.findComponent({ name: 'UserRecordTab' }).props('userId')).toBe('1')
  })

  it('打开记录页签：用户名 / 姓名缺省时标题回退空串', async () => {
    listMock.mockResolvedValue({ list: [{ id: '9' }], total: 1 })
    const { wrapper } = await mountView()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    expect(useTabsStore().tabOf('record:9')?.title).toBe('（）')
  })

  it('新增：打开新增态记录页签（不请求详情）', async () => {
    const { wrapper } = await mountView(['user:create'])

    await wrapper.find('[data-test="user-create"]').trigger('click')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.active).toBe('record:new')
    expect(tabs.tabOf('record:new')?.title).toBe('新增用户')
    expect(wrapper.findComponent({ name: 'UserRecordTab' }).props('userId')).toBe('new')
  })

  it('批量删除：多选后确认删除并刷新列表', async () => {
    const { wrapper } = await mountView(['user:delete'])
    deleteMock.mockResolvedValue(null)

    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[0]])
    await flushPromises()
    await wrapper.find('[data-test="user-batch-delete"]').trigger('click')
    await flushPromises()

    expect(deleteMock).toHaveBeenCalledWith('1')
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 个用户')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('批量删除：空选时短路（不弹确认、不发请求）；未选行时删除按钮为禁用态', async () => {
    const { wrapper } = await mountView(['user:delete'])

    expect(wrapper.find('[data-test="user-batch-delete"]').attributes('disabled')).toBeDefined()

    // 空选时按钮为禁用态（原生 disabled 不派发 click）：直接调用处理函数覆盖短路分支
    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, () => Promise<void>> } }).$.setupState
    await state.removeSelected!()
    await flushPromises()

    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(deleteMock).not.toHaveBeenCalled()
  })

  it('批量删除：取消确认不删除；全部失败时汇总错误且不刷新', async () => {
    const { wrapper } = await mountView(['user:delete'])
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[0]])
    await flushPromises()
    await wrapper.find('[data-test="user-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    deleteMock.mockRejectedValueOnce(new Error('内置账户不可删除'))
    await wrapper.find('[data-test="user-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('内置账户不可删除')
    expect(ElMessage.success).not.toHaveBeenCalled()
    expect(listMock).toHaveBeenCalledTimes(1)

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="user-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：zhangsan')
  })

  it('批量删除：行用户名缺省时错误文案回退空串', async () => {
    const { wrapper } = await mountView(['user:delete'])
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [{ id: '9' }])
    await flushPromises()
    deleteMock.mockRejectedValueOnce('boom')

    await wrapper.find('[data-test="user-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：')
  })

  it('批量启停：选中含启用行时目标为停用（确认后逐行提交）', async () => {
    const { wrapper } = await mountView()
    updateStatusMock.mockResolvedValue({ status: 'disabled', session_revoked: true })

    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', PAGE.list)
    await flushPromises()
    await wrapper.find('[data-test="user-batch-toggle"]').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(updateStatusMock).toHaveBeenCalledWith('1', 'disabled')
    expect(updateStatusMock).toHaveBeenCalledWith('2', 'disabled')
    expect(ElMessage.success).toHaveBeenCalledWith('已批量停用')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('批量启停：选中均为停用行时目标为启用；取消确认则不提交', async () => {
    const { wrapper } = await mountView()
    updateStatusMock.mockResolvedValue({ status: 'enabled', session_revoked: false })
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[1]])
    await flushPromises()

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="user-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateStatusMock).not.toHaveBeenCalled()

    await wrapper.find('[data-test="user-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateStatusMock).toHaveBeenCalledWith('2', 'enabled')
    expect(ElMessage.success).toHaveBeenCalledWith('已批量启用')
  })

  it('批量启停：单行提交失败按 Error / 非 Error 分别提示（仍汇总成功）', async () => {
    const { wrapper } = await mountView()
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', PAGE.list)
    await flushPromises()

    updateStatusMock.mockRejectedValueOnce(new Error('账号已锁定'))
    updateStatusMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="user-batch-toggle"]').trigger('click')
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('账号已锁定')
    expect(ElMessage.error).toHaveBeenCalledWith('操作失败')
    expect(ElMessage.success).toHaveBeenCalledWith('已批量停用')
  })

  it('批量启停：空选时短路（不弹确认、不发请求）', async () => {
    const { wrapper } = await mountView()

    expect(wrapper.find('[data-test="user-batch-toggle"]').attributes('disabled')).toBeDefined()

    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, () => Promise<void>> } }).$.setupState
    await state.batchToggle!()
    await flushPromises()

    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(updateStatusMock).not.toHaveBeenCalled()
  })

  it('状态内联切换：停用需二次确认（确认后提交并提示）', async () => {
    const { wrapper } = await mountView()
    updateStatusMock.mockResolvedValue({ status: 'disabled', session_revoked: true })

    await switchOf(wrapper, 0).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(updateStatusMock).toHaveBeenCalledWith('1', 'disabled')
    expect(ElMessage.success).toHaveBeenCalledWith('已停用')
  })

  it('状态内联切换：停用确认被取消时回滚（不提交）', async () => {
    const { wrapper } = await mountView()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')

    await switchOf(wrapper, 0).vm.$emit('update:modelValue', false)
    await flushPromises()

    expect(updateStatusMock).not.toHaveBeenCalled()
  })

  it('状态内联切换：启用为普通操作（不经确认直存）', async () => {
    const { wrapper } = await mountView()
    updateStatusMock.mockResolvedValue({ status: 'enabled', session_revoked: false })

    await switchOf(wrapper, 1).vm.$emit('update:modelValue', true)
    await flushPromises()

    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(updateStatusMock).toHaveBeenCalledWith('2', 'enabled')
    expect(ElMessage.success).toHaveBeenCalledWith('已启用')
  })

  it('重置密码：非单行选中时提示不支持批量', async () => {
    const { wrapper } = await mountView(['user:reset_pwd'])
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', PAGE.list)
    await flushPromises()

    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, () => void> } }).$.setupState
    state.openResetPassword!()
    await flushPromises()

    expect(ElMessage.error).toHaveBeenCalledWith('请选择一行（重置密码不支持批量）')
  })

  it('重置密码：单行选中但行缺失时目标回退 null（确认时不发请求）', async () => {
    const { wrapper } = await mountView(['user:reset_pwd'])
    // 选中数组长度为 1 但元素缺失（稀疏选中）：目标回退 null
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [undefined])
    await flushPromises()

    await wrapper.find('[data-test="user-reset-pwd"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="user-pwd-input"]').setValue('Abcd1234')
    await wrapper.find('[data-test="user-pwd-confirm"]').trigger('click')
    await flushPromises()

    expect(resetPwdMock).not.toHaveBeenCalled()
  })

  it('重置密码：单行选中打开弹窗，空密码拦截、确认后提交并关闭', async () => {
    const { wrapper } = await mountView(['user:reset_pwd'])
    resetPwdMock.mockResolvedValue({ session_revoked: true, force_change: true })

    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[1]])
    await flushPromises()
    await wrapper.find('[data-test="user-reset-pwd"]').trigger('click')
    await flushPromises()

    const pwdInput = wrapper.find('[data-test="user-pwd-input"]')
    expect(pwdInput.exists()).toBe(true)

    // 复选框 v-model：缺省勾选（true），取消勾选后请求带 `force_change: false`
    const forceCheckbox = wrapper.find('[data-test="user-pwd-force"]').findComponent({ name: 'ElCheckbox' })
    expect(forceCheckbox.props('modelValue')).toBe(true)
    forceCheckbox.vm.$emit('update:modelValue', false)
    await nextTick()
    await wrapper.find('[data-test="user-pwd-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('请输入新密码')
    expect(resetPwdMock).not.toHaveBeenCalled()

    await pwdInput.setValue('Abcd1234')
    await wrapper.find('[data-test="user-pwd-confirm"]').trigger('click')
    await flushPromises()
    expect(resetPwdMock).toHaveBeenCalledWith('2', { new_password: 'Abcd1234', force_change: false })
    expect(ElMessage.success).toHaveBeenCalledWith('密码已重置（全部会话已失效）')
  })

  it('状态内联切换：行姓名缺省时停用确认文案回退空串', async () => {
    listMock.mockResolvedValue({ list: [{ id: '7', username: 'wangwu', status: 'enabled' }], total: 1 })
    const { wrapper } = await mountView()
    updateStatusMock.mockResolvedValue({ status: 'disabled', session_revoked: true })

    const state = (
      wrapper.vm as unknown as {
        $: { setupState: { toggleStatus: (row: { id: string }, next: boolean) => Promise<void> } }
      }
    ).$.setupState
    await state.toggleStatus({ id: '7' }, false)
    await flushPromises()

    expect(ElMessageBox.confirm).toHaveBeenCalledWith(
      '停用「」将立即失效该用户全部会话（踢出），确认停用？',
      '停用确认',
      { type: 'warning' },
    )
  })

  it('重置密码：提交失败按 Error / 非 Error 分别提示', async () => {
    const { wrapper } = await mountView(['user:reset_pwd'])
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[0]])
    await flushPromises()
    await wrapper.find('[data-test="user-reset-pwd"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="user-pwd-input"]').setValue('Abcd1234')

    resetPwdMock.mockRejectedValueOnce(new Error('密码强度不足'))
    await wrapper.find('[data-test="user-pwd-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('密码强度不足')

    resetPwdMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="user-pwd-confirm"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('重置失败')
  })

  it('重置密码：取消关闭弹窗（不提交）', async () => {
    const { wrapper } = await mountView(['user:reset_pwd'])
    wrapper.findComponent({ name: 'ElTable' }).vm.$emit('selection-change', [PAGE.list[0]])
    await flushPromises()
    await wrapper.find('[data-test="user-reset-pwd"]').trigger('click')
    await flushPromises()

    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(true)
    await wrapper.find('[data-test="user-pwd-cancel"]').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)

    // 对话框自身关闭（v-model 由父更新）
    wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('update:modelValue', false)
    await nextTick()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)

    expect(resetPwdMock).not.toHaveBeenCalled()
  })

  it('重置密码：目标缺失时直接返回（不提交）', async () => {
    const { wrapper } = await mountView()
    const state = (wrapper.vm as unknown as { $: { setupState: Record<string, () => Promise<void>> } }).$.setupState
    await state.doResetPassword!()

    expect(resetPwdMock).not.toHaveBeenCalled()
  })

  it('记录页签关闭：脏数据拦截（确认后丢弃、取消则保留）', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    const tabs = useTabsStore()
    tabs.setDirty('record:1', true)
    await nextTick()

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeDefined()

    await wrapper.find('[data-test="form-frame-close-record:1"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:1')).toBeUndefined()
  })

  it('记录页签关闭：非脏页签直接关闭（不走确认）', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[1]!.trigger('dblclick')
    await flushPromises()
    const tabs = useTabsStore()
    expect(tabs.tabOf('record:2')?.dirty).toBe(false)

    await wrapper.find('[data-test="form-frame-close-record:2"]').trigger('click')
    await flushPromises()

    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(tabs.tabOf('record:2')).toBeUndefined()
    expect(tabs.active).toBe('list')
  })

  it('记录页签关闭：页签不存在时拒绝关闭（拦截回调返回 false）', async () => {
    const { wrapper } = await mountView()
    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('记录页签关闭：记录页上抛 close 即丢弃页签', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'UserRecordTab' }).vm.$emit('close')
    await flushPromises()

    const tabs = useTabsStore()
    expect(tabs.tabOf('record:1')).toBeUndefined()
    expect(tabs.active).toBe('list')
  })

  it('记录保存回调：同步页签标题、激活记录页签并刷新列表', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'UserRecordTab' }).vm.$emit('saved', {
      id: '1',
      name: '张三（新）',
      username: 'zhangsan',
    })
    await settle()

    const tabs = useTabsStore()
    expect(tabs.tabOf('record:1')?.title).toBe('张三（新）（zhangsan）')
    expect(tabs.active).toBe('record:1')
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('记录保存回调：标题字段缺省时以空串拼接', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'UserRecordTab' }).vm.$emit('saved', { id: '1' })
    await settle()

    expect(useTabsStore().tabOf('record:1')?.title).toBe('（）')
  })

  it('记录保存回调：返回主键缺省或页签不存在时跳过标题同步，仅刷新列表', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    // 返回实体主键缺省（按空串寻页签，不命中）与主键与当前记录页签不符两种情形
    await wrapper.findComponent({ name: 'UserRecordTab' }).vm.$emit('saved', {})
    await settle()
    await wrapper.findComponent({ name: 'UserRecordTab' }).vm.$emit('saved', { id: '404' })
    await settle()

    const tabs = useTabsStore()
    expect(tabs.tabOf('record:404')).toBeUndefined()
    expect(tabs.tabOf('record:1')?.title).toBe('张三（zhangsan）')
    expect(listMock).toHaveBeenCalledTimes(3)
  })

  it('记录脏态同步：页签标记随记录页上抛更新', async () => {
    const { wrapper } = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    await wrapper.findComponent({ name: 'UserRecordTab' }).vm.$emit('dirty', true)
    await nextTick()
    expect(useTabsStore().tabOf('record:1')?.dirty).toBe(true)

    await wrapper.findComponent({ name: 'UserRecordTab' }).vm.$emit('dirty', false)
    await nextTick()
    expect(useTabsStore().tabOf('record:1')?.dirty).toBe(false)
  })
})
