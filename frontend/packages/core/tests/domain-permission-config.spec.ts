// kiwi_id: 767
/** 权限配置领域纯函数用例（08-4-1）：隐含推导 / 三态与级联 / 字段收窄 / 数据范围 / 主体绑定 / 脏基线 / 幂等键 / 错误码定位。 */

import { describe, expect, it } from 'vitest'

import {
  BaseError,
  PERMISSION_ERROR_TARGETS,
  PERMISSION_SUBJECT_LIMIT,
  applyPermissionCheck,
  bindSubject,
  collectDataScopes,
  collectFieldEntries,
  collectPayload,
  deriveGranted,
  deriveIdempotencyKey,
  findFieldMismatch,
  findFieldPerm,
  findPermissionNode,
  flattenPermissionTree,
  isGrantable,
  normalizeFieldPerms,
  payloadKey,
  resolveCheckState,
  resolveErrorCode,
  resolveErrorTarget,
  setDataScope,
  setFieldPerm,
  unbindSubject,
  type PermissionSnapshot,
} from '../src'

/** 样例权限树（菜单 → 表单 → 业务 / 动作，另含挂接缺失菜单）。 */
function sampleNodes() {
  return [
    {
      key: 'menu:user',
      label: '用户管理',
      type: 'menu' as const,
      children: [
        {
          key: 'form:user',
          label: '用户表单',
          type: 'form' as const,
          children: [
            { key: 'biz:user', label: '用户业务', type: 'business' as const },
            { key: 'act:user:create', label: '新增用户', type: 'action' as const },
          ],
        },
      ],
    },
    { key: 'menu:orphan', label: '未挂接菜单', type: 'menu' as const, detached: true },
  ]
}

/** 样例授权快照。 */
function sampleSnapshot(): PermissionSnapshot {
  return {
    roleId: 'r1',
    nodes: sampleNodes(),
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
}

describe('权限树推导', () => {
  it('扁平化保留层级深度与顺序', () => {
    const flat = flattenPermissionTree(sampleNodes())
    expect(flat.map((entry) => entry.node.key)).toEqual([
      'menu:user',
      'form:user',
      'biz:user',
      'act:user:create',
      'menu:orphan',
    ])
    expect(flat.map((entry) => entry.depth)).toEqual([0, 1, 2, 2, 0])
  })

  it('按节点键查找（根 / 子 / 未命中）', () => {
    const nodes = sampleNodes()
    expect(findPermissionNode(nodes, 'menu:user')?.label).toBe('用户管理')
    expect(findPermissionNode(nodes, 'act:user:create')?.type).toBe('action')
    expect(findPermissionNode(nodes, 'absent')).toBeUndefined()
  })

  it('可授予判定：业务只读、挂接缺失不可授予', () => {
    const nodes = sampleNodes()
    expect(isGrantable(findPermissionNode(nodes, 'menu:user')!)).toBe(true)
    expect(isGrantable(findPermissionNode(nodes, 'form:user')!)).toBe(true)
    expect(isGrantable(findPermissionNode(nodes, 'biz:user')!)).toBe(false)
    expect(isGrantable(findPermissionNode(nodes, 'menu:orphan')!)).toBe(false)
  })

  it('三态：自身勾选 → 已选；有后代勾选 → 半选；否则未选', () => {
    const nodes = sampleNodes()
    expect(resolveCheckState(findPermissionNode(nodes, 'menu:user')!)).toBe('unchecked')
    expect(resolveCheckState(findPermissionNode(nodes, 'biz:user')!)).toBe('unchecked')

    const formChecked = applyPermissionCheck(nodes, 'form:user')
    expect(resolveCheckState(findPermissionNode(formChecked, 'form:user')!)).toBe('checked')
    expect(resolveCheckState(findPermissionNode(formChecked, 'menu:user')!)).toBe('indeterminate')
    expect(resolveCheckState(findPermissionNode(formChecked, 'biz:user')!)).toBe('checked')
  })

  it('勾选菜单隐含表单与业务，但动作不联动（默认全无）', () => {
    const next = applyPermissionCheck(sampleNodes(), 'menu:user')
    expect(findPermissionNode(next, 'menu:user')?.checked).toBe(true)
    expect(findPermissionNode(next, 'form:user')?.checked).toBe(true)
    expect(findPermissionNode(next, 'biz:user')?.checked).toBe(true)
    expect(findPermissionNode(next, 'act:user:create')?.checked).toBeUndefined()
  })

  it('动作须显式勾选；取消菜单连带取消表单与动作', () => {
    const checked = applyPermissionCheck(applyPermissionCheck(sampleNodes(), 'menu:user'), 'act:user:create')
    expect(findPermissionNode(checked, 'act:user:create')?.checked).toBe(true)

    const cleared = applyPermissionCheck(checked, 'menu:user', false)
    expect(findPermissionNode(cleared, 'form:user')?.checked).toBe(false)
    expect(findPermissionNode(cleared, 'biz:user')?.checked).toBe(false)
    expect(findPermissionNode(cleared, 'act:user:create')?.checked).toBe(false)
  })

  it('业务只读与挂接缺失节点勾选不动作', () => {
    const nodes = sampleNodes()
    const readonly = applyPermissionCheck(nodes, 'biz:user')
    expect(findPermissionNode(readonly, 'biz:user')?.checked).toBeUndefined()

    const detached = applyPermissionCheck(nodes, 'menu:orphan')
    expect(findPermissionNode(detached, 'menu:orphan')?.checked).toBeUndefined()
  })

  it('级联为不可变更新（原树不被修改）', () => {
    const nodes = sampleNodes()
    const next = applyPermissionCheck(nodes, 'menu:user')
    expect(next).not.toBe(nodes)
    expect(findPermissionNode(nodes, 'form:user')?.checked).toBeUndefined()
    expect(findPermissionNode(next, 'form:user')?.checked).toBe(true)
  })

  it('勾选集合：菜单 / 表单 / 动作显式勾选 + 业务隐含推导（均升序）', () => {
    const nodes = applyPermissionCheck(applyPermissionCheck(sampleNodes(), 'menu:user'), 'act:user:create')
    expect(deriveGranted(nodes)).toEqual({
      menus: ['menu:user'],
      forms: ['form:user'],
      actions: ['act:user:create'],
      implied: ['biz:user'],
    })
    expect(deriveGranted(sampleNodes())).toEqual({ menus: [], forms: [], actions: [], implied: [] })
  })
})

describe('字段权限与数据范围', () => {
  it('默认全开：缺省的可见 / 可编辑补为真，显式收窄保留', () => {
    const rows = normalizeFieldPerms([
      {
        formKey: 'f1',
        formLabel: '表单',
        fields: [
          { key: 'a', label: 'A', visible: false, editable: false },
          { key: 'b', label: 'B' },
        ],
      },
    ])
    expect(rows[0]?.fields[0]).toMatchObject({ visible: false, editable: false })
    expect(rows[0]?.fields[1]).toMatchObject({ visible: true, editable: true })
  })

  it('按表单 + 字段查找与设置（未命中不改动）', () => {
    const rows = normalizeFieldPerms(sampleSnapshot().fieldPerms)
    expect(findFieldPerm(rows, 'form:user', 'name')?.visible).toBe(true)
    expect(findFieldPerm(rows, 'form:user', 'absent')).toBeUndefined()

    const next = setFieldPerm(rows, 'form:user', 'name', { visible: false })
    expect(findFieldPerm(next, 'form:user', 'name')).toEqual({
      key: 'name',
      label: '姓名',
      visible: false,
      editable: true,
    })
    expect(findFieldPerm(rows, 'form:user', 'name')?.visible).toBe(true)

    const untouched = setFieldPerm(rows, 'form:user', 'absent', { visible: false })
    expect(untouched).toEqual(rows)
  })

  it('字段收窄项：仅收窄入选并按表单 + 字段升序', () => {
    const rows = normalizeFieldPerms([
      {
        formKey: 'f2',
        formLabel: '表单二',
        fields: [{ key: 'b', label: 'B', visible: false, editable: true }],
      },
      {
        formKey: 'f1',
        formLabel: '表单一',
        fields: [
          { key: 'z', label: 'Z', visible: true, editable: true },
          { key: 'a', label: 'A', visible: true, editable: false },
        ],
      },
    ])
    expect(collectFieldEntries(rows)).toEqual([
      { formKey: 'f1', fieldKey: 'a', visible: true, editable: false },
      { formKey: 'f2', fieldKey: 'b', visible: false, editable: true },
    ])
  })

  it('字段归属校验：不匹配命中、未登记表单跳过', () => {
    const rows = normalizeFieldPerms(sampleSnapshot().fieldPerms)
    expect(findFieldMismatch(rows, { 'form:user': ['name'] })).toEqual({ formKey: 'form:user', fieldKey: 'salary' })
    expect(findFieldMismatch(rows, { 'form:user': ['name', 'salary'] })).toBeUndefined()
    expect(findFieldMismatch(rows, {})).toBeUndefined()
  })

  it('数据范围：默认无、非空表达式入选（去空白、按动作键升序）', () => {
    const rows = [
      { actionKey: 'b:list', actionLabel: 'B', expression: 'dept_id = @current_dept' },
      { actionKey: 'a:list', actionLabel: 'A', expression: '   ' },
      { actionKey: 'c:list', actionLabel: 'C', expression: 'user_id = @current_user' },
    ]
    expect(collectDataScopes(rows)).toEqual([
      { actionKey: 'b:list', expression: 'dept_id = @current_dept' },
      { actionKey: 'c:list', expression: 'user_id = @current_user' },
    ])

    const next = setDataScope(rows, 'a:list', 'tenant_id = @tenant')
    expect(next[1]?.expression).toBe('tenant_id = @tenant')
    expect(rows[1]?.expression).toBe('   ')
  })
})

describe('主体绑定', () => {
  it('新增去重、超上限不写入、上限 0 表示不限制', () => {
    const first = bindSubject([], { id: 'u1', type: 'user', name: '张三' })
    expect(first.applied).toBe(true)
    expect(first.list).toHaveLength(1)

    const duplicate = bindSubject(first.list, { id: 'u1', type: 'user', name: '张三' })
    expect(duplicate.applied).toBe(false)
    expect(duplicate.reason).toBe('duplicate')
    expect(duplicate.list).toHaveLength(1)

    const limitTwo = bindSubject(first.list, { id: 'u2', type: 'user', name: '李四' }, 1)
    expect(limitTwo.applied).toBe(false)
    expect(limitTwo.reason).toBe('limit')

    const unlimited = bindSubject(first.list, { id: 'u2', type: 'user', name: '李四' }, 0)
    expect(unlimited.applied).toBe(true)
    expect(unlimited.list).toHaveLength(2)
    expect(PERMISSION_SUBJECT_LIMIT).toBe(20)
  })

  it('解绑按标识（可带类型限定）', () => {
    const list = [
      { id: 'u1', type: 'user' as const, name: '张三' },
      { id: 'u1', type: 'dept' as const, name: '研发部' },
    ]
    expect(unbindSubject(list, 'u1')).toHaveLength(0)
    expect(unbindSubject(list, 'u1', 'user')).toEqual([{ id: 'u1', type: 'dept', name: '研发部' }])
    expect(unbindSubject(list, 'absent')).toHaveLength(2)
  })
})

describe('载荷与脏基线', () => {
  it('载荷：业务不进载荷、字段只收窄、数据范围只非空、主体排序', () => {
    const snapshot = sampleSnapshot()
    snapshot.nodes = applyPermissionCheck(snapshot.nodes, 'menu:user')
    snapshot.fieldPerms = normalizeFieldPerms(snapshot.fieldPerms)
    snapshot.fieldPerms = setFieldPerm(snapshot.fieldPerms, 'form:user', 'salary', { editable: false })
    snapshot.dataScopes = setDataScope(snapshot.dataScopes, 'act:user:list', 'dept_id = @current_dept')
    snapshot.subjects = [
      { id: 'u2', type: 'user', name: '李四' },
      { id: 'u1', type: 'user', name: '张三' },
    ]

    expect(collectPayload(snapshot)).toMatchObject({
      roleId: 'r1',
      menus: ['menu:user'],
      forms: ['form:user'],
      actions: [],
      fields: [{ formKey: 'form:user', fieldKey: 'salary', visible: true, editable: false }],
      dataScopes: [{ actionKey: 'act:user:list', expression: 'dept_id = @current_dept' }],
    })
    expect(collectPayload(snapshot).subjects.map((item) => item.id)).toEqual(['u1', 'u2'])
  })

  it('脏基线键与节点 / 字段 / 主体顺序无关，与授权语义相关', () => {
    const base = sampleSnapshot()
    const reordered = sampleSnapshot()
    reordered.nodes = applyPermissionCheck(reordered.nodes, 'menu:user')
    const same = sampleSnapshot()
    same.nodes = applyPermissionCheck(same.nodes, 'menu:user')
    same.subjects = [
      { id: 'u2', type: 'user', name: '李四' },
      { id: 'u1', type: 'user', name: '张三' },
    ]
    const reorderedSubjects = sampleSnapshot()
    reorderedSubjects.nodes = applyPermissionCheck(reorderedSubjects.nodes, 'menu:user')
    reorderedSubjects.subjects = [
      { id: 'u1', type: 'user', name: '张三' },
      { id: 'u2', type: 'user', name: '李四' },
    ]

    expect(payloadKey(base)).not.toBe(payloadKey(reordered))
    expect(payloadKey(same)).toBe(payloadKey(reorderedSubjects))
  })

  it('幂等键：内容派生的确定性取值', () => {
    const snapshot = sampleSnapshot()
    const key = payloadKey(snapshot)
    expect(deriveIdempotencyKey('r1', key)).toBe(deriveIdempotencyKey('r1', key))
    expect(deriveIdempotencyKey('r1', key)).toMatch(/^perm:r1:[0-9a-f]{8}$/)
    expect(deriveIdempotencyKey('r2', key)).not.toBe(deriveIdempotencyKey('r1', key))
    expect(deriveIdempotencyKey('r1', `${key} `)).not.toBe(deriveIdempotencyKey('r1', key))
    expect(deriveIdempotencyKey(undefined, key)).toMatch(/^perm:-:/)
  })
})

describe('错误码定位', () => {
  it('从错误对象解析错误码（BaseError / 普通对象带 code / 非对象）', () => {
    expect(resolveErrorCode(new BaseError(30047, '规则表达式非法'))).toBe(30047)
    expect(resolveErrorCode(Object.assign(new Error('x'), { code: 30049 }))).toBe(30049)
    expect(resolveErrorCode(new Error('x'))).toBeUndefined()
    expect(resolveErrorCode('boom')).toBeUndefined()
    expect(resolveErrorCode(undefined)).toBeUndefined()
  })

  it('错误码映射到页签（内置角色保护为整体错误）', () => {
    expect(resolveErrorTarget(30046)).toEqual({ tab: 'tree', i18nKey: 'error.30046' })
    expect(resolveErrorTarget(30047)?.tab).toBe('scope')
    expect(resolveErrorTarget(30048)?.tab).toBe('subject')
    expect(resolveErrorTarget(30049)?.tab).toBe('field')
    expect(resolveErrorTarget(30044)?.tab).toBe('subject')
    expect(resolveErrorTarget(30043)?.tab).toBeUndefined()
    expect(resolveErrorTarget(99999)).toBeUndefined()
    expect(resolveErrorTarget(undefined)).toBeUndefined()
    expect(Object.keys(PERMISSION_ERROR_TARGETS)).toEqual(['30043', '30044', '30046', '30047', '30048', '30049'])
  })
})
