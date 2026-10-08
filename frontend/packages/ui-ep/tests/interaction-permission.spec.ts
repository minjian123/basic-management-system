// kiwi_id: 768（旧口径；新口径用例编号于测试步登记后回填）
/** 授权组件与宿主核对用例（08-4-4，新口径）：契约套件驱动（投影适配）+ 八件组件。 */

import {
  BaseAccess,
  type DataScopePolicyItem,
  type DataScopePolicyType,
  type PermissionJobs,
  type PermissionMetadata,
} from '@bms/core'
import {
  describePermissionConfigContract,
  type PermissionConfigContractTarget,
  type PermissionContractHandlers,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import {
  ActionPermissionPanel,
  DataScopePanel,
  DynamicDictPicker,
  FieldPermissionPanel,
  FormPermissionPanel,
  MenuPermissionPanel,
  PermissionConfig,
  PermissionTree,
  RoleAssignPanel,
  useBasePermissionConfig,
} from '../src'

/** 权限上下文样例。 */
class SampleAccess extends BaseAccess {}

/** 契约适配：投影 → 结构化契约面。 */
function permissionTarget(): PermissionConfigContractTarget {
  const projection = useBasePermissionConfig()
  let access: SampleAccess | undefined
  const codesOf = (): readonly string[] => access?.codes ?? []
  return {
    get ready() {
      return projection.ready.value
    },
    get degraded() {
      return projection.degraded.value
    },
    get disabled() {
      return projection.disabled.value
    },
    get requestCount() {
      return projection.requestCount.value
    },
    get dirty() {
      return projection.dirty.value
    },
    get phase() {
      return projection.phase.value
    },
    get canSave() {
      return projection.canSave.value
    },
    get pendingAccessRefresh() {
      return projection.pendingAccessRefresh.value
    },
    get accessCodes() {
      return codesOf()
    },
    setReady: (value) => projection.setReady(value),
    setAccess: (list) => {
      access = new SampleAccess()
      access.setCodes(list)
      projection.setAccess(access)
    },
    setHandlers: (handlers: PermissionContractHandlers) => projection.setJobs(handlers as PermissionJobs),
    load: async () => {
      await projection.load()
    },
    toggleMenu: (id, checked) => projection.toggleMenu(id, checked),
    menuCheckState: (id) => projection.checkMenuState(id),
    formSourceMenuIds: (formId) => projection.formSources(formId),
    toggleAction: (actionId, sourceMenuId, checked) => projection.toggleAction(actionId, sourceMenuId, checked),
    actionSourceMenuIds: (actionId) => projection.actionSources(actionId),
    fieldPerm: (formId, fieldId) => {
      const entry = projection.fieldEntries.value.find(
        (item) => item.formId === formId && item.fieldId === fieldId,
      )
      return entry === undefined ? undefined : { visible: entry.visible, editable: entry.editable }
    },
    setFieldPerm: (formId, fieldId, patch, sourceMenuId) => projection.setFieldPerm(formId, fieldId, patch, sourceMenuId),
    setDataScope: (dictTypeId, policyType, config) =>
      projection.setDataScope(dictTypeId, policyType as DataScopePolicyType, config as DataScopePolicyItem[]),
    payloadPermissions: () => projection.config.permissionPayload.entries,
    payloadFields: () => projection.config.fieldPayload.entries,
    payloadDataScopes: () => projection.config.dataScopePayload.entries,
    idempotencyKey: (kind) => projection.idempotencyKey(kind as 'perm' | 'field' | 'scope'),
    bindUsers: (list) => projection.bindUsers(list),
    userIds: () => projection.users.value.map((user) => user.id),
    save: async () => projection.save(),
    retry: async () => projection.retry(),
    discard: () => projection.discard(),
    refreshAccess: async () => projection.refreshAccess(),
    errorTargetTab: () => projection.errorTarget.value?.tab,
  }
}

describePermissionConfigContract('授权编排契约（BasePermissionConfig，新口径）', permissionTarget)

/** 样例元数据。 */
const METADATA: PermissionMetadata = {
  menus: [
    { id: 'menu:user', name: '用户管理', children: [{ id: 'menu:user:list', name: '用户列表' }] },
    { id: 'menu:orphan', name: '未挂接菜单' },
  ],
  forms: [
    { id: 'form:user', name: '用户表单', menuIds: ['menu:user', 'menu:user:list'] },
    { id: 'form:free', name: '无入口表单', menuIds: [] },
  ],
  actions: [{ id: 'act:user:create', name: '新增用户' }],
  fields: [
    { id: 'field:name', name: '姓名' },
    { id: 'field:salary', name: '薪资' },
  ],
  formActions: { 'form:user': ['act:user:create'] },
  formFields: { 'form:user': ['field:name', 'field:salary'] },
  dictTypes: [{ id: 'dict:user', code: 'user', name: '用户字典' }],
  extensions: [],
}

describe('PermissionConfig 授权总容器件（新口径）', () => {
  it('占位态降级、不渲染页签', () => {
    const wrapper = mount(PermissionConfig)
    expect(wrapper.find('[data-test="permission-degrade"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="permission-tabs"]').exists()).toBe(false)
  })

  it('就绪态经 jobs 装载元数据并装配四页签；菜单勾选上抛 change', async () => {
    const wrapper = mount(PermissionConfig, {
      props: {
        ready: true,
        jobs: {
          loadMetadata: async () => METADATA,
          loadGrants: async () => ({ roleId: 'r1', entries: [], fieldEntries: [], dataScopeEntries: [], users: [] }),
        },
      },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="permission-tabs"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="node-menu:user"]').exists()).toBe(true)
    await wrapper.find('[data-test="node-check-menu:user"]').trigger('change')
    expect(wrapper.emitted('change')?.some((item) => (item[0] as { kind: string }).kind === 'menu')).toBe(true)
  })
})

describe('菜单权限件与菜单树', () => {
  it('树件三态、挂接缺失标记', () => {
    const tree = mount(PermissionTree, {
      props: {
        menus: METADATA.menus,
        forms: METADATA.forms,
        entries: [{ permType: 'menu', targetId: 'menu:user', sourceMenuId: '0' }],
      },
    })
    expect(tree.find('[data-test="node-menu:user"]').attributes('data-state')).toBe('checked')
    expect(tree.find('[data-test="node-menu:orphan"] [data-test="detached"]').exists()).toBe(true)
  })

  it('选中入口渲染操作 / 字段子页签', async () => {
    const panel = mount(MenuPermissionPanel, {
      props: {
        menus: METADATA.menus,
        forms: METADATA.forms,
        actions: METADATA.actions,
        fields: METADATA.fields,
        formActions: METADATA.formActions,
        formFields: METADATA.formFields,
        entries: [],
        selectedMenuId: 'menu:user',
        subTab: 'action',
      },
    })
    expect(panel.find('[data-test="menu-form-form:user"]').exists()).toBe(true)
    expect(panel.find('[data-test="action-act:user:create"]').exists()).toBe(true)
    await panel.find('[data-test="menu-subtab-field"]').trigger('click')
    expect(panel.emitted('update:subTab')?.[0]).toEqual(['field'])
  })
})

describe('表单权限件与操作 / 字段面板', () => {
  it('表单列表含无入口表单', () => {
    const panel = mount(FormPermissionPanel, {
      props: { forms: METADATA.forms, selectedFormId: 'form:free' },
    })
    expect(panel.find('[data-test="form-item-form:free"] [data-test="form-free"]').exists()).toBe(true)
  })

  it('操作面板：默认无、非本来源只读', () => {
    const panel = mount(ActionPermissionPanel, {
      props: {
        actions: METADATA.actions,
        entries: [{ permType: 'action', targetId: 'act:user:create', sourceMenuId: 'menu:user' }],
        sourceMenuId: '0',
      },
    })
    expect(panel.find('[data-test="action-check-act:user:create"]').attributes('checked')).toBeDefined()
    expect(panel.find('[data-test="action-readonly"]').exists()).toBe(true)
  })

  it('字段面板：默认全开、收窄与批量', async () => {
    const panel = mount(FieldPermissionPanel, {
      props: {
        formId: 'form:user',
        fields: METADATA.fields,
        fieldEntries: [{ formId: 'form:user', fieldId: 'field:name', visible: false, editable: true, sourceMenuId: '0' }],
      },
    })
    expect(panel.find('[data-test="field-visible-field:salary"]').attributes('checked')).toBeDefined()
    expect(panel.find('[data-test="field-visible-field:name"]').attributes('checked')).toBeUndefined()
    await panel.find('[data-test="field-batch-hidden"]').trigger('click')
    expect(panel.emitted('batch')?.[0]).toEqual([{ kind: 'visible', value: false }])
  })
})

describe('数据权限件与动态字典件', () => {
  it('扩展未注册不显示该子页签', () => {
    const panel = mount(DataScopePanel, {
      props: { dictTypes: METADATA.dictTypes, extensions: [], selectedDictTypeId: 'dict:user', policy: 'select' },
    })
    expect(panel.find('[data-test="policy-extension"]').exists()).toBe(false)
    expect(panel.find('[data-test="policy-select"]').exists()).toBe(true)
  })

  it('匹配通配符越界触发校验提示', async () => {
    const panel = mount(DataScopePanel, {
      props: {
        dictTypes: METADATA.dictTypes,
        entries: [
          {
            dictTypeId: 'dict:user',
            policyType: 'match',
            config: [{ field: 'code', pattern: 'a=b' }],
          },
        ],
        selectedDictTypeId: 'dict:user',
        policy: 'match',
        ready: false,
      },
    })
    await panel.find('[data-test="match-pattern"]').trigger('change')
    const validated = panel.emitted('validate')
    expect(validated?.[0]?.[0]).toEqual({
      policyType: 'match',
      message: '匹配值仅允许 * ? 与中英文 / 数字 / 下划线',
    })
  })

  it('动态字典件无数据源时为空态', () => {
    const picker = mount(DynamicDictPicker, { props: { dictType: 'user' } })
    expect(picker.find('[data-test="empty"]').exists()).toBe(true)
  })
})

describe('角色分配件', () => {
  it('已分配列表与计数、选择用户弹窗', async () => {
    const panel = mount(RoleAssignPanel, {
      props: {
        users: [{ id: 'u1', username: 'zhang', name: '张三', status: 'enabled' }],
        candidates: [{ id: 'u2', username: 'li', name: '李四', status: 'enabled' }],
      },
    })
    expect(panel.find('[data-test="role-assign-count"]').text()).toContain('已分配 1')
    await panel.find('[data-test="role-assign-open"]').trigger('click')
    expect(panel.find('[data-test="role-assign-dialog"]').exists()).toBe(true)
    await panel.find('[data-test="candidate-u2"] input').trigger('change')
    await panel.find('[data-test="role-assign-confirm"]').trigger('click')
    expect(panel.emitted('bind')?.[0]?.[0]).toHaveLength(1)
  })

  it('移除已分配用户', async () => {
    const panel = mount(RoleAssignPanel, {
      props: { users: [{ id: 'u1', username: 'zhang', name: '张三', status: 'enabled' }] },
    })
    await panel.find('[data-test="role-assign-unbind"]').trigger('click')
    expect(panel.emitted('unbind')?.[0]).toEqual([{ id: 'u1' }])
  })
})
