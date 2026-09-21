// kiwi_id: 962
/** 组织领域纯函数用例（06_05）：归一 / 参数 / 解析 / 选择与上限 / 标记 / 标签摘要 / 路径与树 / 错误码。 */

import {
  ORG_DEFAULT_PAGE_SIZE,
  ORG_PAGE_SIZE_MAX,
  applyOrgSelection,
  buildOrgResolveQuery,
  buildOrgSearchQuery,
  clampOrgPage,
  clampOrgPageSize,
  findOrgDeptPath,
  findOrgItem,
  isBlankOrgKeyword,
  isOrgErrorCode,
  mergeOrgItems,
  normalizeOrgDeptTree,
  normalizeOrgIds,
  normalizeOrgItem,
  normalizeOrgItems,
  normalizeOrgKeyword,
  normalizeOrgKind,
  normalizeOrgNameRefs,
  normalizeOrgSearchQuery,
  normalizeOrgStatus,
  orgCacheKey,
  orgItemLabel,
  orgKindLabel,
  orgKindOfFieldType,
  orgLimitText,
  orgSelectionText,
  orgTagSummary,
  parseOrgDeptTree,
  parseOrgPage,
  removeOrgId,
  resolveOrgErrorText,
  toOrgTreeNodes,
  type OrgKind,
  type OrgOptionItem,
} from '../src'
import { describe, expect, it } from 'vitest'

describe('组织领域 · 归一', () => {
  it('对象类型与字段类型归一（org / dept → dept）', () => {
    expect(normalizeOrgKind('user')).toBe('user')
    expect(normalizeOrgKind(' POST ')).toBe('post')
    expect(normalizeOrgKind('org')).toBe('dept')
    expect(normalizeOrgKind('dept')).toBe('dept')
    expect(normalizeOrgKind('position')).toBeUndefined()
    expect(normalizeOrgKind(1)).toBeUndefined()
    expect(orgKindOfFieldType('user')).toBe('user')
    expect(orgKindOfFieldType('post')).toBe('post')
    expect(orgKindOfFieldType('org')).toBe('dept')
    expect(orgKindOfFieldType('dept')).toBe('dept')
    expect(orgKindOfFieldType('text')).toBeUndefined()
  })

  it('状态归一（非法回落 enabled）', () => {
    expect(normalizeOrgStatus('disabled')).toBe('disabled')
    expect(normalizeOrgStatus('enabled')).toBe('enabled')
    expect(normalizeOrgStatus(undefined)).toBe('enabled')
  })

  it('选项归一（用户昵称优先 / snake_case / 脱敏值原样）', () => {
    const item = normalizeOrgItem(
      {
        id: 1,
        nickname: '张三',
        username: 'zhangsan',
        dept_id: 'd1',
        status: 'disabled',
        phone: '138****8000',
        avatar: 'a.png',
        sort: 2,
      },
      'user',
    )
    expect(item).toEqual({
      id: '1',
      name: '张三',
      kind: 'user',
      status: 'disabled',
      deleted: false,
      username: 'zhangsan',
      deptId: 'd1',
      phone: '138****8000',
      avatar: 'a.png',
      sort: 2,
    })
    expect(normalizeOrgItem({ name: '无 id' }, 'user')).toBeUndefined()
    expect(normalizeOrgItem(null, 'user')).toBeUndefined()
  })

  it('选项归一（岗位名称 / 编码；名称缺失回落标识）', () => {
    const post = normalizeOrgItem({ id: 'p1', name: '研发经理', code: 'RD-MGR' }, 'post')
    expect(post?.name).toBe('研发经理')
    expect(post?.code).toBe('RD-MGR')
    const nameless = normalizeOrgItem({ id: 'p2' }, 'post')
    expect(nameless?.name).toBe('p2')
  })

  it('脏项剔除列表归一', () => {
    const items = normalizeOrgItems([{ id: 'u1', nickname: '甲' }, null, { nickname: '无 id' }], 'user')
    expect(items.map((item) => item.id)).toEqual(['u1'])
  })

  it('部门树归一（嵌套 children、脏节点剔除）', () => {
    const nodes = normalizeOrgDeptTree([
      { id: 'd1', name: '总部', status: 'enabled', children: [{ id: 'd2', name: '研发部' }, { name: '脏' }] },
      { name: '脏' },
    ])
    expect(nodes).toHaveLength(1)
    expect(nodes[0]?.children).toHaveLength(1)
    expect(nodes[0]?.children?.[0]?.status).toBe('enabled')
  })

  it('批量回显归一（未命中 exists=false → 已删除）', () => {
    const refs = normalizeOrgNameRefs(
      [
        { id: 'u1', name: '张三', target: 'user', exists: true, status: 'enabled' },
        { id: 'u9', name: '', target: 'user', exists: false, status: 'disabled' },
      ],
      'user',
    )
    expect(refs[0]?.deleted).toBe(false)
    expect(refs[1]?.deleted).toBe(true)
    expect(refs[1]?.name).toBe('u9')
  })

  it('受控值归一（去重 / 数字转字符串 / 空值）', () => {
    expect(normalizeOrgIds(['u1', 'u1', 2, '', null])).toEqual(['u1', '2'])
    expect(normalizeOrgIds(undefined)).toEqual([])
    expect(normalizeOrgIds('u1')).toEqual(['u1'])
  })
})

describe('组织领域 · 选择与展示', () => {
  const item = (id: string, name: string, extra: Partial<OrgOptionItem> = {}): OrgOptionItem => ({
    id,
    name,
    kind: 'user',
    status: 'enabled',
    deleted: false,
    ...extra,
  })

  it('选择应用：多选追加去重并按上限截断', () => {
    expect(applyOrgSelection(['u1'], ['u1', 'u2'], { multiple: true })).toEqual({
      ids: ['u1', 'u2'],
      exceeded: false,
    })
    expect(applyOrgSelection(['u1'], ['u2', 'u3'], { multiple: true, limit: 2 })).toEqual({
      ids: ['u1', 'u2'],
      exceeded: true,
    })
    expect(applyOrgSelection(['u1'], 'u3', { multiple: false })).toEqual({ ids: ['u3'], exceeded: false })
  })

  it('移除标识', () => {
    expect(removeOrgId(['u1', 'u2'], 'u1')).toEqual(['u2'])
  })

  it('选项合并（同 id 覆盖、保序）', () => {
    const merged = mergeOrgItems([item('u1', '甲')], [item('u1', '甲改'), item('u2', '乙')])
    expect(merged.map((entry) => entry.name)).toEqual(['甲改', '乙'])
    expect(findOrgItem(merged, 'u2')?.name).toBe('乙')
    expect(findOrgItem(merged, 'nobody')).toBeUndefined()
  })

  it('展示文案（已删除 / 停用标记、名称缺失回退标识）', () => {
    expect(orgItemLabel(item('u1', '张三'))).toBe('张三')
    expect(orgItemLabel(item('u2', '李四', { status: 'disabled' }))).toBe('李四（停用）')
    expect(orgItemLabel(item('u9', '王五', { deleted: true }))).toBe('王五（已删除）')
    expect(orgItemLabel(item('u9', '', { deleted: true }))).toBe('u9（已删除）')
  })

  it('选中回显文本与标签摘要', () => {
    const items = [item('u1', '张三'), item('u2', '李四')]
    expect(orgSelectionText(items)).toBe('张三、李四')
    expect(orgSelectionText([])).toBe('—')
    expect(orgTagSummary(items, 1)).toEqual({ visible: [items[0]], overflow: 1 })
    expect(orgTagSummary(items, 0)).toEqual({ visible: items, overflow: 0 })
  })

  it('类型标签与上限文案', () => {
    expect(orgKindLabel('user')).toBe('用户')
    expect(orgKindLabel('post')).toBe('岗位')
    expect(orgKindLabel('dept')).toBe('部门')
    expect(orgLimitText('user', 5)).toBe('最多选择 5 人')
    expect(orgLimitText('post', 3)).toBe('最多选择 3 个岗位')
    expect(orgLimitText('dept', 2)).toBe('最多选择 2 个部门')
  })
})

describe('组织领域 · 参数与解析', () => {
  it('查询归一（关键词去空白截断 / 页码页长夹取）', () => {
    const query = normalizeOrgSearchQuery({
      kind: 'user',
      keyword: ` ${'张'.repeat(120)} `,
      deptId: ' d1 ',
      includeChildren: true,
      status: 'enabled',
      page: -1,
      pageSize: 999,
    })
    expect(query.keyword.length).toBe(100)
    expect(query.deptId).toBe('d1')
    expect(query.includeChildren).toBe(true)
    expect(query.page).toBe(1)
    expect(query.pageSize).toBe(ORG_PAGE_SIZE_MAX)
  })

  it('查询参数构造（空值不传；含下级仅在部门过滤时传）', () => {
    expect(buildOrgSearchQuery({ kind: 'user', keyword: '张', deptId: 'd1', includeChildren: true, status: 'enabled' })).toEqual({
      keyword: '张',
      dept_id: 'd1',
      include_children: true,
      status: 'enabled',
      page: 1,
      size: ORG_DEFAULT_PAGE_SIZE,
    })
    expect(buildOrgSearchQuery({ kind: 'post', includeChildren: true })).toEqual({
      page: 1,
      size: ORG_DEFAULT_PAGE_SIZE,
    })
  })

  it('批量回显参数（target + id_in）', () => {
    expect(buildOrgResolveQuery('user', ['u1', 'u2'])).toEqual({ target: 'user', id_in: 'u1,u2' })
  })

  it('分页解析（list / items / 裸数组 / data 包装；total 回落条数）', () => {
    expect(parseOrgPage({ list: [{ id: 'u1' }], total: 9 }, 'user')).toEqual({
      items: [expect.objectContaining({ id: 'u1' })],
      total: 9,
    })
    expect(parseOrgPage({ items: [{ id: 'u2' }] }, 'user').total).toBe(1)
    expect(parseOrgPage([{ id: 'u3' }], 'user').items).toHaveLength(1)
    expect(parseOrgPage({ data: { list: [{ id: 'u4' }], total: 4 } }, 'user').total).toBe(4)
    expect(parseOrgPage(undefined, 'user')).toEqual({ items: [], total: 0 })
  })

  it('部门树解析（data 包装）', () => {
    expect(parseOrgDeptTree({ data: [{ id: 'd1', name: '总部' }] })).toHaveLength(1)
  })

  it('缓存键（同输入同键；空值 / false 不参与）', () => {
    const left = orgCacheKey('user', normalizeOrgSearchQuery({ kind: 'user', keyword: '张', page: 1 }))
    const right = orgCacheKey('user', normalizeOrgSearchQuery({ kind: 'user', keyword: '张', page: 1 }))
    expect(left).toBe(right)
    expect(left).toContain('keyword=张')
    expect(left).not.toContain('includeChildren')
  })

  it('页码 / 页长夹取', () => {
    expect(clampOrgPage(Number.NaN)).toBe(1)
    expect(clampOrgPage(0)).toBe(1)
    expect(clampOrgPage(9.6)).toBe(9)
    expect(clampOrgPageSize(Number.NaN)).toBe(ORG_DEFAULT_PAGE_SIZE)
    expect(clampOrgPageSize(500)).toBe(ORG_PAGE_SIZE_MAX)
  })
})

describe('组织领域 · 树与错误码', () => {
  it('部门路径查找', () => {
    const nodes = normalizeOrgDeptTree([
      { id: 'd1', name: '总部', children: [{ id: 'd2', name: '研发部', children: [{ id: 'd3', name: '前端组' }] }] },
    ])
    expect(findOrgDeptPath(nodes, 'd3')).toEqual(['总部', '研发部', '前端组'])
    expect(findOrgDeptPath(nodes, 'ghost')).toEqual([])
  })

  it('树件节点映射（标签含标记、停用置禁用）', () => {
    const nodes = normalizeOrgDeptTree([
      { id: 'd1', name: '总部', children: [{ id: 'd2', name: '研发部', status: 'disabled' }] },
    ])
    const treeNodes = toOrgTreeNodes(nodes)
    expect(treeNodes[0]?.key).toBe('d1')
    expect(treeNodes[0]?.label).toBe('总部')
    expect(treeNodes[0]?.children?.[0]?.label).toBe('研发部（停用）')
    expect(treeNodes[0]?.children?.[0]?.disabled).toBe(true)
  })

  it('关键词空判定与归一', () => {
    expect(isBlankOrgKeyword('   ')).toBe(true)
    expect(isBlankOrgKeyword(' 张 ')).toBe(false)
    expect(normalizeOrgKeyword(' 张 ')).toBe('张')
    expect(normalizeOrgKeyword('张'.repeat(120)).length).toBe(100)
  })

  it('错误码判定与文案', () => {
    expect(isOrgErrorCode(30101)).toBe(true)
    expect(isOrgErrorCode(30103)).toBe(true)
    expect(isOrgErrorCode(30104)).toBe(false)
    expect(isOrgErrorCode('30101')).toBe(false)
    expect(resolveOrgErrorText(30101)).toBe('组织数据源不可用')
    expect(resolveOrgErrorText(30102)).toBe('不支持的回显目标类型')
    expect(resolveOrgErrorText(30103)).toBe('部门不存在')
    expect(resolveOrgErrorText(99999)).toBe('组织数据不可用')
    expect(resolveOrgErrorText(undefined)).toBe('')
  })
})

describe('组织领域 · 类型面', () => {
  it('组织对象类型覆盖用户 / 岗位 / 部门', () => {
    const kinds: OrgKind[] = ['user', 'post', 'dept']
    expect(kinds.map(orgKindLabel)).toEqual(['用户', '岗位', '部门'])
  })
})
