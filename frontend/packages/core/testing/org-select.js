/**
 * 组织选择契约（`@bms/core/testing`）。
 *
 * 组件基类 / 投影 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、数据源注入与就绪、三类派发与查询参数、关键词结果缓存、批量回显与
 * 已删除 / 停用标记、多选去重与上限、部门树一次性加载、错误码与重试、用户展示花名册。
 */
import { describe, expect, it } from 'vitest';
/** 契约用户（含停用项）。 */
export const ORG_CONTRACT_USERS = [
    { id: 'u1', nickname: '张三', username: 'zhangsan', deptId: 'd2', status: 'enabled', phone: '138****8000', avatar: 'a.png' },
    { id: 'u2', nickname: '李四', username: 'lisi', deptId: 'd2', status: 'disabled' },
];
/** 契约岗位。 */
export const ORG_CONTRACT_POSTS = [
    { id: 'p1', name: '研发经理', code: 'RD-MGR', deptId: 'd1', status: 'enabled' },
];
/** 契约部门树（嵌套）。 */
export const ORG_CONTRACT_DEPTS = [
    { id: 'd1', code: 'DEPT0001', name: '总部', status: 'enabled', children: [{ id: 'd2', code: 'DEPT0002', name: '研发部', status: 'enabled' }] },
];
/** 契约回显引用（`u2` 停用；未列出的 id 视为已删除）。 */
export const ORG_CONTRACT_REFS = [
    { id: 'u1', name: '张三', target: 'user', exists: true, status: 'enabled' },
    { id: 'u2', name: '李四', target: 'user', exists: true, status: 'disabled' },
    { id: 'u9', name: '', target: 'user', exists: false, status: 'disabled' },
];
/**
 * 创建组织数据源桩（记录调用轨迹）。
 *
 * @param overrides 覆盖方法。
 * @returns 数据源桩。
 */
export function createOrgSourceStub(overrides = {}) {
    const calls = [];
    const queries = [];
    const source = {
        searchUsers: async (query) => {
            calls.push('searchUsers');
            queries.push({ ...query });
            return { list: ORG_CONTRACT_USERS, total: ORG_CONTRACT_USERS.length };
        },
        searchPosts: async (query) => {
            calls.push('searchPosts');
            queries.push({ ...query });
            return { list: ORG_CONTRACT_POSTS, total: ORG_CONTRACT_POSTS.length };
        },
        loadDeptTree: async (query) => {
            calls.push('loadDeptTree');
            queries.push({ ...query });
            return ORG_CONTRACT_DEPTS;
        },
        resolveNames: async (query) => {
            calls.push('resolveNames');
            queries.push({ ids: [...query.ids] });
            return query.ids.map((id) => ORG_CONTRACT_REFS.find((ref) => ref.id === id) ?? {
                id,
                name: '',
                target: query.target,
                exists: false,
                status: 'disabled',
            });
        },
        ...overrides,
    };
    return { source, calls, queries };
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
export function describeOrgSelectContract(name, create) {
    describe(name, () => {
        it('未就绪时降级且不产生请求', async () => {
            const target = create();
            const stub = createOrgSourceStub();
            target.setSource(stub.source);
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            await target.load();
            await target.resolve(['u1']);
            await target.loadDeptTree();
            expect(target.requestCount).toBe(0);
            expect(stub.calls).toEqual([]);
            expect(target.items).toEqual([]);
            expect(target.deptNodes).toEqual([]);
        });
        it('未注入数据源时不请求（就绪亦占位）', async () => {
            const target = create();
            target.setReady(true);
            await target.load();
            target.setValue('u1');
            await target.resolve();
            await target.loadDeptTree();
            expect(target.degraded).toBe(false);
            expect(target.requestCount).toBe(0);
            expect(target.items).toEqual([]);
        });
        it('三类派发：用户 / 岗位查询与部门树一次性加载', async () => {
            const target = create();
            const stub = createOrgSourceStub();
            target.setReady(true);
            target.setSource(stub.source);
            target.setKind('user');
            await target.load();
            expect(stub.calls).toEqual(['searchUsers']);
            expect(target.items).toHaveLength(2);
            expect(target.labelOf('u1')).toBe('张三');
            expect(target.labelOf('u2')).toBe('李四（停用）');
            target.setKind('post');
            await target.load();
            expect(stub.calls).toEqual(['searchUsers', 'searchPosts']);
            expect(target.labelOf('p1')).toBe('研发经理');
            target.setKind('dept');
            await target.load();
            expect(stub.calls).toEqual(['searchUsers', 'searchPosts', 'loadDeptTree']);
            expect(target.deptNodes).toHaveLength(1);
            expect(target.deptNodes[0]?.children).toHaveLength(1);
            target.setKind('user');
            target.setPage(2);
            await target.load();
            expect(stub.queries.at(-1)?.page).toBe(2);
            expect(target.total).toBe(2);
        });
        it('查询参数：关键词 / 部门与含下级 / 状态 / 分页', async () => {
            const target = create();
            const stub = createOrgSourceStub();
            target.setReady(true);
            target.setSource(stub.source);
            target.setKind('user');
            target.setKeyword(' 张 ');
            target.setDeptFilter('d1', true);
            target.setStatus('enabled');
            await target.load();
            expect(stub.queries[0]).toEqual({
                keyword: '张',
                deptId: 'd1',
                includeChildren: true,
                status: 'enabled',
                page: 1,
                pageSize: 20,
            });
        });
        it('关键词结果短缓存：命中不重复请求，失效后重新请求', async () => {
            const target = create();
            const stub = createOrgSourceStub();
            target.setReady(true);
            target.setSource(stub.source);
            target.setKind('user');
            await target.load();
            await target.load();
            expect(target.requestCount).toBe(1);
            target.setKeyword('李');
            await target.load();
            expect(target.requestCount).toBe(2);
            target.invalidate();
            await target.load();
            expect(target.requestCount).toBe(3);
        });
        it('批量回显：单请求、已删除 / 停用标记、已解析不重复请求', async () => {
            const target = create();
            const stub = createOrgSourceStub();
            target.setReady(true);
            target.setSource(stub.source);
            target.setKind('user');
            target.setValue(['u1', 'u2', 'u9']);
            await target.resolve();
            expect(stub.calls).toEqual(['resolveNames']);
            expect(stub.queries[0]?.ids).toEqual(['u1', 'u2', 'u9']);
            expect(target.labelOf('u1')).toBe('张三');
            expect(target.labelOf('u9')).toBe('u9（已删除）');
            expect(target.getLabel(['u1', 'u9'])).toBe('张三、u9（已删除）');
            await target.resolve();
            expect(target.requestCount).toBe(1);
        });
        it('多选去重 / 上限截断 / 移除 / 清空；单选整体替换', () => {
            const target = create();
            target.setMultiple(true);
            target.setLimit(2);
            target.toggle('u1');
            target.toggle('u1');
            expect(target.selectedIds).toEqual([]);
            target.toggle('u1');
            target.toggle('u2');
            expect(target.selectedIds).toEqual(['u1', 'u2']);
            expect(target.limitExceeded).toBe(false);
            target.toggle('p1');
            expect(target.selectedIds).toEqual(['u1', 'u2']);
            expect(target.limitExceeded).toBe(true);
            expect(target.limitText()).toBe('最多选择 2 人');
            target.setLimitExceeded(false);
            expect(target.limitExceeded).toBe(false);
            target.remove('u1');
            expect(target.selectedIds).toEqual(['u2']);
            target.clearSelection();
            expect(target.selectedIds).toEqual([]);
            expect(target.selectionText()).toBe('—');
            target.setMultiple(false);
            target.toggle('u1');
            target.toggle('u2');
            expect(target.selectedIds).toEqual(['u2']);
            target.toggle('u2');
            expect(target.selectedIds).toEqual(['u2']);
        });
        it('用户展示花名册：用户选项汇入 BaseUserDisplay', async () => {
            const target = create();
            const stub = createOrgSourceStub();
            const users = {};
            target.setUserDisplay({
                mergeUsers(items) {
                    for (const item of items) {
                        users[item.id] = { name: item.name, status: item.status, deleted: item.deleted };
                    }
                },
            });
            target.setReady(true);
            target.setSource(stub.source);
            target.setKind('user');
            await target.load();
            expect(users.u1?.name).toBe('张三');
            expect(users.u1?.status).toBe('active');
            expect(users.u2?.status).toBe('disabled');
        });
        it('错误码与错误态', async () => {
            const target = create();
            const stub = createOrgSourceStub({
                searchUsers: async () => {
                    throw Object.assign(new Error('boom'), { code: 30101 });
                },
            });
            target.setReady(true);
            target.setSource(stub.source);
            target.setKind('user');
            await target.load();
            expect(target.errorCode).toBe(30101);
            expect(target.errorMessage).toBe('组织数据源不可用');
        });
        it('竞态：旧响应不覆盖新响应', async () => {
            let resolveFirst;
            let call = 0;
            const stub = createOrgSourceStub({
                searchUsers: async () => {
                    call += 1;
                    if (call === 1) {
                        return new Promise((resolve) => {
                            resolveFirst = resolve;
                        });
                    }
                    return { list: [{ id: 'b1', nickname: '乙', status: 'enabled' }], total: 1 };
                },
            });
            const target = create();
            target.setReady(true);
            target.setSource(stub.source);
            target.setKind('user');
            target.setKeyword('甲');
            const first = target.load();
            target.setKeyword('乙');
            await target.load();
            expect(target.labelOf('b1')).toBe('乙');
            resolveFirst?.({ list: [{ id: 'a1', nickname: '甲', status: 'enabled' }], total: 1 });
            await first;
            expect(target.labelOf('a1')).toBe('a1');
            expect(target.labelOf('b1')).toBe('乙');
        });
    });
}
