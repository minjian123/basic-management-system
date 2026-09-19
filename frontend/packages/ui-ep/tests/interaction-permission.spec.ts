// kiwi_id: 768
/** 权限配置组件用例（08_04_02）：契约套件驱动 + 五件组件（授权总容器 / 权限树 / 字段权限矩阵与单元格 / 数据范围 / 主体绑定）。 */

import {
  BaseAccess,
  applyPermissionCheck,
  type FieldPermRow,
  type PermissionJobs,
  type PermissionSnapshot,
  type PermissionSubject,
} from '@bms/core'
import {
  describePermissionConfigContract,
  type PermissionContractHandlers,
  type PermissionContractPayload,
  type PermissionConfigContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import {
  DataScopePanel,
  FieldPermCell,
  FieldPermMatrix,
  PermissionConfig,
  PermissionTree,
  SubjectBinding,
  useBaseFieldPerm,
  useBasePermissionConfig,
} from '../src'

/** 样例授权快照（角色 `r1`；含挂接缺失菜单）。 */
const SNAPSHOT: PermissionSnapshot = {
  roleId: 'r1',
  nodes: [
    {
      key: 'menu:user',
      label: '用户管理',
      type: 'menu',
      children: [
        {
          key: 'form:user',
          label: '用户表单',
          type: 'form',
          children: [
            { key: 'biz:user', label: '用户业务', type: 'business' },
            { key: 'act:user:create', label: '新增用户', type: 'action' },
          ],
        },
      ],
    },
    { key: 'menu:orphan', label: '未挂接菜单', type: 'menu', detached: true },
  ],
  fieldPerms: [
    {
      formKey: 'form:user',
      formLabel: '用户表单',
      fields: [
        { key: 'name', label: '姓名', visible: true, editable: true },
        { key: 'salary', label: '薪资', visible: true, editable: true },
      ],
    },
  ],
  dataScopes: [{ actionKey: 'act:user:list', actionLabel: '查询', expression: '' }],
  subjects: [],
}

/** 样例字段权限矩阵（运行态口径）。 */
const FIELD_ROWS: FieldPermRow[] = [
  {
    formKey: 'form:user',
    formLabel: '用户表单',
    fields: [
      { key: 'name', label: '姓名', visible: true, editable: true },
      { key: 'salary', label: '薪资', visible: true, editable: true },
    ],
  },
]

/** 权限上下文样例。 */
class SampleAccess extends BaseAccess {}

/**
 * 在独立作用域内执行（组合式投影需要活动作用域）。
 *
 * @param factory 工厂函数。
 */
function scoped<T>(factory: () => T): T {
  const scope = effectScope()
  const result = scope.run(factory)
  if (result === undefined) {
    throw new Error('effectScope 未返回结果')
  }
  return result
}

/** 授权编排契约目标（`useBasePermissionConfig` 投影）。 */
function permissionTarget(): PermissionConfigContractTarget {
  return scoped(() => {
    const api = useBasePermissionConfig()
    const access = new SampleAccess()
    const handlers: PermissionContractHandlers = {}
    return {
      get ready() {
        return api.ready.value
      },
      get degraded() {
        return api.degraded.value
      },
      get disabled() {
        return api.disabled.value
      },
      get requestCount() {
        return api.requestCount.value
      },
      get dirty() {
        return api.dirty.value
      },
      get phase() {
        return api.phase.value
      },
      get canSave() {
        return api.canSave.value
      },
      get pendingAccessRefresh() {
        return api.pendingAccessRefresh.value
      },
      get accessCodes() {
        return access.codes
      },
      setReady: (value: boolean) => api.setReady(value),
      setAccess: (codes: readonly string[]) => {
        access.setCodes(codes)
        api.setAccess(access)
      },
      setHandlers: (next) => {
        handlers.load = undefined
        handlers.submit = undefined
        handlers.loadPermissionCodes = undefined
        Object.assign(handlers, next)
        api.setJobs({
          load:
            handlers.load === undefined
              ? undefined
              : async (input) => (await handlers.load?.(input)) as unknown as PermissionSnapshot,
          submit: handlers.submit === undefined ? undefined : async (input) => (await handlers.submit?.(input)) ?? {},
          loadPermissionCodes:
            handlers.loadPermissionCodes === undefined
              ? undefined
              : async () => (await handlers.loadPermissionCodes?.()) ?? [],
        })
      },
      load: () => api.load(),
      toggleNode: (key: string, checked?: boolean) => api.toggleNode(key, checked),
      checkState: (key: string) => api.checkState(key),
      granted: () => api.granted.value,
      fieldPerm: (formKey: string, fieldKey: string) => {
        const field = api.fieldPerms.value
          .find((row) => row.formKey === formKey)
          ?.fields.find((item) => item.key === fieldKey)
        return field === undefined ? undefined : { visible: field.visible, editable: field.editable }
      },
      setFieldPerm: (formKey, fieldKey, patch) => api.setFieldPerm(formKey, fieldKey, patch),
      scopeExpression: (actionKey: string) =>
        api.dataScopes.value.find((row) => row.actionKey === actionKey)?.expression ?? '',
      setDataScope: (actionKey: string, expression: string) => api.setDataScope(actionKey, expression),
      subjectIds: () => api.subjects.value.map((item) => item.id),
      bindSubject: (subject: { id: string; type: string; name: string }) =>
        api.bindSubject({ ...subject, type: subject.type as PermissionSubject['type'] }),
      payload: () => api.config.payload as unknown as PermissionContractPayload,
      idempotencyKey: () => api.config.idempotencyKey,
      save: () => api.save(),
      retry: () => api.retry(),
      discard: () => api.discard(),
      refreshAccess: () => api.refreshAccess(),
      errorTargetTab: () => api.errorTarget.value?.tab,
    }
  })
}

describePermissionConfigContract('授权编排契约（BasePermissionConfig）', permissionTarget)

describe('useBasePermissionConfig 投影', () => {
  it('装载即记基线、受控处理函数注入与就绪联动', () => {
    const api = scoped(() => useBasePermissionConfig({ ready: true, snapshot: SNAPSHOT }))
    expect(api.ready.value).toBe(true)
    expect(api.degraded.value).toBe(false)
    expect(api.disabled.value).toBe(false)
    expect(api.dirty.value).toBe(false)
    expect(api.nodes.value).toHaveLength(2)
    expect(api.canSave.value).toBe(true)
    expect(api.loadReady.value).toBe(false)

    const access = new SampleAccess()
    api.setAccess(access)
    expect(api.canSave.value).toBe(false)
    access.setCodes(['role:grant'])
    api.setAccess(access)
    expect(api.canSave.value).toBe(true)

    api.setJobs({ submit: async () => ({ recordVersion: 1 }) })
    expect(api.submitReady.value).toBe(true)
  })
})

describe('useBaseFieldPerm 投影', () => {
  it('可见 / 可编辑三态与生效禁用', () => {
    const perm = scoped(() => useBaseFieldPerm({ visible: false, editable: true }))
    expect(perm.permVisible.value).toBe(false)
    expect(perm.rendered.value).toBe(false)
    expect(perm.editable.value).toBe(true)

    perm.applyPerm({ visible: true, editable: false })
    expect(perm.permVisible.value).toBe(true)
    expect(perm.rendered.value).toBe(true)
    expect(perm.editable.value).toBe(false)
    expect(perm.effectiveDisabled.value).toBe(true)
  })
})

describe('PermissionTree 权限树件', () => {
  it('渲染推导只读标识、挂接缺失禁用与空态', () => {
    const wrapper = mount(PermissionTree, { props: { nodes: SNAPSHOT.nodes } })
    expect(wrapper.get('[data-test="node-biz:user"] [data-test="derived"]').text()).toBe('推导')
    expect(wrapper.get('[data-test="node-check-biz:user"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="node-menu:orphan"] [data-test="detached"]').text()).toBe('未挂接')
    expect(wrapper.get('[data-test="node-check-menu:orphan"]').attributes('disabled')).toBeDefined()

    const empty = mount(PermissionTree, { props: {} })
    expect(empty.get('[data-test="empty"]').text()).toBe('暂无权限数据')
  })

  it('三态：直接勾选子级时父级半选并渲染半选标记', async () => {
    const wrapper = mount(PermissionTree, { props: { nodes: SNAPSHOT.nodes } })
    await wrapper.get('[data-test="node-check-form:user"]').trigger('change')
    expect(wrapper.emitted('check')?.[0]).toEqual([{ key: 'form:user', checked: true }])

    const half = mount(PermissionTree, { props: { nodes: applyPermissionCheck(SNAPSHOT.nodes, 'form:user') } })
    expect(half.get('[data-test="node-menu:user"]').attributes('data-state')).toBe('indeterminate')
    expect(half.find('[data-test="node-menu:user"] [data-test="indeterminate"]').exists()).toBe(true)
  })

  it('搜索过滤（命中父链）与展开收起', async () => {
    const wrapper = mount(PermissionTree, { props: { nodes: SNAPSHOT.nodes } })
    await wrapper.get('[data-test="tree-search"]').setValue('用户业务')
    expect(wrapper.emitted('update:keyword')?.[0]).toEqual(['用户业务'])

    await wrapper.setProps({ keyword: '用户业务' })
    expect(wrapper.find('[data-test="node-menu:user"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="node-biz:user"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="node-menu:orphan"]').exists()).toBe(false)

    await wrapper.setProps({ keyword: '' })
    await wrapper.get('[data-test="tree-toggle-all"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-test="node-biz:user"]').exists()).toBe(false)
  })
})

describe('FieldPermMatrix 字段权限矩阵与 FieldPermCell 单元格', () => {
  it('默认全开、收窄上抛与批量', async () => {
    const wrapper = mount(FieldPermMatrix, { props: { rows: FIELD_ROWS } })
    expect(wrapper.get('[data-test="form-form:user"]').text()).toContain('用户表单')
    expect(
      wrapper.get('[data-test="field-form:user-name"] [data-test="field-perm-cell"]').attributes('data-visible'),
    ).toBe('true')

    await wrapper.get('[data-test="field-form:user-salary"] input').trigger('change')
    expect(wrapper.emitted('change')?.[0]).toEqual([
      { formKey: 'form:user', fieldKey: 'salary', key: 'visible', value: false },
    ])

    await wrapper.get('[data-test="batch-invisible"]').trigger('click')
    expect(wrapper.emitted('batch')?.[0]).toEqual([{ key: 'visible', value: false }])
  })

  it('仅显示已收窄过滤与分页', async () => {
    const rows: FieldPermRow[] = [
      { ...FIELD_ROWS[0]!, fields: [{ ...FIELD_ROWS[0]!.fields[0]!, visible: false }] },
      { ...FIELD_ROWS[0]!, formKey: 'form:other', formLabel: '其他表单' },
    ]
    const wrapper = mount(FieldPermMatrix, { props: { rows, onlyNarrowed: true } })
    expect(wrapper.find('[data-test="form-form:user"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="form-form:other"]').exists()).toBe(false)

    const paged = mount(FieldPermMatrix, { props: { rows, pageSize: 1 } })
    expect(paged.findAll('[data-test^="form-form:"]')).toHaveLength(1)
    await paged.get('[data-test="page-next"]').trigger('click')
    expect(paged.emitted('update:page')?.[0]).toEqual([2])
  })

  it('单元格：不可见时不渲染可编辑项，禁用时置灰', () => {
    const hidden = mount(FieldPermCell, {
      props: { formKey: 'f1', field: { key: 'a', label: 'A', visible: false, editable: true } },
    })
    expect(hidden.attributes('data-visible')).toBe('false')
    expect(hidden.find('[data-test="cell-editable"]').exists()).toBe(false)

    const readonly = mount(FieldPermCell, {
      props: { formKey: 'f1', field: { key: 'a', label: 'A', visible: true, editable: false } },
    })
    expect(readonly.get('[data-test="cell-editable"]').attributes('disabled')).toBeDefined()
  })
})

describe('DataScopePanel 数据范围件', () => {
  it('默认无数据权限、模板套用与表达式上抛', async () => {
    const wrapper = mount(DataScopePanel, {
      props: {
        rows: [{ actionKey: 'act:user:list', actionLabel: '查询', expression: '' }],
        templates: [{ key: 'self', label: '本人', expression: 'created_by = @current_user' }],
      },
    })
    expect(wrapper.get('[data-test="scope-summary"]').text()).toBe('无数据权限')

    await wrapper.get('[data-test="scope-template-self"]').trigger('click')
    expect(wrapper.emitted('apply-template')?.[0]).toEqual(['self'])
    expect(wrapper.emitted('change')?.[0]).toEqual([
      { actionKey: 'act:user:list', expression: 'created_by = @current_user' },
    ])
  })

  it('按动作切换与空态', async () => {
    const rows = [
      { actionKey: 'a:list', actionLabel: '查询', expression: 'dept_id = @current_dept' },
      { actionKey: 'b:list', actionLabel: '导出', expression: '' },
    ]
    const wrapper = mount(DataScopePanel, { props: { rows } })
    expect(wrapper.get('[data-test="scope-a:list"] [data-test="scope-summary"]').text()).toBe('dept_id = @current_dept')
    await wrapper.get('[data-test="scope-b:list"] button').trigger('click')
    expect(wrapper.emitted('update:activeKey')?.[0]).toEqual(['b:list'])

    const empty = mount(DataScopePanel, { props: {} })
    expect(empty.get('[data-test="empty"]').text()).toBe('暂无数据范围配置')
  })
})

describe('SubjectBinding 主体绑定件', () => {
  it('绑定 / 解绑与候选过滤（按类型页签）', async () => {
    const wrapper = mount(SubjectBinding, {
      props: {
        subjects: [{ id: 'u1', type: 'user', name: '张三' }],
        candidates: [
          { id: 'u2', type: 'user', name: '李四' },
          { id: 'p1', type: 'position', name: '主管' },
        ],
        limit: 3,
      },
    })
    await flushPromises()
    expect(wrapper.get('[data-test="subject-u1"]').text()).toBe('张三')
    expect(wrapper.find('[data-test="candidate-u2"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="candidate-p1"]').exists()).toBe(false)

    await wrapper.get('[data-test="candidate-u2"] button').trigger('click')
    expect(wrapper.emitted('bind')?.[0]?.[0]).toEqual({ id: 'u2', type: 'user', name: '李四' })

    await wrapper.get('[data-test="subject-unbind"]').trigger('click')
    expect(wrapper.emitted('unbind')?.[0]).toEqual([{ id: 'u1', type: 'user' }])

    await wrapper.get('[data-test="subject-tab-position"]').trigger('click')
    expect(wrapper.find('[data-test="candidate-p1"]').exists()).toBe(true)
  })

  it('上限提示与空态', async () => {
    const wrapper = mount(SubjectBinding, {
      props: {
        subjects: [
          { id: 'u1', type: 'user', name: '张三' },
          { id: 'u2', type: 'user', name: '李四' },
        ],
        candidates: [{ id: 'u3', type: 'user', name: '王五' }],
        limit: 2,
      },
    })
    await flushPromises()
    expect(wrapper.get('[data-test="subject-limit"]').text()).toBe('已达单主体上限')
    expect(wrapper.get('[data-test="candidate-u3"] button').attributes('disabled')).toBeDefined()

    const empty = mount(SubjectBinding, { props: {} })
    expect(empty.get('[data-test="empty"]').text()).toBe('暂无主体绑定')
  })
})

describe('PermissionConfig 授权总容器件', () => {
  /** 就绪态处理函数集。 */
  const jobs = (): PermissionJobs => ({
    load: async () => SNAPSHOT,
    submit: async () => ({ recordVersion: 5 }),
    loadPermissionCodes: async () => ['role:grant', 'user:create'],
  })

  it('未就绪：降级提示、操作禁用且注入处理函数也不请求', async () => {
    const load = vi.fn(async () => SNAPSHOT)
    const wrapper = mount(PermissionConfig, { props: { ready: false, jobs: { ...jobs(), load } } })
    await flushPromises()
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.get('[data-test="placeholder"]').text()).toContain('权限配置未就绪')
    expect(wrapper.find('[data-test="tabs"]').exists()).toBe(false)
    expect(load).not.toHaveBeenCalled()
  })

  it('就绪：自动取数、勾选联动与取消连带', async () => {
    const load = vi.fn(async () => SNAPSHOT)
    const wrapper = mount(PermissionConfig, { props: { ready: true, jobs: { ...jobs(), load } } })
    await flushPromises()
    expect(load).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-test="node-check-menu:user"]').trigger('change')
    await flushPromises()
    expect(wrapper.get('[data-test="node-form:user"]').attributes('data-state')).toBe('checked')
    expect(wrapper.get('[data-test="node-act:user:create"]').attributes('data-state')).toBe('unchecked')
    expect(wrapper.get('[data-test="dirty"]').text()).toBe('未保存')

    await wrapper.get('[data-test="node-check-act:user:create"]').trigger('change')
    await flushPromises()
    expect(wrapper.get('[data-test="node-act:user:create"]').attributes('data-state')).toBe('checked')

    await wrapper.get('[data-test="node-check-menu:user"]').trigger('change')
    await flushPromises()
    expect(wrapper.get('[data-test="node-act:user:create"]').attributes('data-state')).toBe('unchecked')
  })

  it('保存成功上抛 saved 并刷新权限上下文', async () => {
    const access = new SampleAccess()
    access.setCodes(['role:grant'])
    const wrapper = mount(PermissionConfig, { props: { ready: true, access, jobs: jobs() } })
    await flushPromises()
    await wrapper.get('[data-test="node-check-menu:user"]').trigger('change')
    await flushPromises()

    await wrapper.get('[data-test="save"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('saved')?.[0]?.[0]).toEqual({ recordVersion: 5 })
    expect(access.codes).toContain('user:create')
    expect(wrapper.find('[data-test="refresh-pending"]').exists()).toBe(false)
  })

  it('未注入取码处理时提示待刷新；提交失败按错误码定位并可重试', async () => {
    const wrapper = mount(PermissionConfig, {
      props: {
        ready: true,
        jobs: {
          load: async () => SNAPSHOT,
          submit: async () => {
            throw Object.assign(new Error('规则表达式非法'), { code: 30047 })
          },
        },
      },
    })
    await flushPromises()
    await wrapper.get('[data-test="node-check-menu:user"]').trigger('change')
    await flushPromises()

    await wrapper.get('[data-test="save"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('failed')?.[0]?.[0]).toMatchObject({ message: '规则表达式非法', target: { tab: 'scope' } })
    expect(wrapper.get('[data-test="error-target"]').text()).toContain('scope')
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="dirty"]').exists()).toBe(true)
  })

  it('页签受控：点击只上抛 update:tab，受控值变化切换面板', async () => {
    const wrapper = mount(PermissionConfig, {
      props: { ready: true, tab: 'tree', jobs: { load: async () => SNAPSHOT, submit: async () => ({}) } },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="panel-tree"]').exists()).toBe(true)

    await wrapper.get('[data-test="tab-field"]').trigger('click')
    expect(wrapper.emitted('update:tab')?.[0]).toEqual(['field'])
    expect(wrapper.find('[data-test="panel-tree"]').exists()).toBe(true)

    await wrapper.setProps({ tab: 'field' })
    expect(wrapper.find('[data-test="panel-field"]').exists()).toBe(true)

    await wrapper.setProps({ tab: 'scope' })
    await flushPromises()
    expect(wrapper.find('[data-test="panel-scope"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="scope-act:user:list"]').exists()).toBe(true)

    await wrapper.setProps({ tab: 'subject' })
    await flushPromises()
    expect(wrapper.find('[data-test="panel-subject"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="subject-binding"]').exists()).toBe(true)
  })

  it('受控覆盖：外部传入四类授权与脏标记', async () => {
    const wrapper = mount(PermissionConfig, {
      props: { ready: true, dirty: true, treeNodes: SNAPSHOT.nodes, fieldPerms: FIELD_ROWS },
    })
    await flushPromises()
    expect(wrapper.get('[data-test="dirty"]').text()).toBe('未保存')
    expect(wrapper.find('[data-test="node-menu:user"]').exists()).toBe(true)

    await wrapper.setProps({ tab: 'field' })
    expect(wrapper.get('[data-test="form-form:user"]').text()).toContain('用户表单')
  })
})
