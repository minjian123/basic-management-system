/**
 * 字典树纯函数用例：平铺条目按 `parentId` 组树、同级排序、禁用态、孤儿挂根、环防御、路径查找。
 */

import { describe, expect, it } from 'vitest'

import { buildDictTree, findDictTreePath, type DictItem } from '../src'

/**
 * 构造字典条目。
 *
 * @param id 条目 id。
 * @param parentId 父 id。
 * @param label 文案。
 * @param sort 排序值。
 * @param status 状态。
 */
function item(
  id: string,
  parentId: string | undefined,
  label: string,
  sort = 0,
  status: 'enabled' | 'disabled' = 'enabled',
): DictItem {
  return { id, parentId, label, code: id, value: id, sort, status }
}

describe('buildDictTree', () => {
  it('按 parentId 组装多级树并按 sort 排序', () => {
    const nodes = buildDictTree([
      item('b', '0', 'B 部门', 2),
      item('a', '0', 'A 部门', 1),
      item('a1', 'a', 'A-1', 1),
      item('a2', 'a', 'A-2', 0),
    ])
    expect(nodes.map((node) => node.key)).toEqual(['a', 'b'])
    expect(nodes[0]?.children?.map((node) => node.key)).toEqual(['a2', 'a1'])
  })

  it('parentId 缺省 / 空串均视为顶层', () => {
    const nodes = buildDictTree([item('a', undefined, 'A'), item('b', '', 'B'), item('a1', 'a', 'A-1')])
    expect(nodes.map((node) => node.key)).toEqual(['a', 'b'])
    expect(nodes[0]?.children?.map((node) => node.key)).toEqual(['a1'])
  })

  it('非 enabled 条目置 disabled', () => {
    const nodes = buildDictTree([item('a', '0', 'A', 0, 'disabled')])
    expect(nodes[0]?.disabled).toBe(true)
  })

  it('孤儿节点挂根，且其子节点补挂到该孤儿下', () => {
    const nodes = buildDictTree([item('x', 'missing', 'X'), item('x1', 'x', 'X-1')])
    expect(nodes.map((node) => node.key)).toEqual(['x'])
    expect(nodes[0]?.children?.map((node) => node.key)).toEqual(['x1'])
  })

  it('丢弃孤儿模式不挂根', () => {
    const nodes = buildDictTree([item('x', 'missing', 'X')], { keepOrphans: false })
    expect(nodes).toEqual([])
  })

  it('环引用不死循环（已访问节点不再挂子级）', () => {
    const nodes = buildDictTree([item('a', 'b', 'A'), item('b', 'a', 'B')])
    expect(nodes.map((node) => node.key)).toEqual(['a'])
    expect(nodes[0]?.children?.map((node) => node.key)).toEqual(['b'])
    expect(nodes[0]?.children?.[0]?.children).toBeUndefined()
  })

  it('自定义根父标识', () => {
    const nodes = buildDictTree([item('a', 'root', 'A')], { rootParentId: 'root' })
    expect(nodes.map((node) => node.key)).toEqual(['a'])
  })
})

describe('findDictTreePath', () => {
  it('命中返回根到目标的路径', () => {
    const nodes = buildDictTree([item('a', '0', 'A'), item('a1', 'a', 'A-1'), item('a11', 'a1', 'A-1-1')])
    expect(findDictTreePath(nodes, 'a11').map((node) => node.label)).toEqual(['A', 'A-1', 'A-1-1'])
  })

  it('未命中返回空数组', () => {
    const nodes = buildDictTree([item('a', '0', 'A')])
    expect(findDictTreePath(nodes, 'missing')).toEqual([])
  })
})
