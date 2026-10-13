// kiwi_id: 2277, 2294
/**
 * 用户记录页（`UserRecordTab`）用例（`02_02` / `08_02` · Kiwi 2277 / 2294）：
 * 详情载入 / 编辑与取消 / 工具栏单一保存（基础资料与分配分段）/ 新建（初始密码）/ 删除 /
 * SSO 身份只读区块 / 脏态判定与上抛 / 三子页签渲染 / 字典记录页骨架对齐（骨架件承载、
 * 首行三字段顺序与列宽、业务 Tab 位置、SSO 区块落系统信息侧）。
 *
 * 说明：插件挂接位在本用例中由桩件承接（`ModuleAreaOutlet` 桩捕获宿主上下文），
 * 挂接位本身的契约由 `user-assign-slot.spec.ts`（Kiwi 2276）覆盖。
 */

import { flushPromises, mount } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, onMounted } from 'vue'

const getUser = vi.fn()
const listUserIdentities = vi.fn()
const createUser = vi.fn()
const updateUser = vi.fn()
const updateUserStatus = vi.fn()
const deleteUser = vi.fn()
const applyUserAssignments = vi.fn()

vi.mock('@/api/user', () => ({
  getUser: (...args: unknown[]) => getUser(...args),
  listUserIdentities: (...args: unknown[]) => listUserIdentities(...args),
  createUser: (...args: unknown[]) => createUser(...args),
  updateUser: (...args: unknown[]) => updateUser(...args),
  updateUserStatus: (...args: unknown[]) => updateUserStatus(...args),
  deleteUser: (...args: unknown[]) => deleteUser(...args),
  applyUserAssignments: (...args: unknown[]) => applyUserAssignments(...args),
  listUserRoles: vi.fn(),
  listUsers: vi.fn(),
  resetUserPassword: vi.fn(),
}))

vi.mock('@/api/role', () => ({ listRoles: vi.fn() }))

const { useSessionStore } = await import('@/stores/session')
const UserRecordTab = (await import('@/views/system/user/UserRecordTab.vue')).default

/** 用例内共享的 pinia 实例。 */
let pinia: ReturnType<typeof createPinia>

/** 宿主提交器登记入参（供桩件捕获后由用例驱动）。 */
interface SubmitterEntry {
  isDirty: () => boolean
  buildSegment: () => { key: string; value: Record<string, unknown> } | null
  reload: () => Promise<void>
}

/** 桩件捕获到的插槽上下文（`registerSubmitter` 值即函数）。 */
let captured: { registerSubmitter: (entry: SubmitterEntry) => void } | undefined

/**
 * `ModuleAreaOutlet` 桩：透传插槽上下文供用例登记草稿提交器。
 *
 * 说明：桩根节点以 class 标识（`data-test` 会被宿主透传属性覆盖）。
 */
const OutletStub = defineComponent({
  name: 'ModuleAreaOutlet',
  props: { context: { type: Object, default: undefined } },
  setup(props) {
    onMounted(() => {
      captured = props.context as { registerSubmitter: (entry: SubmitterEntry) => void }
    })
    return () => h('div', { class: 'user-assign-outlet-stub' })
  },
})

/** 装饰性 EP 件桩。 */
const stubs = { ModuleAreaOutlet: OutletStub }

/** 用户详情桩数据。 */
const DETAIL = {
  id: '7',
  username: 'zhangsan',
  name: '张三',
  phone: '13800000000',
  email: 'zhangsan@example.com',
  status: 'enabled',
  version: 3,
  created_at: '2026-10-09T00:00:00',
  updated_at: '2026-10-09T00:00:00',
}

/**
 * 挂载用户记录页。
 *
 * @param userId 用户主键（新增态传 `new`）。
 */
async function mountRecord(userId = '7') {
  const wrapper = mount(UserRecordTab, { props: { userId }, global: { plugins: [pinia], stubs } })
  await flushPromises()
  return wrapper
}

/** 记录页暴露面。 */
type Exposed = { save: () => Promise<void>; isDirty: () => boolean }

/** 取记录页暴露面。 */
function exposed(wrapper: ReturnType<typeof mount>): Exposed {
  return wrapper.vm as unknown as Exposed
}

/** 登记一个草稿提交器（经桩件捕获的宿主通道）。 */
async function registerEntry(entry: SubmitterEntry): Promise<void> {
  captured?.registerSubmitter(entry)
  await nextTick()
}

/** 默认提交器（无改动、无分段）。 */
function idleEntry(): SubmitterEntry {
  return { isDirty: () => false, buildSegment: () => null, reload: vi.fn(async () => undefined) }
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  captured = undefined
  for (const mock of [
    getUser,
    listUserIdentities,
    createUser,
    updateUser,
    updateUserStatus,
    deleteUser,
    applyUserAssignments,
  ]) {
    mock.mockReset()
  }
  getUser.mockResolvedValue({ ...DETAIL })
  listUserIdentities.mockResolvedValue({ items: [] })
  createUser.mockResolvedValue({ user: { ...DETAIL }, initial_password: null })
  updateUser.mockResolvedValue({ ...DETAIL })
  updateUserStatus.mockResolvedValue({})
  deleteUser.mockResolvedValue(null)
  applyUserAssignments.mockResolvedValue({})
  useSessionStore().codes = ['user:update', 'user:delete', 'user:assign_role']
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessageBox, 'alert').mockResolvedValue(undefined as never)
})

describe('用户记录页（02_02 · Kiwi 2277）', () => {
  it('详情载入：回填表单、置查看态并载入 SSO 身份', async () => {
    listUserIdentities.mockResolvedValue({
      items: [{ idp_key: 'oidc', external_id: 'sub-1', tenant_id: 't1' }],
    })
    const wrapper = await mountRecord()

    expect(getUser).toHaveBeenCalledWith('7')
    expect(listUserIdentities).toHaveBeenCalledWith('7')
    expect((wrapper.find('[data-test="user-record-username"]').element as HTMLInputElement).value).toBe('zhangsan')
    expect((wrapper.find('[data-test="user-record-name"]').element as HTMLInputElement).value).toBe('张三')
    expect(wrapper.find('[data-test="user-record-edit"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-record-identities"]').text()).toContain('oidc')
  })

  it('详情载入失败：按 Error / 非 Error 分别提示', async () => {
    getUser.mockRejectedValueOnce(new Error('用户不存在'))
    await mountRecord()
    expect(ElMessage.error).toHaveBeenCalledWith('用户不存在')

    getUser.mockRejectedValueOnce('oops')
    await mountRecord()
    expect(ElMessage.error).toHaveBeenCalledWith('用户详情加载失败')
  })

  it('详情字段缺省：逐字段回退默认值（账号 / 姓名 / 联系方式 / 状态 / 版本）', async () => {
    getUser.mockResolvedValue({ id: '7' })
    listUserIdentities.mockResolvedValue({})
    const wrapper = await mountRecord()

    expect((wrapper.find('[data-test="user-record-username"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('[data-test="user-record-name"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('[data-test="user-record-phone"]').element as HTMLInputElement).value).toBe('')
    expect((wrapper.find('[data-test="user-record-email"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.find('[data-test="user-record-identities"]').text()).toContain('该用户未绑定任何 SSO 身份')

    // 详情状态缺省（`enabled`）：改名保存时状态判定取默认值，不触发启停端点
    await wrapper.find('[data-test="user-record-edit"]').trigger('click')
    await wrapper.find('[data-test="user-record-name"]').setValue('张三丰')
    await exposed(wrapper).save()
    await flushPromises()
    expect(updateUserStatus).not.toHaveBeenCalled()
  })

  it('SSO 身份载入失败：静默降级为空（不提示）', async () => {
    listUserIdentities.mockRejectedValue(new Error('identity 服务不可用'))
    const wrapper = await mountRecord()

    await wrapper.findAll('.el-tabs__item')[2]!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="user-record-identities"]').text()).toContain('该用户未绑定任何 SSO 身份')
    expect(ElMessage.error).not.toHaveBeenCalled()
  })

  it('编辑：改动基础资料置脏并上抛 dirty；回填原值后脏态消除', async () => {
    const wrapper = await mountRecord()

    await wrapper.find('[data-test="user-record-edit"]').trigger('click')
    const name = wrapper.find('[data-test="user-record-name"]')
    await name.setValue('张三丰')
    await wrapper.find('[data-test="user-record-email"]').setValue('zhangsanfeng@example.com')
    expect(wrapper.find('[data-test="user-record-dirty"]').exists()).toBe(true)
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    await name.setValue('张三')
    await wrapper.find('[data-test="user-record-email"]').setValue('zhangsan@example.com')
    expect(wrapper.find('[data-test="user-record-dirty"]').exists()).toBe(false)
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([false])
  })

  it('新增态改动表单不置脏（新增不参与基线比对）', async () => {
    const wrapper = await mountRecord('new')

    await wrapper.find('[data-test="user-record-username"]').setValue('lisi')
    expect(wrapper.find('[data-test="user-record-dirty"]').exists()).toBe(false)
  })

  it('取消编辑：查看态按详情回填并重新载入；新增态直接关闭', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="user-record-edit"]').trigger('click')
    await wrapper.find('[data-test="user-record-cancel"]').trigger('click')
    await flushPromises()
    expect(getUser).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="user-record-edit"]').exists()).toBe(true)

    // 新增态工具栏无「取消」按钮（模板仅在非新增态的编辑态渲染）；经组件实例直接调用该分支
    const created = await mountRecord('new')
    ;(created.vm as unknown as { cancelEdit: () => void }).cancelEdit()
    await nextTick()
    expect(created.emitted('close')).toHaveLength(1)
  })

  it('保存：仅基础资料改动走 updateUser（状态未变不调启停端点）', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="user-record-edit"]').trigger('click')
    await wrapper.find('[data-test="user-record-name"]').setValue('张三丰')

    await exposed(wrapper).save()
    await flushPromises()

    expect(updateUser).toHaveBeenCalledWith('7', {
      name: '张三丰',
      email: 'zhangsan@example.com',
      phone: '13800000000',
      version: 3,
    })
    expect(updateUserStatus).not.toHaveBeenCalled()
    expect(applyUserAssignments).not.toHaveBeenCalled()
    expect(ElMessage.success).toHaveBeenCalledWith('保存成功')
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('保存：状态改动追加启停端点（详情状态与表单不一致）', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="user-record-edit"]').trigger('click')
    await wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 'disabled')
    await nextTick()

    await exposed(wrapper).save()
    await flushPromises()

    expect(updateUser).toHaveBeenCalledTimes(1)
    expect(updateUserStatus).toHaveBeenCalledWith('7', 'disabled')
  })

  it('保存：分配草稿经编排端点一次提交（角色 / 岗位 / 部门三段）', async () => {
    const reload = vi.fn(async () => undefined)
    const wrapper = await mountRecord()
    await registerEntry({
      isDirty: () => true,
      buildSegment: () => ({ key: 'role_ids', value: { role_ids: ['1', '2'] } }),
      reload,
    })
    await registerEntry({
      isDirty: () => false,
      buildSegment: () => ({ key: 'user_posts', value: { post_ids: ['p1'] } }),
      reload,
    })
    await registerEntry({
      isDirty: () => false,
      buildSegment: () => ({ key: 'user_depts', value: { dept_ids: ['d1'] } }),
      reload,
    })
    await registerEntry(idleEntry())
    // 段值缺省（`role_ids` 缺失 → 空集）与未知段名（不参与编排）均不报错
    await registerEntry({
      isDirty: () => false,
      buildSegment: () => ({ key: 'role_ids', value: {} }),
      reload: vi.fn(async () => undefined),
    })
    await registerEntry({
      isDirty: () => false,
      buildSegment: () => ({ key: 'unknown_segment', value: {} }),
      reload: vi.fn(async () => undefined),
    })

    await exposed(wrapper).save()
    await flushPromises()

    expect(applyUserAssignments).toHaveBeenCalledWith('7', {
      profile: null,
      role_ids: [],
      user_posts: { post_ids: ['p1'] },
      user_depts: { dept_ids: ['d1'] },
    })
    expect(reload).toHaveBeenCalledTimes(3)
    expect(updateUser).not.toHaveBeenCalled()
  })

  it('保存：本体改动 + 分配草稿同帧提交（载荷带 profile）', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="user-record-edit"]').trigger('click')
    await wrapper.find('[data-test="user-record-phone"]').setValue('13900000000')
    await registerEntry({
      isDirty: () => true,
      buildSegment: () => ({ key: 'role_ids', value: { role_ids: ['1'] } }),
      reload: vi.fn(async () => undefined),
    })

    await exposed(wrapper).save()
    await flushPromises()

    expect(applyUserAssignments).toHaveBeenCalledWith('7', {
      profile: { name: '张三', email: 'zhangsan@example.com', phone: '13900000000', status: 'enabled', version: 3 },
      role_ids: ['1'],
      user_posts: null,
      user_depts: null,
    })
  })

  it('保存：无任何变更时短路（不发请求、退出编辑态）', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="user-record-edit"]').trigger('click')

    await exposed(wrapper).save()
    await flushPromises()

    expect(updateUser).not.toHaveBeenCalled()
    expect(applyUserAssignments).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="user-record-edit"]').exists()).toBe(true)
  })

  it('保存失败：按 Error / 非 Error 分别提示', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="user-record-edit"]').trigger('click')
    await wrapper.find('[data-test="user-record-name"]').setValue('张三丰')
    updateUser.mockRejectedValueOnce(new Error('乐观锁冲突'))
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('乐观锁冲突')

    updateUser.mockRejectedValueOnce('boom')
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('保存失败')
  })

  it('新建：提交建号（无初始密码不弹窗）并上抛 saved', async () => {
    const wrapper = await mountRecord('new')
    await wrapper.find('[data-test="user-record-username"]').setValue('lisi')
    await wrapper.find('[data-test="user-record-name"]').setValue('李四')
    await wrapper.find('[data-test="user-record-email"]').setValue('lisi@example.com')
    await wrapper.find('[data-test="user-record-phone"]').setValue('13900000000')
    await wrapper.findComponent({ name: 'ElCheckbox' }).vm.$emit('update:modelValue', false)
    await nextTick()

    await exposed(wrapper).save()
    await flushPromises()

    expect(createUser).toHaveBeenCalledWith({
      username: 'lisi',
      name: '李四',
      pwd_reset_required: false,
      email: 'lisi@example.com',
      phone: '13900000000',
      status: 'enabled',
    })
    expect(ElMessageBox.alert).not.toHaveBeenCalled()
    expect(ElMessage.success).toHaveBeenCalledWith('用户已创建')
    expect(wrapper.emitted('saved')).toHaveLength(1)
  })

  it('新建：有初始密码时弹窗提示留存', async () => {
    createUser.mockResolvedValue({ user: { id: '7' }, initial_password: 'Init@123' })
    const wrapper = await mountRecord('new')

    await exposed(wrapper).save()
    await flushPromises()

    expect(ElMessageBox.alert).toHaveBeenCalledWith('初始密码：Init@123', '请留存初始密码', { type: 'warning' })
  })

  it('新建失败：按 Error / 非 Error 分别提示', async () => {
    createUser.mockRejectedValueOnce(new Error('账号已存在'))
    const wrapper = await mountRecord('new')
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('账号已存在')

    createUser.mockRejectedValueOnce('boom')
    await exposed(wrapper).save()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('新建失败')
  })

  it('删除：确认后删除并关闭；取消确认不删除；删除失败提示', async () => {
    const wrapper = await mountRecord()
    await wrapper.find('[data-test="user-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteUser).toHaveBeenCalledWith('7')
    expect(ElMessage.success).toHaveBeenCalledWith('已删除')
    expect(wrapper.emitted('close')).toHaveLength(1)

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    const kept = await mountRecord()
    await kept.find('[data-test="user-record-delete"]').trigger('click')
    await flushPromises()
    expect(deleteUser).toHaveBeenCalledTimes(1)
    expect(kept.emitted('close')).toBeUndefined()

    deleteUser.mockRejectedValueOnce(new Error('内置管理员不可删除'))
    const failed = await mountRecord()
    await failed.find('[data-test="user-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('内置管理员不可删除')

    deleteUser.mockRejectedValueOnce('boom')
    await failed.find('[data-test="user-record-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败')
  })

  it('权限缺省：隐藏修改与删除按钮', async () => {
    useSessionStore().codes = []
    const wrapper = await mountRecord()

    expect(wrapper.find('[data-test="user-record-edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="user-record-delete"]').exists()).toBe(false)
  })

  it('工具栏：刷新重新载入、关闭上抛 close', async () => {
    const wrapper = await mountRecord()

    await wrapper.find('[data-test="user-record-refresh"]').trigger('click')
    await flushPromises()
    expect(getUser).toHaveBeenCalledTimes(2)

    await wrapper.find('[data-test="user-record-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('用户分配页签：停用账号给出只读提示，启用账号渲染挂接位', async () => {
    getUser.mockResolvedValue({ ...DETAIL, status: 'disabled' })
    const wrapper = await mountRecord()
    await wrapper.findAll('.el-tabs__item')[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="user-assign-disabled-hint"]').exists()).toBe(true)
    expect(wrapper.find('.user-assign-outlet-stub').exists()).toBe(true)
  })

  it('新增态插槽上下文：userId 归一为空串（不向插件暴露 `new`）', async () => {
    const wrapper = await mountRecord('new')

    const context = (wrapper.vm as unknown as { $: { setupState: Record<string, unknown> } }).$.setupState
      .slotContext as Record<string, unknown>
    expect(context.userId).toBe('')
    expect(typeof context.registerSubmitter).toBe('function')
  })

  it('用户分配页签：新增态提示创建后可分配（不渲染挂接位）', async () => {
    const wrapper = await mountRecord('new')
    await wrapper.findAll('.el-tabs__item')[1]!.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="user-assign-new-hint"]').exists()).toBe(true)
    expect(wrapper.find('.user-assign-outlet-stub').exists()).toBe(false)
  })

  it('系统信息页签：渲染系统信息面板与 SSO 身份表', async () => {
    const wrapper = await mountRecord()
    await wrapper.findAll('.el-tabs__item')[2]!.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="sys-info-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-record-identities"]').exists()).toBe(true)
  })

  it('props.userId 变化：重新载入详情', async () => {
    const wrapper = await mountRecord()
    await wrapper.setProps({ userId: '8' })
    await flushPromises()

    expect(getUser).toHaveBeenLastCalledWith('8')
  })

  it('暴露 isDirty：随插件草稿变化', async () => {
    const wrapper = await mountRecord()
    expect(exposed(wrapper).isDirty()).toBe(false)

    await registerEntry({ ...idleEntry(), isDirty: () => true })
    expect(exposed(wrapper).isDirty()).toBe(true)
  })
})

describe('用户记录页 · 字典记录页骨架对齐（08_02 · Kiwi 2294）', () => {
  it('经骨架件承载：信息栏两固定 Tab 齐备，业务 Tab 插在两者之间', async () => {
    const wrapper = await mountRecord()

    expect(wrapper.find('[data-test="dict-record-layout"]').exists()).toBe(true)
    const labels = wrapper.findAllComponents({ name: 'ElTabPane' }).map((pane) => pane.props('label'))
    expect(labels).toEqual(['详细信息', '用户分配', '系统信息'])
  })

  it('详细信息首行三字段（用户名 / 姓名 / 状态）三列等宽且顺序固定，其余字段排首行之后', async () => {
    const wrapper = await mountRecord()

    for (const test of ['user-record-username', 'user-record-name', 'user-record-status']) {
      const col = wrapper.find(`[data-test="${test}"]`).element.closest('.el-col')
      expect(col?.className).toContain('el-col-8')
    }
    const html = wrapper.html()
    const order = [
      'user-record-username',
      'user-record-name',
      'user-record-status',
      'user-record-phone',
      'user-record-email',
    ]
    const indexes = order.map((test) => html.indexOf(`data-test="${test}"`))
    expect(indexes.every((value, index) => value >= 0 && (index === 0 || value > indexes[index - 1]!))).toBe(true)
  })

  it('SSO 身份绑定只读区块落「系统信息」侧、排在内置系统信息件之后', async () => {
    listUserIdentities.mockResolvedValue({ items: [{ idp_key: 'oidc', external_id: 'sub-1', tenant_id: 't1' }] })
    const wrapper = await mountRecord()

    const sysPane = wrapper.find('#pane-sys')
    expect(sysPane.exists()).toBe(true)
    expect(sysPane.find('[data-test="sys-info-panel"]').exists()).toBe(true)
    expect(sysPane.find('[data-test="user-record-identities"]').exists()).toBe(true)
    const html = sysPane.html()
    expect(html.indexOf('sys-info-panel')).toBeLessThan(html.indexOf('user-record-identities'))
  })
})
