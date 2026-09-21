/**
 * 组织选择契约（`@bms/core/testing`）。
 *
 * 组件基类 / 投影 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、数据源注入与就绪、三类派发与查询参数、关键词结果缓存、批量回显与
 * 已删除 / 停用标记、多选去重与上限、部门树一次性加载、错误码与重试、用户展示花名册。
 */

import { describe, expect, it } from 'vitest'

import type { OrgSourceAdapter } from '../src'

/** 契约用户（含停用项）。 */
export const ORG_CONTRACT_USERS: readonly Record<string, unknown>[] = [
  { id: 'u1', nickname: '张三', username: 'zhangsan', deptId: 'd2', status: 'enabled', phone: '138****8000', avatar: 'a.png' },
  { id: 'u2', nickname: '李四', username: 'lisi', deptId: 'd2', status: 'disabled' },
]

/** 契约岗位。 */
export const ORG_CONTRACT_POSTS: readonly Record<string, unknown>[] = [
  { id: 'p1', name: '研发经理', code: 'RD-MGR', deptId: 'd1', status: 'enabled' },
]

/** 契约部门树（嵌套）。 */
export const ORG_CONTRACT_DEPTS: readonly Record<string, unknown>[] = [
  { id: 'd1', name: '总部', status: 'enabled', children: [{ id: 'd2', name: '研发部', status: 'enabled' }] },
]

/** 契约回显引用（`u2` 停用；未列出的 id 视为已删除）。 */
export const ORG_CONTRACT_REFS: readonly Record<string, unknown>[] = [
  { id: 'u1', name: '张三', target: 'user', exists: true, status: 'enabled' },
  { id: 'u2', name: '李四', target: 'user', exists: true, status: 'disabled' },
  { id: 'u9', name: '', target: 'user', exists: false, status: 'disabled' },
]

/** 契约选项（结构化最小面）。 */
export interface OrgSelectContractItem {
  /** 标识。 */
  id: string
  /** 名称。 */
  name: string
  /** 状态。 */
  status: string
  /** 是否已删除。 */
  deleted: boolean
}

/** 契约部门树节点（结构化最小面）。 */
export interface OrgSelectContractNode {
  /** 标识。 */
  id: string
  /** 名称。 */
  name: string
  /** 子节点。 */
  children?: unknown[]
}

/** 组织选择契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface OrgSelectContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 对象类型。 */
  readonly kind: string
  /** 候选页码（自 1）。 */
  readonly page: number
  /** 候选总数。 */
  readonly total: number
  /** 候选与已选选项。 */
  readonly items: readonly OrgSelectContractItem[]
  /** 部门树节点。 */
  readonly deptNodes: readonly OrgSelectContractNode[]
  /** 选中标识。 */
  readonly selectedIds: readonly string[]
  /** 多选超限标记。 */
  readonly limitExceeded: boolean
  /** 错误码。 */
  readonly errorCode: number | undefined
  /** 错误文案。 */
  readonly errorMessage: string
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: OrgSourceAdapter | undefined): void
  /** 注入 / 移除用户展示能力。 */
  setUserDisplay(display: unknown): void
  /** 切换对象类型。 */
  setKind(kind: string): void
  /** 设置关键词。 */
  setKeyword(keyword: string): void
  /** 设置部门过滤。 */
  setDeptFilter(deptId: string, includeChildren?: boolean): void
  /** 设置状态过滤。 */
  setStatus(status: string): void
  /** 设置多选。 */
  setMultiple(value: boolean): void
  /** 设置多选上限。 */
  setLimit(limit: number): void
  /** 设置候选页码。 */
  setPage(page: number): void
  /** 同步多选超限标记。 */
  setLimitExceeded(value: boolean): void
  /** 设置受控值。 */
  setValue(value: string | string[] | undefined): void
  /** 加载候选。 */
  load(): Promise<void>
  /** 批量回显。 */
  resolve(ids?: readonly string[]): Promise<void>
  /** 加载部门树。 */
  loadDeptTree(): Promise<void>
  /** 失效缓存。 */
  invalidate(kind?: string): void
  /** 选中 / 取消选中。 */
  toggle(id: string): void
  /** 移除选中。 */
  remove(id: string): void
  /** 清空选中。 */
  clearSelection(): void
  /** 展示文案。 */
  labelOf(id: string): string
  /** 选中回显文本。 */
  selectionText(): string
  /** 上限提示文案。 */
  limitText(): string
  /** 按值回显文案。 */
  getLabel(value: string | string[]): string | undefined
}

/** 数据源桩（记录调用轨迹与查询入参）。 */
export interface OrgSourceStub {
  /** 数据源实现。 */
  source: OrgSourceAdapter
  /** 调用轨迹。 */
  calls: string[]
  /** 查询入参轨迹。 */
  queries: Record<string, unknown>[]
}

/**
 * 创建组织数据源桩（记录调用轨迹）。
 *
 * @param overrides 覆盖方法。
 * @returns 数据源桩。
 */
export function createOrgSourceStub(overrides: OrgSourceAdapter = {}): OrgSourceStub {
  const calls: string[] = []
  const queries: Record<string, unknown>[] = []
  const source: OrgSourceAdapter = {
    searchUsers: async (query) => {
      calls.push('searchUsers')
      queries.push({ ...query })
      return { list: ORG_CONTRACT_USERS, total: ORG_CONTRACT_USERS.length }
    },
    searchPosts: async (query) => {
      calls.push('searchPosts')
      queries.push({ ...query })
      return { list: ORG_CONTRACT_POSTS, total: ORG_CONTRACT_POSTS.length }
    },
    loadDeptTree: async (query) => {
      calls.push('loadDeptTree')
      queries.push({ ...query })
      return ORG_CONTRACT_DEPTS
    },
    resolveNames: async (query) => {
      calls.push('resolveNames')
      queries.push({ ids: [...query.ids] })
      return query.ids.map(
        (id) =>
          ORG_CONTRACT_REFS.find((ref) => ref.id === id) ?? {
            id,
            name: '',
            target: query.target,
            exists: false,
            status: 'disabled',
          },
      )
    },
    ...overrides,
  }
  return { source, calls, queries }
}

/**
 * 组织选择契约（`06_05` 冻结；后续移动端复用同一套断言）。
 *
 * 目标约定：用户 `u1`（启用）/ `u2`（停用）、岗位 `p1`、部门树两节点、
 * 回显 `u1` / `u2` 命中、`u9` 未命中（`exists=false`）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeOrgSelectContract(name: string, create: () => OrgSelectContractTarget): void {
  describe(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      const stub = createOrgSourceStub()
      target.setSource(stub.source)
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)

      await target.load()
      await target.resolve(['u1'])
      await target.loadDeptTree()
      expect(target.requestCount).toBe(0)
      expect(stub.calls).toEqual([])
      expect(target.items).toEqual([])
      expect(target.deptNodes).toEqual([])
    })

    it('未注入数据源时不请求（就绪亦占位）', async () => {
      const target = create()
      target.setReady(true)
      await target.load()
      target.setValue('u1')
      await target.resolve()
      await target.loadDeptTree()
      expect(target.degraded).toBe(false)
      expect(target.requestCount).toBe(0)
      expect(target.items).toEqual([])
    })

    it('三类派发：用户 / 岗位查询与部门树一次性加载', async () => {
      const target = create()
      const stub = createOrgSourceStub()
      target.setReady(true)
      target.setSource(stub.source)

      target.setKind('user')
      await target.load()
      expect(stub.calls).toEqual(['searchUsers'])
      expect(target.items).toHaveLength(2)
      expect(target.labelOf('u1')).toBe('张三')
      expect(target.labelOf('u2')).toBe('李四（停用）')

      target.setKind('post')
      await target.load()
      expect(stub.calls).toEqual(['searchUsers', 'searchPosts'])
      expect(target.labelOf('p1')).toBe('研发经理')

      target.setKind('dept')
      await target.load()
      expect(stub.calls).toEqual(['searchUsers', 'searchPosts', 'loadDeptTree'])
      expect(target.deptNodes).toHaveLength(1)
      expect(target.deptNodes[0]?.children).toHaveLength(1)

      target.setKind('user')
      target.setPage(2)
      await target.load()
      expect(stub.queries.at(-1)?.page).toBe(2)
      expect(target.total).toBe(2)
    })

    it('查询参数：关键词 / 部门与含下级 / 状态 / 分页', async () => {
      const target = create()
      const stub = createOrgSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('user')
      target.setKeyword(' 张 ')
      target.setDeptFilter('d1', true)
      target.setStatus('enabled')
      await target.load()
      expect(stub.queries[0]).toEqual({
        keyword: '张',
        deptId: 'd1',
        includeChildren: true,
        status: 'enabled',
        page: 1,
        pageSize: 20,
      })
    })

    it('关键词结果短缓存：命中不重复请求，失效后重新请求', async () => {
      const target = create()
      const stub = createOrgSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('user')

      await target.load()
      await target.load()
      expect(target.requestCount).toBe(1)

      target.setKeyword('李')
      await target.load()
      expect(target.requestCount).toBe(2)

      target.invalidate()
      await target.load()
      expect(target.requestCount).toBe(3)
    })

    it('批量回显：单请求、已删除 / 停用标记、已解析不重复请求', async () => {
      const target = create()
      const stub = createOrgSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('user')
      target.setValue(['u1', 'u2', 'u9'])
      await target.resolve()
      expect(stub.calls).toEqual(['resolveNames'])
      expect(stub.queries[0]?.ids).toEqual(['u1', 'u2', 'u9'])
      expect(target.labelOf('u1')).toBe('张三')
      expect(target.labelOf('u9')).toBe('u9（已删除）')
      expect(target.getLabel(['u1', 'u9'])).toBe('张三、u9（已删除）')

      await target.resolve()
      expect(target.requestCount).toBe(1)
    })

    it('多选去重 / 上限截断 / 移除 / 清空；单选整体替换', () => {
      const target = create()
      target.setMultiple(true)
      target.setLimit(2)
      target.toggle('u1')
      target.toggle('u1')
      expect(target.selectedIds).toEqual([])

      target.toggle('u1')
      target.toggle('u2')
      expect(target.selectedIds).toEqual(['u1', 'u2'])
      expect(target.limitExceeded).toBe(false)

      target.toggle('p1')
      expect(target.selectedIds).toEqual(['u1', 'u2'])
      expect(target.limitExceeded).toBe(true)
      expect(target.limitText()).toBe('最多选择 2 人')
      target.setLimitExceeded(false)
      expect(target.limitExceeded).toBe(false)

      target.remove('u1')
      expect(target.selectedIds).toEqual(['u2'])
      target.clearSelection()
      expect(target.selectedIds).toEqual([])
      expect(target.selectionText()).toBe('—')

      target.setMultiple(false)
      target.toggle('u1')
      target.toggle('u2')
      expect(target.selectedIds).toEqual(['u2'])
      target.toggle('u2')
      expect(target.selectedIds).toEqual(['u2'])
    })

    it('用户展示花名册：用户选项汇入 BaseUserDisplay', async () => {
      const target = create()
      const stub = createOrgSourceStub()
      const users: Record<string, { name: string; status?: string; deleted?: boolean }> = {}
      target.setUserDisplay({
        mergeUsers(items: readonly { id: string; name: string; status?: string; deleted?: boolean }[]) {
          for (const item of items) {
            users[item.id] = { name: item.name, status: item.status, deleted: item.deleted }
          }
        },
      })
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('user')
      await target.load()
      expect(users.u1?.name).toBe('张三')
      expect(users.u1?.status).toBe('active')
      expect(users.u2?.status).toBe('disabled')
    })

    it('错误码与错误态', async () => {
      const target = create()
      const stub = createOrgSourceStub({
        searchUsers: async () => {
          throw Object.assign(new Error('boom'), { code: 30101 })
        },
      })
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('user')
      await target.load()
      expect(target.errorCode).toBe(30101)
      expect(target.errorMessage).toBe('组织数据源不可用')
    })

    it('竞态：旧响应不覆盖新响应', async () => {
      let resolveFirst: ((value: unknown) => void) | undefined
      let call = 0
      const stub = createOrgSourceStub({
        searchUsers: async () => {
          call += 1
          if (call === 1) {
            return new Promise((resolve) => {
              resolveFirst = resolve
            })
          }
          return { list: [{ id: 'b1', nickname: '乙', status: 'enabled' }], total: 1 }
        },
      })
      const target = create()
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('user')
      target.setKeyword('甲')
      const first = target.load()
      target.setKeyword('乙')
      await target.load()
      expect(target.labelOf('b1')).toBe('乙')
      resolveFirst?.({ list: [{ id: 'a1', nickname: '甲', status: 'enabled' }], total: 1 })
      await first
      expect(target.labelOf('a1')).toBe('a1')
      expect(target.labelOf('b1')).toBe('乙')
    })
  })
}
