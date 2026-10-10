/**
 * 表格契约（`@bms/core/testing`）。
 *
 * 通用表格（`07_05`）/ 移动端与后续列表件为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 分页夹取、多列排序叠加与参数序列化、密度映射、列归一与末列保护、多选与树形展开。
 */
import { describe, expect, it } from 'vitest';
/**
 * 表格契约（`07_05` 冻结；真实实现与后续列表件继续跑同一套件）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeTableContract(name, create) {
    describe(name, () => {
        it('分页夹取与回第 1 页', () => {
            const target = create();
            target.setPage(3);
            expect(target.page).toBe(3);
            target.setPage(-5);
            expect(target.page).toBe(1);
            target.setPageSize(500);
            expect(target.pageSize).toBe(200);
            target.setPageSize(0);
            expect(target.pageSize).toBe(20);
            target.setPage(4);
            target.resetToFirstPage();
            expect(target.page).toBe(1);
        });
        it('多列排序：叠加 ≤ 3 列、方向切换与参数序列化', () => {
            const target = create();
            const a = { key: 'a', title: 'A' };
            const b = { key: 'b', title: 'B' };
            const c = { key: 'c', title: 'C' };
            const d = { key: 'd', title: 'D' };
            expect(target.toggleSort(a)).toEqual([{ field: 'a', order: 'asc' }]);
            expect(target.toggleSort(b, true)).toEqual([
                { field: 'a', order: 'asc' },
                { field: 'b', order: 'asc' },
            ]);
            expect(target.toggleSort(c, true)).toHaveLength(3);
            expect(target.toggleSort(d, true)).toHaveLength(3);
            expect(target.sortParams()).toEqual({ order_by: 'a,b,c', order: ['asc', 'asc', 'asc'] });
            expect(target.toggleSort(a)).toEqual([{ field: 'a', order: 'desc' }]);
            expect(target.toggleSort(a)).toEqual([]);
            expect(target.sortParams()).toEqual({});
        });
        it('密度：持久化取值 default|small，根密度映射 compact', () => {
            const target = create();
            target.setListDensity('small');
            expect(target.listDensity).toBe('small');
            expect(target.densityToken).toBe('compact');
            target.setListDensity('default');
            expect(target.listDensity).toBe('default');
            expect(target.densityToken).toBe('default');
        });
        it('列归一：剔除已删列、追加新增列、末列不可隐藏', () => {
            const target = create();
            target.normalizeColumns([{ key: 'a' }, { key: 'b' }]);
            expect(target.columnKeys).toEqual(['a', 'b']);
            target.setVisible('b', false);
            expect(target.columnKeys).toEqual(['a']);
            target.setVisible('a', false);
            expect(target.columnKeys).toEqual(['a']);
            target.setVisible('b', true);
            target.normalizeColumns([{ key: 'b' }, { key: 'c' }]);
            expect(target.columnKeys).toEqual(['b', 'c']);
        });
        it('多选与树形展开', () => {
            const target = create();
            target.setRows([{ id: 1 }, { id: 2 }], 2);
            expect(target.total).toBe(2);
            target.toggleSelect('1');
            expect(target.selectedKeys).toEqual(['1']);
            target.toggleSelect('1');
            expect(target.selectedKeys).toEqual([]);
            target.expandAll();
            expect(target.expandedKeys).toEqual(['1', '2']);
            target.collapseAll();
            expect(target.expandedKeys).toEqual([]);
            target.toggleExpand('2');
            expect(target.expandedKeys).toEqual(['2']);
        });
        it('树形默认展开：按规模自适应（≤ 阈值全展开、超过只展第一层）', () => {
            const target = create();
            const tree = [{ id: 'a', children: [{ id: 'b', children: [{ id: 'c' }] }, { id: 'd' }] }];
            target.setRows(tree, 1);
            target.setTreeExpandThreshold(10);
            expect(target.treeExpandThreshold).toBe(10);
            expect([...target.defaultExpandKeys()].sort()).toEqual(['a', 'b']);
            target.setTreeExpandThreshold(1);
            expect(target.defaultExpandKeys()).toEqual(['a']);
        });
        it('搜索命中：祖先路径展开', () => {
            const target = create();
            const tree = [{ id: 'a', children: [{ id: 'b', children: [{ id: 'c' }] }, { id: 'd' }] }];
            target.setRows(tree, 1);
            target.expandAncestorsFor((row) => row.id === 'c');
            expect([...target.expandedKeys].sort()).toEqual(['a', 'b']);
        });
    });
}
