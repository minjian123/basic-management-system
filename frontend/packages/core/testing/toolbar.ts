/**
 * 工具栏契约用例工厂（`BaseToolbar` 及其投影共用；`09_02` 首次落地）。
 *
 * 目标约定：动作集含 `create` / `refresh` / `batch-delete`（批量动作）与 `close`；
 * 帮助未登记锚点时隐藏，登记后位于右组末位；帮助永不进溢出。
 */

import { describe, expect, it } from 'vitest'

/** 工具栏契约面。 */
export interface ToolbarContractTarget {
  /** 当前可见动作键（分态 + 权限过滤后，不含帮助）。 */
  readonly keys: readonly string[]
  /** 左组动作键。 */
  readonly leftKeys: readonly string[]
  /** 右组直显动作键（含帮助时在末位）。 */
  readonly rightKeys: readonly string[]
  /** 溢出动作键（不含帮助）。 */
  readonly overflowKeys: readonly string[]
  /** 帮助入口是否可见。 */
  readonly helpVisible: boolean
  /** 当前分态。 */
  readonly mode: string
  /** 切换分态。 */
  setEditing(value: boolean): void
  /** 设置选中数。 */
  setSelectedCount(count: number): void
  /** 设置帮助可用性。 */
  setHelpAvailable(value: boolean): void
  /** 为指定动作声明权限码（覆盖）。 */
  setPermission(key: string, permission?: string): void
  /** 注入权限判定。 */
  setPermChecker(checker: ((permission: string) => boolean) | undefined): void
  /** 动作是否可触发。 */
  canRun(key: string): boolean
}

/**
 * 工具栏契约（`BaseListToolbar` / `useBaseToolbar` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeToolbarContract(name: string, create: () => ToolbarContractTarget): void {
  describe(name, () => {
    it('默认动作集按分组渲染，帮助未登记锚点时隐藏', () => {
      const target = create()
      expect(target.keys).toContain('create')
      expect(target.leftKeys).toContain('create')
      expect(target.rightKeys).not.toContain('help')
      expect(target.helpVisible).toBe(false)
      expect(target.overflowKeys).not.toContain('help')
    })

    it('帮助登记锚点后位于右组末位，永不进溢出', () => {
      const target = create()
      target.setHelpAvailable(true)
      expect(target.helpVisible).toBe(true)
      expect(target.rightKeys[target.rightKeys.length - 1]).toBe('help')
      expect(target.overflowKeys).not.toContain('help')

      target.setEditing(true)
      expect(target.rightKeys[target.rightKeys.length - 1]).toBe('help')
    })

    it('批量动作随选中态启用；加载态由权限与禁用判据约束', () => {
      const target = create()
      expect(target.canRun('batch-delete')).toBe(false)
      target.setSelectedCount(2)
      expect(target.canRun('batch-delete')).toBe(true)

      target.setSelectedCount(0)
      target.setPermission('refresh', 'user.refresh')
      target.setPermChecker(() => false)
      expect(target.canRun('refresh')).toBe(false)
      expect(target.keys).not.toContain('refresh')
      target.setPermChecker(undefined)
      expect(target.canRun('refresh')).toBe(true)
      expect(target.keys).toContain('refresh')
    })
  })
}
