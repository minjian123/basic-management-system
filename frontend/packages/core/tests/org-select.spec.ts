// kiwi_id: 962
/** 组织选择族组件基类用例（06_05）：契约同实现（核心 + 投影）+ 身份依赖 + 部门树缓存 + 用户展示汇入。 */

import { BaseField, BaseOptionSource, BaseOrgSelect, BaseUserDisplay, normalizeOrgKind, type OrgSourceAdapter } from '@bms/core'
import {
  createOrgSourceStub,
  describeOrgSelectContract,
  type OrgSelectContractTarget,
} from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

/** 具体组织选择族（可实例化）。 */
class OrgSelectState extends BaseOrgSelect {}

/** 具体用户展示（可实例化）。 */
class UserDisplayState extends BaseUserDisplay {}

/** 契约目标（基类实例适配）。 */
function makeTarget(): OrgSelectContractTarget {
  const base = new OrgSelectState()
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
    setSource: (source) => base.setSource(source as OrgSourceAdapter | undefined),
    setUserDisplay: (display) => base.setUserDisplay(display as BaseUserDisplay | undefined),
    setKind: (kind) => base.setKind(normalizeOrgKind(kind) ?? 'user'),
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
    invalidate: (kind) => base.invalidate(kind === undefined ? undefined : normalizeOrgKind(kind)),
    toggle: (id) => base.toggle(id),
    remove: (id) => base.remove(id),
    clearSelection: () => base.clearSelection(),
    labelOf: (id) => base.labelOf(id),
    selectionText: () => base.selectionText(),
    limitText: () => base.limitText(),
    getLabel: (value) => base.getLabel(value),
  }
}

describeOrgSelectContract('组织选择契约（BaseOrgSelect）', makeTarget)

describe('BaseOrgSelect 继承链与身份', () => {
  it('挂链 BaseOptionSource → BaseField，能力键与依赖登记一致', () => {
    const base = new OrgSelectState()
    expect(base).toBeInstanceOf(BaseOptionSource)
    expect(base).toBeInstanceOf(BaseField)
    expect(base.identifier).toBe('org-select')
    expect(base.depends).toEqual(['option-source', 'user-display'])
  })

  it('继承选项源语义（options / getLabel / dataVersion 同步）', async () => {
    const stub = createOrgSourceStub()
    const base = new OrgSelectState()
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
    const stub = createOrgSourceStub()
    const base = new OrgSelectState()
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

describe('BaseOrgSelect 缓存与释放', () => {
  it('部门树一次性加载并会话缓存；invalidate(dept) 后重取', async () => {
    const stub = createOrgSourceStub()
    const base = new OrgSelectState()
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
    const stub = createOrgSourceStub({ loadDeptTree: async () => [] })
    const base = new OrgSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    await base.loadDeptTree()
    await base.loadDeptTree()
    expect(base.requestCount).toBe(1)
    expect(base.deptNodes).toEqual([])
  })

  it('候选缓存上限内复用；切换类型清空候选', async () => {
    const stub = createOrgSourceStub()
    const base = new OrgSelectState()
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
    const base = new OrgSelectState()
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

describe('BaseOrgSelect 用户展示与部门路径', () => {
  it('用户选项汇入 BaseUserDisplay 花名册（状态映射 / 部门路径补全）', async () => {
    const stub = createOrgSourceStub()
    const display = new UserDisplayState()
    const base = new OrgSelectState()
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
    const stub = createOrgSourceStub()
    const display = new UserDisplayState()
    const base = new OrgSelectState()
    base.setReady(true)
    base.setSource(stub.source)
    base.setUserDisplay(display)
    base.setKind('post')
    await base.load()
    expect(display.users).toEqual([])
  })
})
