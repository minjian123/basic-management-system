// kiwi_id: 2525
/** 工具栏基类（09_02）：列表 / 表单派生、默认动作、分态、帮助位、权限与批量启用。 */

import { describe, expect, it } from 'vitest'

import { BaseFormToolbar, BaseListToolbar } from '@bms/core'
import { describeToolbarContract, type ToolbarContractTarget } from '@bms/core/testing'

/** 可实例化列表工具栏。 */
class ListToolbarState extends BaseListToolbar {}

/** 可实例化表单工具栏。 */
class FormToolbarState extends BaseFormToolbar {}

/**
 * 把列表工具栏适配为契约目标。
 *
 * @returns 契约目标。
 */
function makeListTarget(): ToolbarContractTarget {
  const toolbar = new ListToolbarState()
  const permissionOverrides: { key: string; permission?: string }[] = []
  return {
    get keys() {
      return toolbar.visibleActions().map((action) => action.key)
    },
    get leftKeys() {
      return toolbar.groups().left.map((action) => action.key)
    },
    get rightKeys() {
      return toolbar.groups().right.map((action) => action.key)
    },
    get overflowKeys() {
      return toolbar.groups().overflow.map((action) => action.key)
    },
    get helpVisible() {
      return toolbar.helpVisible
    },
    get mode() {
      return toolbar.mode
    },
    setEditing: (value) => toolbar.setEditing(value),
    setSelectedCount: (count) => toolbar.setSelectedCount(count),
    setHelpAvailable: (value) => toolbar.setHelpAvailable(value),
    setPermission: (key, permission) => {
      const index = permissionOverrides.findIndex((entry) => entry.key === key)
      const next = { key, ...(permission === undefined ? {} : { permission }) }
      if (index < 0) {
        permissionOverrides.push(next)
      } else {
        permissionOverrides[index] = next
      }
      toolbar.setOverrides(permissionOverrides)
    },
    setPermChecker: (checker) => toolbar.setPermChecker(checker),
    canRun: (key) => toolbar.canRun(key),
  }
}

describe('列表工具栏基类（09_02）', () => {
  describeToolbarContract('列表工具栏契约', makeListTarget)

  it('默认动作集与分组；帮助登记锚点后位于右组末位', () => {
    const toolbar = new ListToolbarState()
    expect(toolbar.identifier).toBe('list_toolbar')
    expect(toolbar.groups().left.map((action) => action.key)).toEqual([
      'create',
      'refresh',
      'batch-toggle',
      'batch-delete',
      'close',
    ])
    expect(toolbar.groups().right).toEqual([])
    expect(toolbar.helpVisible).toBe(false)

    toolbar.setHelpAvailable(true)
    expect(toolbar.groups().right.map((action) => action.key)).toEqual(['help'])
    expect(toolbar.groups().overflow).toEqual([])
  })

  it('页面覆盖保留 testId 与业务顺序；权限过滤即时生效', () => {
    const toolbar = new ListToolbarState()
    toolbar.setOverrides([
      { key: 'create', label: '新建用户', testId: 'user-create' },
      { key: 'close', label: '关闭页面', testId: 'user-close-page' },
    ])
    toolbar.addActions([
      { key: 'reset-pwd', label: '重置密码', group: 'left', order: 25, testId: 'user-reset-pwd' },
    ])
    expect(toolbar.groups().left.map((action) => action.key)).toEqual([
      'create',
      'refresh',
      'reset-pwd',
      'batch-toggle',
      'batch-delete',
      'close',
    ])
    expect(toolbar.actionOf('create')?.testId).toBe('user-create')

    toolbar.setPermChecker((permission) => permission !== 'user.delete')
    toolbar.setOverrides([{ key: 'batch-delete', permission: 'user.delete' }])
    expect(toolbar.groups().left.map((action) => action.key)).not.toContain('batch-delete')
  })

  it('加载态禁用全部动作；溢出只收纳右组', () => {
    const toolbar = new ListToolbarState()
    toolbar.addActions([
      { key: 'export', label: '导出', group: 'right', order: 20 },
      { key: 'columns', label: '自定义列', group: 'right', order: 30 },
      { key: 'log', label: '日志', group: 'right', order: 40 },
    ])
    toolbar.setHelpAvailable(true)
    toolbar.setMaxRight(2)
    expect(toolbar.groups().right.map((action) => action.key)).toEqual(['export', 'columns', 'help'])
    expect(toolbar.groups().overflow.map((action) => action.key)).toEqual(['log'])
    expect(toolbar.groups().left.some((action) => action.key === 'log')).toBe(false)

    toolbar.setProps({ loading: true })
    expect(toolbar.canRun('refresh')).toBe(false)
  })
})

describe('表单工具栏基类（09_02）', () => {
  it('只读 / 编辑分态：修改与保存互斥，关闭两态可见，帮助末位', () => {
    const toolbar = new FormToolbarState()
    toolbar.setHelpAvailable(true)
    expect(toolbar.mode).toBe('readonly')
    expect(toolbar.visibleActions().map((action) => action.key)).toEqual(['edit', 'delete', 'refresh', 'close'])
    expect(toolbar.groups().right.map((action) => action.key)).toEqual(['help'])

    toolbar.setEditing(true)
    expect(toolbar.mode).toBe('editing')
    expect(toolbar.visibleActions().map((action) => action.key)).toEqual(['save', 'cancel', 'refresh', 'close'])
    expect(toolbar.canRun('save')).toBe(true)
    expect(toolbar.canRun('edit')).toBe(false)
  })

  it('页面覆盖禁用与危险语义；保存为编辑态唯一主操作', () => {
    const toolbar = new FormToolbarState()
    toolbar.setOverrides([
      { key: 'save', label: '保存并关闭', testId: 'user-record-save' },
      { key: 'delete', disabled: true, reason: '存在关联数据' },
    ])
    const save = toolbar.actionOf('save')
    expect(save?.type).toBe('primary')
    expect(save?.testId).toBe('user-record-save')
    expect(toolbar.actionOf('delete')?.danger).toBe(true)
    const del = toolbar.actionOf('delete')
    expect(del).toBeDefined()
    expect(toolbar.isDisabled(del!)).toBe(true)
  })
})
