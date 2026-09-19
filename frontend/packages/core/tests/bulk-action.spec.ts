import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseBulkAction,
  BaseNotice,
  validateCapabilityGraph,
  type BulkActionDef,
} from '../src'

/** 具体权限上下文（测试用）。 */
class Access extends BaseAccess {}

/** 具体提示通知（测试用）。 */
class Notice extends BaseNotice {}

/** 具体批量动作件（测试用）。 */
class Bulk extends BaseBulkAction {}

describe('capabilities/selection · 选中集合', () => {
  it('选中去重保序，且 replace 按内容比较（无变更不通知）', () => {
    const bulk = new Bulk()
    let updates = 0
    bulk.onLifecycle((event) => {
      if (event === 'update') {
        updates += 1
      }
    })
    bulk.select('2')
    bulk.select('1')
    bulk.select(1)
    expect(bulk.selected).toEqual(['2', '1'])
    expect(bulk.count).toBe(2)

    const before = updates
    bulk.replace(['2', '1'])
    expect(updates).toBe(before)

    bulk.replace(['1'])
    expect(bulk.selected).toEqual(['1'])
  })

  it('page 模式翻页剔除不在当前页的键；cross-page 模式保留', () => {
    const page = new Bulk()
    page.setPageKeys([1, 2])
    page.select(1)
    page.select(2)
    page.setPageKeys([3])
    expect(page.selected).toEqual([])
    expect(page.count).toBe(0)

    const cross = new Bulk()
    cross.setMode('cross-page')
    cross.setPageKeys([1, 2])
    cross.select(1)
    cross.setPageKeys([3, 4])
    expect(cross.selected).toEqual(['1'])
  })

  it('当前页全选 / 反选 / 取消全选', () => {
    const bulk = new Bulk()
    bulk.setPageKeys([1, 2, 3])
    bulk.selectPage()
    expect(bulk.isAllPageSelected).toBe(true)
    expect(bulk.count).toBe(3)

    bulk.invertPage()
    expect(bulk.count).toBe(0)

    bulk.select(1)
    expect(bulk.somePageSelected).toBe(true)
    bulk.deselectPage()
    expect(bulk.count).toBe(0)
    expect(bulk.somePageSelected).toBe(false)
  })

  it('跨页全选仅 cross-page 模式生效，取总记录数并在切页后清标记', () => {
    const page = new Bulk()
    page.setTotal(50)
    page.selectAllAcrossPages()
    expect(page.allAcrossPages).toBe(false)

    const cross = new Bulk()
    cross.setMode('cross-page')
    cross.setTotal(50)
    cross.setPageKeys([1, 2])
    cross.select(1)
    cross.selectAllAcrossPages()
    expect(cross.allAcrossPages).toBe(true)
    expect(cross.selected).toEqual([])
    expect(cross.count).toBe(50)
    expect(cross.summary).toEqual({ count: 50, allAcrossPages: true, total: 50, mode: 'cross-page' })

    cross.setPageKeys([3])
    expect(cross.allAcrossPages).toBe(false)
    expect(cross.count).toBe(0)
  })
})

describe('capabilities/bulk-action · 动作编排', () => {
  it('权限过滤：未注入权限不过滤，注入后按权限码过滤', () => {
    const bulk = new Bulk()
    bulk.actions = [
      { key: 'enable', perm: 'user.enable', label: '启用', run: () => ({ success: 1, failed: 0 }) },
      { key: 'delete', perm: 'user.delete', label: '删除', danger: true, run: () => ({ success: 1, failed: 0 }) },
    ]
    expect(bulk.visibleActions.map((action) => action.key)).toEqual(['enable', 'delete'])

    const access = new Access()
    access.setCodes(['user.enable'])
    bulk.access = access
    expect(bulk.visibleActions.map((action) => action.key)).toEqual(['enable'])
    expect(bulk.hasVisibleActions).toBe(true)
  })

  it('确认判定：危险 / 显式 / 超量三类命中', () => {
    const bulk = new Bulk()
    bulk.confirmThreshold = 5
    bulk.actions = [
      { key: 'enable', label: '启用', run: () => ({ success: 1, failed: 0 }) },
      { key: 'export', label: '导出', confirm: true, run: () => ({ success: 1, failed: 0 }) },
      { key: 'delete', label: '删除', danger: true, run: () => ({ success: 1, failed: 0 }) },
      { key: 'move', label: '移动', threshold: 2, run: () => ({ success: 1, failed: 0 }) },
    ]
    const [enable, exportAction, remove, move] = bulk.actions as BulkActionDef[]
    expect(bulk.needsConfirm(enable as BulkActionDef)).toBe(false)
    expect(bulk.needsConfirm(exportAction as BulkActionDef)).toBe(true)
    expect(bulk.needsConfirm(remove as BulkActionDef)).toBe(true)

    bulk.setPageKeys([1, 2])
    bulk.selectPage()
    expect(bulk.needsConfirm(enable as BulkActionDef)).toBe(false)
    expect(bulk.needsConfirm(move as BulkActionDef)).toBe(true)

    bulk.select(3)
    bulk.select(4)
    bulk.select(5)
    expect(bulk.needsConfirm(enable as BulkActionDef)).toBe(true)
  })

  it('需确认动作先进入确认阶段，确认后执行；取消回 idle 不执行', async () => {
    const bulk = new Bulk()
    let runs = 0
    bulk.actions = [
      {
        key: 'delete',
        label: '删除',
        danger: true,
        run: () => {
          runs += 1
          return { success: 2, failed: 0 }
        },
      },
    ]
    bulk.setPageKeys([1, 2])
    bulk.selectPage()

    expect(await bulk.request('delete')).toBeUndefined()
    expect(bulk.phase).toBe('confirming')
    expect(bulk.pendingActionKey).toBe('delete')

    bulk.cancel()
    expect(bulk.phase).toBe('idle')
    expect(runs).toBe(0)

    await bulk.request('delete')
    await expect(bulk.confirm()).resolves.toEqual({ success: 2, failed: 0 })
    expect(runs).toBe(1)
    expect(bulk.phase).toBe('done')
    expect(bulk.count).toBe(0)
  })

  it('执行中拒绝重复请求；无选中不执行', async () => {
    const bulk = new Bulk()
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    bulk.actions = [
      {
        key: 'export',
        label: '导出',
        run: async () => {
          await gate
          return { success: 1, failed: 0 }
        },
      },
    ]
    expect(await bulk.run('export')).toBeUndefined()

    bulk.setPageKeys([1])
    bulk.select(1)
    const pending = bulk.run('export')
    expect(bulk.running).toBe(true)
    expect(await bulk.run('export')).toBeUndefined()
    release()
    await expect(pending).resolves.toEqual({ success: 1, failed: 0 })
  })

  it('执行异常记为整体失败并通知；clearAfterDone 为假时保留选中', async () => {
    const bulk = new Bulk()
    const notice = new Notice()
    bulk.notice = notice
    bulk.clearAfterDone = false
    bulk.actions = [
      {
        key: 'move',
        label: '移动',
        run: () => {
          throw new Error('目标部门不存在')
        },
      },
    ]
    bulk.setPageKeys([1, 2])
    bulk.selectPage()

    await expect(bulk.run('move')).resolves.toEqual({ success: 0, failed: 2, message: '目标部门不存在' })
    expect(bulk.lastResult?.failed).toBe(2)
    expect(bulk.count).toBe(2)
    expect(notice.queue.at(-1)?.type).toBe('warning')
  })

  it('部分成功：进度上报 + 结果汇总 + 完成提示', async () => {
    const bulk = new Bulk()
    const notice = new Notice()
    bulk.notice = notice
    bulk.actions = [
      {
        key: 'disable',
        label: '停用',
        run: (context) => {
          context.setProgress(2, 3)
          return { success: 2, failed: 1, failures: [{ key: '3', reason: '已被引用' }] }
        },
      },
    ]
    bulk.setPageKeys([1, 2, 3])
    bulk.selectPage()

    const result = await bulk.run('disable')
    expect(bulk.progress).toEqual({ current: 2, total: 3 })
    expect(result?.failures).toEqual([{ key: '3', reason: '已被引用' }])
    expect(notice.queue.at(-1)?.content).toBe('成功 2 项，失败 1 项')
    expect(bulk.count).toBe(0)
  })

  it('能力依赖登记包含新增四项且无环', () => {
    const problems = validateCapabilityGraph()
    expect(problems).toEqual([])
  })
})
