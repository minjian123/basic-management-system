// kiwi_id: 2276
/**
 * 用户记录页「角色分配」区域项（`RoleAssignPanel`）用例（`02_02/_01` · Kiwi 2276）：
 * 宿主插槽上下文（`userId` + `registerSubmitter`）消费、已分配角色载入与失败降级、
 * 候选角色弹窗（关键字过滤 / 勾选草稿 / 关闭保留）、只读态（无宿主通道或无权限码）、
 * 草稿提交器登记（`isDirty` / `buildSegment` / `reload`）。
 */

import { MODULE_SLOT_CONTEXT_KEY, type HostSubmitterEntry, type HostSubmitterRegistrar } from '@bms/ui_ep'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref, type Ref } from 'vue'

const listUserRoles = vi.fn()
const listRoles = vi.fn()

vi.mock('@/api/user', () => ({
  listUserRoles: (...args: unknown[]) => listUserRoles(...args),
  getUser: vi.fn(),
  listUsers: vi.fn(),
  createUser: vi.fn(),
  updateUser: vi.fn(),
  updateUserStatus: vi.fn(),
  deleteUser: vi.fn(),
  applyUserAssignments: vi.fn(),
  listUserIdentities: vi.fn(),
  resetUserPassword: vi.fn(),
}))

vi.mock('@/api/role', () => ({ listRoles: (...args: unknown[]) => listRoles(...args) }))

const { useSessionStore } = await import('@/stores/session')
const RoleAssignPanel = (await import('@/views/system/user/RoleAssignPanel.vue')).default

/** 用例内共享的 pinia 实例。 */
let pinia: ReturnType<typeof createPinia>
/** 插槽上下文（宿主记录页注入；`registerSubmitter` 由用例捕获）。 */
let context: Ref<Record<string, unknown> | undefined>
/** 用例捕获的宿主提交器登记通道。 */
let capturedRegistrar: HostSubmitterRegistrar | undefined
/** 登记到宿主提交器（`reload` 供用例断言）。 */
let entry: HostSubmitterEntry | undefined

/** 装饰性 EP 件桩（表格列 / 弹窗壳透传插槽；原生表格在 jsdom 下依赖 ResizeObserver）。 */
const stubs = {
  ElTable: defineComponent({
    name: 'ElTable',
    props: { data: { type: Array, default: () => [] } },
    template: '<div class="el-table-stub"><slot name="empty" /></div>',
  }),
  ElTableColumn: defineComponent({ name: 'ElTableColumn', template: '<div />' }),
}

/**
 * 挂载区域项（经宿主上下文注入通道）。
 *
 * @param options 覆盖项：`noUser` 表示上下文无作用实体；`noRegistrar` 表示无宿主提交器通道；`noContext` 表示完全无上下文。
 */
async function mountPanel(
  options: {
    userId?: string
    noUser?: boolean
    noRegistrar?: boolean
    noContext?: boolean
  } = {},
): Promise<VueWrapper> {
  const registrar: HostSubmitterRegistrar | undefined = options.noRegistrar
    ? undefined
    : (value: HostSubmitterEntry) => (entry = value)
  capturedRegistrar = registrar
  context = options.noContext
    ? ref<Record<string, unknown> | undefined>(undefined)
    : ref<Record<string, unknown> | undefined>({
        userId: options.noUser ? undefined : (options.userId ?? '7'),
        registerSubmitter: registrar,
      })
  const wrapper = mount(RoleAssignPanel, {
    global: {
      plugins: [pinia],
      stubs,
      provide: { [MODULE_SLOT_CONTEXT_KEY]: context },
    },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  context = undefined
  capturedRegistrar = undefined
  entry = undefined
  listUserRoles.mockReset()
  listRoles.mockReset()
  listUserRoles.mockResolvedValue({
    items: [{ role_id: '1', role_code: 'role_a', role_name: '角色甲', role_type: 'custom' }],
  })
  listRoles.mockResolvedValue({ list: [{ id: '2', code: 'role_b', name: '角色乙' }] })
  useSessionStore().codes = ['user:assign_role']
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
})

describe('用户记录页「角色分配」区域项（02_02/_01 · Kiwi 2276）', () => {
  it('载入已分配角色：请求作用实体、回填草稿并渲染计数与表格', async () => {
    const wrapper = await mountPanel()

    expect(listUserRoles).toHaveBeenCalledWith('7')
    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 1')
    expect(wrapper.find('[data-test="user-role-table"]').exists()).toBe(true)
    // 可写（有宿主通道 + 权限码）：显示选择入口、不显示只读提示
    expect(wrapper.find('[data-test="user-role-open"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-role-readonly"]').exists()).toBe(false)
    // 草稿与已分配一致：无脏标记
    expect(wrapper.find('[data-test="user-role-dirty"]').exists()).toBe(false)
  })

  it('已分配表格：类型列经角色类型映射渲染（真实 EP 件）', async () => {
    listUserRoles.mockResolvedValue({
      items: [
        { role_id: '1', role_code: 'role_a', role_name: '角色甲', role_type: 'custom' },
        { role_id: '2', role_code: 'role_b', role_name: '角色乙', role_type: undefined },
      ],
    })
    // 本用例不桩表格：真实 `el-table` 渲染列模板（jsdom 下可渲染，仅交互需 ResizeObserver）
    const wrapper = mount(RoleAssignPanel, {
      global: {
        plugins: [pinia],
        provide: { [MODULE_SLOT_CONTEXT_KEY]: ref({ userId: '7', registerSubmitter: () => undefined }) },
      },
    })
    await flushPromises()

    const text = wrapper.find('[data-test="user-role-table"]').text()
    expect(text).toContain('自定义')
    expect(text).toContain('—')
  })

  it('上下文缺省：短路不请求，渲染「尚未选择用户」空态', async () => {
    const wrapper = await mountPanel({ noUser: true })

    expect(listUserRoles).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="user-role-context-absent"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-role-count"]').exists()).toBe(false)
  })

  it('作用实体为空串：同样短路不请求', async () => {
    const wrapper = await mountPanel({ userId: '' })

    expect(listUserRoles).not.toHaveBeenCalled()
    expect(wrapper.find('[data-test="user-role-context-absent"]').exists()).toBe(true)
  })

  it('已分配载入失败：按 Error / 非 Error 分别提示，草稿保持为空', async () => {
    listUserRoles.mockRejectedValueOnce(new Error('用户不存在'))
    const wrapper = await mountPanel()
    expect(ElMessage.error).toHaveBeenCalledWith('用户不存在')
    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 0')

    listUserRoles.mockRejectedValueOnce('boom')
    await mountPanel()
    expect(ElMessage.error).toHaveBeenCalledWith('已分配角色加载失败')
  })

  it('已分配清单缺省：`items` 缺失按空集处理', async () => {
    listUserRoles.mockResolvedValue({})
    const wrapper = await mountPanel()

    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 0')
  })

  it('只读态：无宿主通道时不给选择入口（避免绕过编排直写关系表）', async () => {
    const wrapper = await mountPanel({ noRegistrar: true })

    expect(wrapper.find('[data-test="user-role-readonly"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-role-open"]').exists()).toBe(false)
  })

  it('只读态：无 `user:assign_role` 权限码时不给选择入口', async () => {
    useSessionStore().codes = []
    const wrapper = await mountPanel()

    expect(wrapper.find('[data-test="user-role-readonly"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="user-role-open"]').exists()).toBe(false)
  })

  it('选择角色弹窗：候选按关键字过滤（角色码 / 名称）', async () => {
    listRoles.mockResolvedValue({
      list: [
        { id: '2', code: 'role_b', name: '角色乙' },
        { id: '3', code: 'audit_x', name: '审计员' },
        // 角色码 / 名称均缺失：无关键字时在列，有关键字时被过滤（缺省空串参与拼接）
        { id: '4' },
      ],
    })
    const wrapper = await mountPanel()

    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()

    expect(listRoles).toHaveBeenCalledWith({ status: 'enabled', size: 200 })
    expect(wrapper.findAll('[data-test^="user-role-candidate-"]')).toHaveLength(3)

    await wrapper.find('[data-test="user-role-picker-kw"]').setValue('AUDIT')
    expect(wrapper.findAll('[data-test^="user-role-candidate-"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="user-role-candidate-3"]').exists()).toBe(true)

    await wrapper.find('[data-test="user-role-picker-kw"]').setValue('角色')
    expect(wrapper.findAll('[data-test^="user-role-candidate-"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="user-role-candidate-2"]').exists()).toBe(true)

    // 关键字回清空：候选恢复全量
    await wrapper.find('[data-test="user-role-picker-kw"]').setValue('')
    expect(wrapper.findAll('[data-test^="user-role-candidate-"]')).toHaveLength(3)
  })

  it('候选载入失败：按 Error / 非 Error 分别提示', async () => {
    listRoles.mockRejectedValueOnce(new Error('角色服务不可用'))
    const wrapper = await mountPanel()
    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('角色服务不可用')

    listRoles.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('角色列表加载失败')
  })

  it('候选清单缺省：`list` 缺失按空集处理', async () => {
    listRoles.mockResolvedValue({})
    const wrapper = await mountPanel()
    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()

    expect(wrapper.findAll('[data-test^="user-role-candidate-"]')).toHaveLength(0)
  })

  it('勾选只改草稿：置脏标记并按集合差异上报', async () => {
    const wrapper = await mountPanel()
    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()
    const group = wrapper.findComponent({ name: 'ElCheckboxGroup' })

    group.vm.$emit('change', ['1', '2'])
    await nextTick()
    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 2')
    expect(wrapper.find('[data-test="user-role-dirty"]').exists()).toBe(true)

    // 集合差异：新增项即脏
    expect(entry?.isDirty()).toBe(true)
    expect(entry?.buildSegment()).toEqual({ key: 'role_ids', value: { role_ids: ['1', '2'] } })

    // 回填原集合：脏态消除，段返回 `null`
    group.vm.$emit('change', ['1'])
    await nextTick()
    expect(wrapper.find('[data-test="user-role-dirty"]').exists()).toBe(false)
    expect(entry?.buildSegment()).toBeNull()
  })

  it('勾选为数值 / 布尔时统一字符串化（雪花主键口径）', async () => {
    const wrapper = await mountPanel()
    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()
    wrapper.findComponent({ name: 'ElCheckboxGroup' }).vm.$emit('change', [1, true])
    await nextTick()

    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 2')
    expect(entry?.buildSegment()).toEqual({ key: 'role_ids', value: { role_ids: ['1', 'true'] } })
  })

  it('弹窗关闭：草稿保留（取消 / 确定同一行为）', async () => {
    const wrapper = await mountPanel()
    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()
    wrapper.findComponent({ name: 'ElCheckboxGroup' }).vm.$emit('change', ['2'])
    await nextTick()

    await wrapper.find('[data-test="user-role-picker-cancel"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 1')

    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-test="user-role-picker-confirm"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 1')
  })

  it('弹窗经 `v-model` 回写：`update:modelValue` 直接关闭草稿弹窗', async () => {
    const DialogStub = defineComponent({
      name: 'ElDialog',
      props: { modelValue: { type: Boolean, default: false } },
      emits: ['update:modelValue'],
      template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
    })
    const wrapper = mount(RoleAssignPanel, {
      global: {
        plugins: [pinia],
        stubs: { ...stubs, ElDialog: DialogStub },
        provide: { [MODULE_SLOT_CONTEXT_KEY]: ref({ userId: '7', registerSubmitter: () => undefined }) },
      },
    })
    await flushPromises()

    await wrapper.find('[data-test="user-role-open"]').trigger('click')
    await nextTick()
    const dialog = wrapper.findComponent(DialogStub)
    expect(dialog.props('modelValue')).toBe(true)

    // 弹窗自身回写（关闭按钮 / 遮罩）：宿主 `v-model` 绑定同步关闭
    dialog.vm.$emit('update:modelValue', false)
    await nextTick()
    expect(wrapper.findComponent(DialogStub).props('modelValue')).toBe(false)
  })

  it('宿主提交器登记：`reload` 重新载入已分配集合', async () => {
    const wrapper = await mountPanel()
    expect(capturedRegistrar).toBeDefined()
    expect(entry).toBeDefined()

    listUserRoles.mockResolvedValue({ items: [] })
    await entry?.reload()
    await flushPromises()
    expect(listUserRoles).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-test="user-role-count"]').text()).toBe('已分配 0')
  })

  it('作用实体切换：重新载入已分配集合', async () => {
    const wrapper = await mountPanel()
    context.value = { userId: '9', registerSubmitter: capturedRegistrar }
    await flushPromises()

    expect(listUserRoles).toHaveBeenLastCalledWith('9')
    expect(wrapper.find('[data-test="user-role-count"]').exists()).toBe(true)
  })

  it('载入中：显示载入提示', async () => {
    let release: (value: unknown) => void = () => undefined
    listUserRoles.mockReturnValue(
      new Promise((resolve) => {
        release = resolve
      }),
    )
    const wrapper = mount(RoleAssignPanel, {
      global: { plugins: [pinia], stubs, provide: { [MODULE_SLOT_CONTEXT_KEY]: ref({ userId: '7' }) } },
    })
    await nextTick()

    expect(wrapper.find('[data-test="user-role-loading"]').exists()).toBe(true)
    release({ items: [] })
    await flushPromises()
    expect(wrapper.find('[data-test="user-role-loading"]').exists()).toBe(false)
  })
})
