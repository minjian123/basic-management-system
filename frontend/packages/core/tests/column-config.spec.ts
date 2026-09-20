/** 列配置组件基类（`BaseColumnConfig`：显隐 / 顺序 / 宽度 / 冻结 / 归一 / 恢复默认）。 */

import { describe, expect, it } from 'vitest'

import { BaseColumnConfig, BasePersistedState } from '../src'

/** 具体列配置件（可实例化）。 */
class DemoColumns extends BaseColumnConfig {}

describe('BaseColumnConfig 继承与身份', () => {
  it('继承偏好持久化能力基类', () => {
    const columns = new DemoColumns()
    expect(columns).toBeInstanceOf(BasePersistedState)
    expect(columns.identifier).toBe('column-config')
    expect(columns.key).toBe('column-config')
  })
})

describe('BaseColumnConfig 显隐与顺序', () => {
  it('整体设置 / 切换显隐 / 可见列', () => {
    const columns = new DemoColumns()
    columns.setColumns([
      { key: 'a', visible: true, order: 1 },
      { key: 'b', visible: false, order: 0 },
    ])
    expect(columns.visibleOrder).toEqual(['a'])
    columns.toggleVisible('b')
    expect(columns.visibleOrder).toEqual(['b', 'a'])
    expect(columns.local).toEqual(columns.columns)
    columns.toggleVisible('absent')
    expect(columns.has('absent')).toBe(false)
  })

  it('末列不可隐藏', () => {
    const columns = new DemoColumns()
    columns.setColumns([{ key: 'a', visible: true, order: 0 }])
    columns.setVisible('a', false)
    expect(columns.visibleOrder).toEqual(['a'])
    columns.setVisible('absent', false)
    expect(columns.visibleOrder).toEqual(['a'])
  })

  it('移动列并重排顺序（越界夹取）', () => {
    const columns = new DemoColumns()
    columns.setColumns([
      { key: 'a', visible: true, order: 0 },
      { key: 'b', visible: true, order: 1 },
      { key: 'c', visible: true, order: 2 },
    ])
    columns.moveColumn('a', 1)
    expect(columns.columns.map((column) => column.key)).toEqual(['b', 'a', 'c'])
    expect(columns.columns.map((column) => column.order)).toEqual([0, 1, 2])
    columns.moveColumn('c', 99)
    expect(columns.visibleOrder).toEqual(['b', 'a', 'c'])
    columns.moveColumn('absent', 1)
    columns.moveColumn('a', Number.NaN)
    expect(columns.visibleOrder).toEqual(['b', 'a', 'c'])
  })
})

describe('BaseColumnConfig 宽度与冻结', () => {
  it('宽度夹取与冻结标记', () => {
    const columns = new DemoColumns()
    columns.setColumns([{ key: 'a', visible: true, order: 0 }])
    columns.setWidth('a', 200)
    expect(columns.columns[0]?.width).toBe(200)
    columns.setWidth('a', 10)
    expect(columns.columns[0]?.width).toBe(60)
    columns.setWidth('a', 60)
    expect(columns.columns[0]?.width).toBe(60)
    columns.setWidth('absent', 100)
    expect(columns.has('absent')).toBe(false)

    columns.setFrozen('a', true)
    expect(columns.columns[0]?.frozen).toBe(true)
    columns.setFrozen('a', true)
    columns.setFrozen('absent', true)
  })
})

describe('BaseColumnConfig 归一与恢复默认', () => {
  it('归一保留既有状态、剔除已删列、追加新增列', () => {
    const columns = new DemoColumns()
    columns.setColumns([
      { key: 'b', visible: false, order: 0, width: 100 },
      { key: 'a', visible: true, order: 1 },
      { key: 'gone', visible: true, order: 2 },
    ])
    columns.normalizeWith([{ key: 'b' }, { key: 'a' }, { key: 'c', width: 180 }])
    expect(columns.visibleOrder).toEqual(['a', 'c'])
    expect(columns.columns.map((column) => column.key)).toEqual(['b', 'a', 'c'])
    expect(columns.columns[0]).toMatchObject({ visible: false, width: 100 })
    expect(columns.columns[2]).toMatchObject({ visible: true, width: 180, frozen: false })
  })

  it('恢复默认全量重建', () => {
    const columns = new DemoColumns()
    columns.setColumns([{ key: 'b', visible: false, order: 0, width: 100 }])
    columns.resetColumns([
      { key: 'a', width: 120 },
      { key: 'b', visible: false },
    ])
    expect(columns.columns.map((column) => column.key)).toEqual(['a', 'b'])
    expect(columns.columns[0]).toMatchObject({ visible: true, order: 0, width: 120 })
    expect(columns.visibleOrder).toEqual(['a'])
  })
})
