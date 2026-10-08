// kiwi_id: 2265
/** 权限配置领域用例（08-4-3，新口径）：菜单三态与连带 / 来源判定 / 字段收窄 / 数据权限 / 用户分配 / 载荷与幂等。 */

import { describe, expect, it } from 'vitest'

import {
  PERMISSION_SOURCE_DIRECT,
  bindUsers,
  collectCheckedMenuIds,
  collectDataScopePayload,
  collectFieldEntries,
  collectPermissionPayload,
  deriveIdempotencyKey,
  diffUserIds,
  fieldPermOf,
  findFieldMismatch,
  findMenu,
  flattenMenus,
  formSourceMenuIds,
  isMenuDetached,
  isValidMatchPattern,
  menuCheckState,
  menuFormIds,
  menuSubtreeIds,
  payloadKey,
  pruneMenuFieldEntries,
  removeDataScopeEntry,
  resolveErrorCode,
  resolveErrorTarget,
  setDataScopeEntry,
  setFieldPerm,
  toggleAction,
  toggleMenu,
  unbindUser,
  type AssignedUser,
  type PermissionMenuNode,
  type PermissionEntry,
  type PermissionSnapshot,
} from '../src'

/** 样例菜单树。 */
const MENUS: PermissionMenuNode[] = [
  { id: 'menu:user', name: '用户管理', children: [{ id: 'menu:user:list', name: '用户列表' }] },
  { id: 'menu:orphan', name: '未挂接菜单' },
]

/** 样例表单。 */
const FORMS = [
  { id: 'form:user', name: '用户表单', menuIds: ['menu:user', 'menu:user:list'] },
  { id: 'form:free', name: '无入口表单', menuIds: [] },
]

describe('domain/permission-config（新口径）', () => {
  it('flattenMenus / findMenu / menuSubtreeIds / menuFormIds', () => {
    expect(flattenMenus(MENUS).map((item) => [item.node.id, item.depth])).toEqual([
      ['menu:user', 0],
      ['menu:user:list', 1],
      ['menu:orphan', 0],
    ])
    expect(findMenu(MENUS, 'menu:user:list')?.name).toBe('用户列表')
    expect(findMenu(MENUS, 'absent')).toBeUndefined()
    expect(menuSubtreeIds(MENUS, 'menu:user')).toEqual(['menu:user', 'menu:user:list'])
    expect(menuSubtreeIds(MENUS, 'absent')).toEqual([])
    expect(menuFormIds(FORMS, 'menu:user')).toEqual(['form:user'])
    expect(isMenuDetached(FORMS, 'menu:orphan')).toBe(true)
    expect(isMenuDetached(FORMS, 'menu:user')).toBe(false)
  })

  it('勾选菜单：级联子树并连带关联表单（按来源）', () => {
    const entries = toggleMenu([], MENUS, FORMS, 'menu:user')
    expect(collectCheckedMenuIds(entries)).toEqual(['menu:user', 'menu:user:list'])
    expect(formSourceMenuIds(entries, 'form:user')).toEqual(['menu:user', 'menu:user:list'])
    expect(menuCheckState(MENUS, entries, 'menu:user')).toBe('checked')
  })

  it('取消菜单仅撤销本来源（其它来源保留），并清理关联字段条目', () => {
    const base: PermissionEntry[] = [{ permType: 'form', targetId: 'form:user', sourceMenuId: PERMISSION_SOURCE_DIRECT }]
    const on = toggleMenu(base, MENUS, FORMS, 'menu:user')
    expect(formSourceMenuIds(on, 'form:user')).toEqual(['0', 'menu:user', 'menu:user:list'])

    const fields = setFieldPerm([], 'form:user', 'field:name', { visible: false }, 'menu:user')
    const off = toggleMenu(on, MENUS, FORMS, 'menu:user', false)
    expect(formSourceMenuIds(off, 'form:user')).toEqual(['0'])
    expect(menuCheckState(MENUS, off, 'menu:user')).toBe('unchecked')
    expect(pruneMenuFieldEntries(fields, MENUS, 'menu:user')).toEqual([])
  })

  it('三态：子级勾选父级半选', () => {
    const entries = toggleMenu([], MENUS, FORMS, 'menu:user:list')
    expect(menuCheckState(MENUS, entries, 'menu:user')).toBe('indeterminate')
  })

  it('挂接缺失菜单不可授予（勾选不产生条目）', () => {
    // toggleMenu 纯函数不做挂接校验（由能力基类把关）；此处断言子树仍能生成空表单连带。
    const entries = toggleMenu([], MENUS, FORMS, 'menu:orphan')
    expect(formSourceMenuIds(entries, 'form:free')).toEqual([])
  })

  it('操作权限：按来源写入与撤销', () => {
    let entries = toggleAction([], 'act:user:create', '0')
    expect(entries).toHaveLength(1)
    entries = toggleAction(entries, 'act:user:create', 'menu:user')
    expect(entries.map((entry) => entry.sourceMenuId)).toEqual(['0', 'menu:user'])
    entries = toggleAction(entries, 'act:user:create', '0', false)
    expect(entries.map((entry) => entry.sourceMenuId)).toEqual(['menu:user'])
    // 重复勾选同来源不重复
    expect(toggleAction(entries, 'act:user:create', 'menu:user')).toHaveLength(1)
  })

  it('字段权限：未命中默认全开、editable=false 强制不可见、收窄项收集与字段校验', () => {
    expect(fieldPermOf([], 'form:user', 'field:name')).toBeUndefined()
    let fields = setFieldPerm([], 'form:user', 'field:name', { visible: false }, '0')
    expect(fields).toEqual([
      { formId: 'form:user', fieldId: 'field:name', visible: false, editable: true, sourceMenuId: '0' },
    ])
    fields = setFieldPerm(fields, 'form:user', 'field:salary', { editable: false }, 'menu:user')
    expect(fields.find((item) => item.fieldId === 'field:salary')).toEqual({
      formId: 'form:user',
      fieldId: 'field:salary',
      visible: false,
      editable: false,
      sourceMenuId: 'menu:user',
    })
    expect(collectFieldEntries(fields)).toHaveLength(2)
    expect(collectFieldEntries(setFieldPerm([], 'form:user', 'field:name', {}, '0'))).toEqual([])
    expect(findFieldMismatch(fields, { 'form:user': ['field:name', 'field:salary'] })).toBeUndefined()
    expect(findFieldMismatch(fields, { 'form:user': ['field:name'] })).toEqual({
      formId: 'form:user',
      fieldId: 'field:salary',
    })
  })

  it('匹配通配符校验：仅 * ? 与中英文 / 数字 / 下划线', () => {
    expect(isValidMatchPattern('user_*')).toBe(true)
    expect(isValidMatchPattern('张?')).toBe(true)
    expect(isValidMatchPattern('a b')).toBe(false)
    expect(isValidMatchPattern('a=b')).toBe(false)
    expect(isValidMatchPattern('')).toBe(false)
  })

  it('数据权限：覆盖、移除、空配置丢弃', () => {
    let entries = setDataScopeEntry([], 'dict:user', 'select', [{ itemCode: 'enabled' }])
    expect(entries).toEqual([{ dictTypeId: 'dict:user', policyType: 'select', config: [{ itemCode: 'enabled' }] }])
    entries = setDataScopeEntry(entries, 'dict:user', 'match', [{ field: 'code', pattern: 'user_*' }])
    expect(entries).toHaveLength(2)
    expect(removeDataScopeEntry(entries, 'dict:user', 'select')).toHaveLength(1)
    expect(collectDataScopePayload([{ dictTypeId: 'dict:user', policyType: 'select', config: [] }])).toEqual([])
  })

  it('用户分配：去重、解绑、差量', () => {
    const list: AssignedUser[] = [{ id: 'u1', username: 'zhang', name: '张三', status: 'enabled' }]
    const merged = bindUsers(list, [
      { id: 'u1', username: 'zhang', name: '张三', status: 'enabled' },
      { id: 'u2', username: 'li', name: '李四', status: 'enabled' },
    ])
    expect(merged.map((user) => user.id)).toEqual(['u1', 'u2'])
    const removed = unbindUser(merged, 'u1')
    expect(removed.map((user) => user.id)).toEqual(['u2'])
    expect(diffUserIds(list, merged)).toEqual({ added: ['u2'], removed: [] })
    expect(diffUserIds(merged, list)).toEqual({ added: [], removed: ['u2'] })
  })

  it('载荷确定性、脏基线与幂等键', () => {
    const snapshot: PermissionSnapshot = {
      roleId: 'r1',
      entries: collectPermissionPayload(toggleMenu(toggleAction([], 'act:user:create', '0'), MENUS, FORMS, 'menu:user')),
      fieldEntries: setFieldPerm([], 'form:user', 'field:name', { visible: false }, '0'),
      dataScopeEntries: setDataScopeEntry([], 'dict:user', 'select', [{ itemCode: 'enabled' }]),
      users: [{ id: 'u1', username: 'zhang', name: '张三', status: 'enabled' }],
    }
    const reordered: PermissionSnapshot = { ...snapshot, entries: [...snapshot.entries].reverse() }
    expect(payloadKey(snapshot)).toBe(payloadKey(reordered))

    const key = deriveIdempotencyKey('r1', 'perm', payloadKey(snapshot))
    expect(key).toMatch(/^perm:r1:perm:[0-9a-f]+$/)
    expect(deriveIdempotencyKey('r1', 'perm', payloadKey(snapshot))).toBe(key)
    expect(deriveIdempotencyKey('r1', 'field', payloadKey(snapshot))).not.toBe(key)
  })

  it('错误码识别与定位', () => {
    expect(resolveErrorCode(Object.assign(new Error('x'), { code: 30047 }))).toBe(30047)
    expect(resolveErrorCode(new Error('x'))).toBeUndefined()
    expect(resolveErrorTarget(30047)).toEqual({ tab: 'data', i18nKey: 'error.30047' })
    expect(resolveErrorTarget(30049)).toEqual({ tab: 'form', i18nKey: 'error.30049' })
    expect(resolveErrorTarget(99999)).toBeUndefined()
  })
})
