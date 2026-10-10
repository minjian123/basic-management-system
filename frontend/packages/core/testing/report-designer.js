/**
 * 报表设计器编排契约（`@bms/core/testing`）。
 *
 * 报表设计器与后续同契约实现（大屏复用编排口径）在本套件中传入适配器跑同一套断言：
 * 占位零请求、取数基线、只读不动作、增删改与网格夹取、脏拦截、保存发布另存、预览、防重复。
 */
import { describe, expect, it } from 'vitest';
/** 契约数据集。 */
export const REPORT_CONTRACT_DATASETS = [
    {
        id: 'd1',
        code: 'sales_monthly',
        name: '销售月报',
        status: 'enabled',
        fields: [
            { name: 'month', type: 'text' },
            { name: 'receipt', type: 'number' },
        ],
    },
    { id: 'd2', code: 'stopped', name: '已停用', status: 'disabled', fields: [{ name: 'region', type: 'text' }] },
];
/** 契约初始图表项。 */
export const REPORT_CONTRACT_CHARTS = [
    { id: 'chart-1', datasetId: 'd1', chartType: 'bar', title: '销售趋势', layout: { x: 0, y: 0, w: 6, h: 4 } },
];
/** 契约取数快照。 */
export const REPORT_CONTRACT_SNAPSHOT = {
    code: 'sales_report',
    name: '销售月报',
    charts: REPORT_CONTRACT_CHARTS,
};
/**
 * 创建契约处理函数（记录调用轨迹）。
 *
 * @param onSave 保存钩子（失败用例可抛错）。
 * @returns 处理函数集。
 */
export function createReportJobs(onSave) {
    const calls = [];
    return {
        calls,
        load: async () => {
            calls.push('load');
            return REPORT_CONTRACT_SNAPSHOT;
        },
        save: async () => {
            calls.push('save');
            return onSave !== undefined ? onSave() : { recordVersion: 3 };
        },
        publish: async () => {
            calls.push('publish');
        },
        saveAs: async () => {
            calls.push('saveAs');
            return { recordVersion: 1 };
        },
        preview: async () => {
            calls.push('preview');
            return { columns: [{ name: 'month', type: 'text' }], rows: [{ month: '1月' }] };
        },
    };
}
/**
 * 报表设计器编排契约（`08-9-1`）。
 *
 * 断言：占位零请求；就绪未注入处理函数零请求；取数装载与基线；只读不动作不写脏；
 * 增删改与网格夹取；脏判定与拦截；保存成功清脏 / 失败保留；发布与另存；预览；防重复。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeReportDesignerContract(name, create) {
    describe(name, () => {
        it('未就绪时降级，取数 / 保存 / 发布零请求', async () => {
            const target = create();
            target.setReady(false);
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            expect(target.requestCount).toBe(0);
            await target.load();
            await target.save();
            await target.publish();
            expect(target.requestCount).toBe(0);
        });
        it('就绪后不再降级，未注入处理函数仍零请求', async () => {
            const target = create();
            target.setReady(true);
            expect(target.degraded).toBe(false);
            await target.load();
            expect(target.requestCount).toBe(0);
        });
        it('取数装载图表项并记基线', async () => {
            const target = create();
            const jobs = createReportJobs();
            target.setJobs(jobs);
            await target.load();
            expect(target.requestCount).toBe(1);
            expect(target.charts()).toHaveLength(1);
            expect(target.dirty).toBe(false);
            expect(jobs.calls).toContain('load');
        });
        it('只读（无权限）时结构操作不动作且不写脏', () => {
            const target = create();
            target.setOperators({ codes: [] });
            const before = target.charts().length;
            expect(target.addChart({ datasetId: 'd1', chartType: 'line' })).toBeUndefined();
            expect(target.removeChart('chart-1')).toBe(false);
            expect(target.charts()).toHaveLength(before);
            target.markBaseline();
            expect(target.dirty).toBe(false);
        });
        it('增删改与网格夹取', () => {
            const target = create();
            target.setOperators({ codes: ['rpt:design'] });
            const created = target.addChart({ datasetId: 'd1', chartType: 'line' });
            expect(created).toBeDefined();
            expect(target.charts()).toHaveLength(2);
            const id = created?.id ?? '';
            expect(target.moveChart(id, 99, 0)).toBe(true);
            const moved = target.charts().find((item) => item.id === id);
            expect(moved?.layout.x).toBeLessThanOrEqual(12 - (moved?.layout.w ?? 0));
            expect(target.resizeChart(id, 99, 99)).toBe(true);
            const resized = target.charts().find((item) => item.id === id);
            expect(resized?.layout.w).toBe(12);
            expect(target.updateChart(id, { title: '改名' })).toBe(true);
            expect(target.charts().find((item) => item.id === id)?.title).toBe('改名');
            expect(target.duplicateChart(id)).toBe(true);
            expect(target.removeChart(id)).toBe(true);
            expect(target.charts().some((item) => item.id === id)).toBe(false);
        });
        it('选中联动', () => {
            const target = create();
            target.selectChart('chart-1');
            expect(target.selectedId()).toBe('chart-1');
            target.selectChart(null);
            expect(target.selectedId()).toBe('');
        });
        it('脏判定与拦截与撤销', () => {
            const target = create();
            target.setOperators({ codes: ['rpt:design'] });
            target.markBaseline();
            expect(target.dirty).toBe(false);
            target.addChart({ datasetId: 'd1', chartType: 'bar' });
            expect(target.dirty).toBe(true);
            expect(target.needsBlock('leave')).toBe(true);
            expect(target.discard()).toBe(true);
            expect(target.dirty).toBe(false);
        });
        it('保存成功清脏、失败保留本地与脏标记', async () => {
            const target = create();
            target.setOperators({ codes: ['rpt:design'] });
            const jobs = createReportJobs();
            target.setJobs(jobs);
            target.markBaseline();
            target.addChart({ datasetId: 'd1', chartType: 'bar' });
            expect(target.dirty).toBe(true);
            const result = await target.save();
            expect(result).toEqual({ recordVersion: 3 });
            expect(target.dirty).toBe(false);
            const failing = create();
            failing.setOperators({ codes: ['rpt:design'] });
            failing.setJobs(createReportJobs(async () => {
                throw new Error('500');
            }));
            failing.markBaseline();
            failing.addChart({ datasetId: 'd1', chartType: 'bar' });
            const failed = await failing.save();
            expect(failed).toBeUndefined();
            expect(failing.dirty).toBe(true);
        });
        it('发布与另存为', async () => {
            const target = create();
            const jobs = createReportJobs();
            target.setJobs(jobs);
            expect(await target.publish()).toBe(true);
            expect(await target.saveAs('r2', '副本')).toEqual({ recordVersion: 1 });
            expect(jobs.calls).toContain('publish');
            expect(jobs.calls).toContain('saveAs');
        });
        it('预览取数', async () => {
            const target = create();
            const jobs = createReportJobs();
            target.setJobs(jobs);
            const result = await target.preview('chart-1');
            expect(result?.rows).toHaveLength(1);
            expect(jobs.calls).toContain('preview');
            const noJobs = create();
            await expect(noJobs.preview('chart-1')).resolves.toBeUndefined();
        });
        it('校验与停用数据集', () => {
            const target = create();
            target.setOperators({ codes: ['rpt:design'] });
            expect(target.validation().valid).toBe(true);
            target.addChart({ datasetId: 'd1', chartType: 'bar' });
            expect(target.validation().valid).toBe(true);
        });
    });
}
