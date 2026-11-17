// kiwi_id: 2525
/** 工具栏领域纯函数（09_02）：动作合并 / 排序 / 权限 / 分态 / 溢出收纳。 */

import { describe, expect, it } from 'vitest'

import {
  filterToolbarActions,
  groupToolbarActions,
  isToolbarActionDisabled,
  mergeToolbarActions,
  visibleToolbarActions,
  type ToolbarAction,
} from '@bms/core'

/** 默认动作样本。 */
function defaults(): ToolbarAction[] {
  return [
    { key: 'create', label: '新增', group: 'left', order: 10 },
    { key: 'refresh', label: '刷新', group: 'left', order: 20 },
    { key: 'export', label: '导出', group: 'right', order: 30, permission: 'user.export' },
    { key: 'columns', label: '自定义列', group: 'right', order: 40 },
    { key: 'close', label: '关闭', group: 'right', order: 50 },
  ]
}

describe('工具栏动作模型（09_02）', () => {
  it('合并：覆盖文案与顺序、新增动作、同键再覆盖、隐藏删除', () => {
    const merged = mergeToolbarActions(
      defaults(),
      [
        { key: 'create', label: '新建用户', order: 5 },
        { key: 'columns', hidden: true },
      ],
      [
        { key: 'batch-delete', label: '删除', group: 'left', order: 15, danger: true },
        { key: 'refresh', label: '重新加载' },
      ],
    )
    expect(merged.map((action) => action.key)).toEqual(['create', 'batch-delete', 'refresh', 'export', 'close'])
    expect(merged[0]?.label).toBe('新建用户')
    expect(merged.find((action) => action.key === 'refresh')?.label).toBe('重新加载')
    expect(merged.find((action) => action.key === 'batch-delete')?.danger).toBe(true)
  })

  it('权限过滤：无权限不渲染，未注入判定不过滤', () => {
    const actions = defaults()
    expect(visibleToolbarActions(actions).map((action) => action.key)).toContain('export')
    expect(visibleToolbarActions(actions, (code) => code !== 'user.export').map((action) => action.key)).not.toContain(
      'export',
    )
  })

  it('分态过滤：showIn 缺省两态可见', () => {
    const actions: ToolbarAction[] = [
      { key: 'edit', label: '修改', showIn: ['readonly'] },
      { key: 'save', label: '保存', showIn: ['editing'] },
      { key: 'close', label: '关闭' },
    ]
    expect(filterToolbarActions(actions, 'readonly').map((action) => action.key)).toEqual(['edit', 'close'])
    expect(filterToolbarActions(actions, 'editing').map((action) => action.key)).toEqual(['save', 'close'])
  })

  it('禁用：加载 / 显式禁用 / 批量无选中', () => {
    expect(isToolbarActionDisabled({ key: 'a', label: 'A' }, { loading: true })).toBe(true)
    expect(isToolbarActionDisabled({ key: 'a', label: 'A', disabled: true })).toBe(true)
    expect(isToolbarActionDisabled({ key: 'b', label: 'B', batch: true }, { selectedCount: 0 })).toBe(true)
    expect(isToolbarActionDisabled({ key: 'b', label: 'B', batch: true }, { selectedCount: 2 })).toBe(false)
  })

  it('分组：左组不收纳；右组超限进溢出；帮助不参与分组', () => {
    const help: ToolbarAction = { key: 'help', label: '帮助', group: 'right', order: 999 }
    const groups = groupToolbarActions([...defaults(), help], 2)
    expect(groups.left.map((action) => action.key)).toEqual(['create', 'refresh'])
    expect(groups.right.map((action) => action.key)).toEqual(['export', 'columns'])
    expect(groups.overflow.map((action) => action.key)).toEqual(['close'])
    expect([...groups.left, ...groups.right, ...groups.overflow].map((action) => action.key)).not.toContain('help')

    const zero = groupToolbarActions(defaults(), 0)
    expect(zero.right).toEqual([])
    expect(zero.overflow.map((action) => action.key)).toEqual(['export', 'columns', 'close'])
  })
})
