// kiwi_id: 962
/** 远程字典选择族组件基类用例（06_05）：契约同实现（核心 + 投影）+ 身份依赖 + 部门树缓存 + 用户展示汇入。 */

import {
  BaseField,
  BaseOptionSource,
  BaseDictRemoteSelect,
  BaseUserDisplay,
  normalizeDictDataDeptTree,
  normalizeDictDataKind,
  dictDataItemLabel,
  toDictDataTreeNodes,
  type DictRemoteSourceAdapter,
} from '@bms/core'
import {
  createDictRemoteSourceStub,
  describeDictRemoteSelectContract,
  type DictRemoteSelectContractTarget,
} from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

/** 具体远程字典选择族（可实例化）。 */
class DictSelectState extends BaseDictRemoteSelect {}

/** 具体用户展示（可实例化）。 */
class UserDisplayState extends BaseUserDisplay {}

/** 契约目标（基类实例适配）。 */
function makeTarget(): DictRemoteSelectContractTarget {
  const base = new DictSelectState()
  return {
    get ready() {
      return base.ready
    },
    get degraded() {
      return base.degraded
    },
    get requestCount() {
      return base.requestCount
    },
    get kind() {
      return base.kind
    },
    get page() {
      return base.page
    },
    get total() {
      return base.total
    },
    get items() {
      return base.items
    },
    get deptNodes() {
      return base.deptNodes
    },
    get selectedIds() {
      return base.selectedIds
    },
    get limitExceeded() {
      return base.limitExceeded
    },
    get errorCode() {
      return base.errorCode
    },
    get errorMessage() {
      return base.errorMessage
    },
    setReady: (value) => base.setReady(value),
    setSource: (source) => base.setSource(source as DictRemoteSourceAdapter | undefined),
    setUserDisplay: (display) => base.setUserDisplay(display as BaseUserDisplay | undefined),
    setKind: (kind) => base.setKind(normalizeDictDataKind(kind) ?? 'user'),
    setKeyword: (keyword) => base.setKeyword(keyword),
    setDeptFilter: (deptId, includeChildren) => base.setDeptFilter(deptId, includeChildren),
    setStatus: (status) => base.setStatus(status === 'enabled' || status === 'disabled' ? status : ''),
    setMultiple: (value) => base.setMultiple(value),
    setLimit: (limit) => base.setLimit(limit),
    setPage: (page) => base.setPage(page),
    setLimitExceeded: (value) => base.setLimitExceeded(value),
    setValue: (value) => base.setValue(value),
    load: () => base.load(),
    resolve: (ids) => base.resolve(ids),
    loadDeptTree: () => base.loadDeptTree(),
    invalidate: (kind) => base.invalidate(kind === undefined ? undefined : normalizeDictDataKind(kind)),
    toggle: (id) => base.toggle(id),
    remove: (id) => base.remove(id),
    clearSelection: () => base.clearSelection(),
    labelOf: (id) => base.labelOf(id),
    selectionText: () => base.selectionText(),
    limitText: () => base.limitText(),
    getLabel: (value) => base.getLabel(value),
  }
}

describeDictRemoteSelectContract('远程字典选择契约（BaseDictRemoteSelect）', makeTarget)

describe('BaseDictRemoteSelect 继承链与身份', () => {
  it('挂链 BaseOptionSource → BaseField，能力键与依赖登记一致', () => {
    const base = new DictSelectState()
    expect(base).toBeInstanceOf(BaseOptionSource)
    expect(base).toBeInstanceOf(BaseField)
    expect(base.identifier).toBe('dict_remote_select')
    expect(base.depends).toEqual(['option_source', 'user_display'])
  })

  it('继承选项源语义（options / getLabel / dataVersion 同步）', async () => {
    const stub = createDictRemoteSourceStub()
    const base = new DictSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    await base.load()
    expect(base.options.map((item) => item.value)).toEqual(['u1', 'u2'])
    expect(base.getLabel('u1')).toBe('张三')
    expect(base.getLabel('u2')).toBe('李四（停用）')
    expect(base.dataVersion).toBeGreaterThan(0)
    expect(base.search('张')).toHaveLength(1)
  })

  it('本地搜索（继承）与远程搜索（load）互不影响', async () => {
    const stub = createDictRemoteSourceStub()
    const base = new DictSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    await base.load()
    expect(base.search('李').map((item) => item.value)).toEqual(['u2'])
    base.setKeyword('李')
    await base.load()
    expect(base.requestCount).toBe(2)
    expect(base.options.map((item) => item.value)).toEqual(['u1', 'u2'])
  })
})

describe('BaseDictRemoteSelect 缓存与释放', () => {
  it('部门树一次性加载并会话缓存；invalidate(dept) 后重取', async () => {
    const stub = createDictRemoteSourceStub()
    const base = new DictSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    base.setKind('dept')
    await base.load()
    expect(base.requestCount).toBe(1)
    expect(base.deptNodes).toHaveLength(1)

    await base.loadDeptTree()
    expect(base.requestCount).toBe(1)

    base.invalidate('dept')
    await base.loadDeptTree()
    expect(base.requestCount).toBe(2)
    expect(base.deptNodes).toHaveLength(1)
  })

  it('空部门树亦视为已加载（不重复请求）', async () => {
    const stub = createDictRemoteSourceStub({ loadDeptTree: async () => [] })
    const base = new DictSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    await base.loadDeptTree()
    await base.loadDeptTree()
    expect(base.requestCount).toBe(1)
    expect(base.deptNodes).toEqual([])
  })

  it('候选缓存上限内复用；切换类型清空候选', async () => {
    const stub = createDictRemoteSourceStub()
    const base = new DictSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    await base.load()
    await base.load()
    expect(base.requestCount).toBe(1)

    base.setKind('post')
    expect(base.items).toEqual([])
    await base.load()
    expect(base.requestCount).toBe(2)
    expect(base.labelOf('p1')).toBe('研发经理')
  })

  it('查询参数（归一后 camelCase；含部门与状态）', () => {
    const base = new DictSelectState()
    base.setKeyword('  张 ')
    base.setDeptFilter(' d1 ', true)
    base.setStatus('enabled')
    expect(base.searchQuery()).toEqual({
      keyword: '张',
      deptId: 'd1',
      includeChildren: true,
      status: 'enabled',
      page: 1,
      pageSize: 20,
    })
    expect(base.resolveParams(['u1'])).toEqual({ target: 'user', id_in: 'u1' })
  })
})

describe('BaseDictRemoteSelect 用户展示与部门路径', () => {
  it('用户选项汇入 BaseUserDisplay 花名册（状态映射 / 部门路径补全）', async () => {
    const stub = createDictRemoteSourceStub()
    const display = new UserDisplayState()
    const base = new DictSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    base.setUserDisplay(display)
    await base.loadDeptTree()
    await base.load()
    expect(display.findUser('u1')?.name).toBe('张三')
    expect(display.findUser('u1')?.status).toBe('active')
    expect(display.findUser('u1')?.deptPath).toBe('总部 / 研发部')
    expect(display.displayOf('ghost')).toEqual({ id: 'ghost', name: 'ghost', deleted: true })
  })

  it('岗位类型不汇入用户花名册', async () => {
    const stub = createDictRemoteSourceStub()
    const display = new UserDisplayState()
    const base = new DictSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    base.setUserDisplay(display)
    base.setKind('post')
    await base.load()
    expect(display.users).toEqual([])
  })
})

describe('部门编码展示（mdm 出口 code）', () => {
  it('归一保留部门编码；未返回 code 的旧出口回落为无编码', () => {
    const tree = normalizeDictDataDeptTree([
      {
        id: 'd1',
        code: 'DEPT0001',
        name: '总部',
        status: 'enabled',
        children: [{ id: 'd2', name: '研发部', status: 'enabled' }],
      },
    ])
    expect(tree[0]?.code).toBe('DEPT0001')
    expect(tree[0]?.children?.[0]?.code).toBeUndefined()
  })

  it('树件 label 附部门编码（标记在编码之后）；无编码时只显名称', () => {
    const nodes = toDictDataTreeNodes([
      { id: 'd1', code: 'DEPT0001', name: '总部', status: 'enabled', deleted: false },
      { id: 'd2', code: 'DEPT0002', name: '研发部', status: 'disabled', deleted: false },
      { id: 'd3', name: '无编码部门', status: 'enabled', deleted: false },
    ])
    expect(nodes[0]?.label).toBe('总部 (DEPT0001)')
    expect(nodes[1]?.label).toBe('研发部 (DEPT0002)（停用）')
    expect(nodes[2]?.label).toBe('无编码部门')
  })

  it('非部门类型的编码不拼进 label（岗位编码仍单独展示）', () => {
    const label = dictDataItemLabel({
      id: 'p1',
      name: '研发经理',
      kind: 'post',
      status: 'enabled',
      deleted: false,
      code: 'RD-MGR',
    })
    expect(label).toBe('研发经理')
  })
})
