/**
 * 表单布局元数据契约与设计器编排契约（`@bms/core/testing`）。
 *
 * 设计器 / 渲染器 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言。
 */
import { describe, expect, it } from 'vitest';
import { layoutEqual, toRenderMetadata, } from '../src';
/** 契约字段清单：平台字段 `name` + 租户自建 `project_no`。 */
export const FORM_CONTRACT_FIELDS = [
    { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active' },
    { key: 'remark', label: '备注', type: 'longtext', group: 'platform', status: 'active' },
    { key: 'project_no', label: '项目编号', type: 'text', group: 'tenant', status: 'active' },
    { key: 'ext_broken', label: '建列失败字段', type: 'text', group: 'tenant', status: 'failed' },
];
/** 契约布局工厂：单分区多字段。 */
export function contractLayout(keys = ['name']) {
    return {
        main: {
            labelPosition: 'top',
            sections: [{ key: 's1', title: '基本信息', columns: 2, fields: keys.map((key) => ({ key })) }],
        },
    };
}
/**
 * 元数据契约（`domain/form-layout` + `BaseFormDesigner` 的布局语义；`08-6-1` 首次落地，`08-6-2` 渲染器复用）。
 *
 * 目标约定：字段清单为 `FORM_CONTRACT_FIELDS`；初始层级 `tenant`、布局 `contractLayout(['name'])`、
 * 已注入维护权限（`formdesign:manage`）与注册类型（含 `text` / `longtext`）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeFormLayoutContract(name, create) {
    describe(name, () => {
        it('空布局回退默认栅格（保无配置可用）', () => {
            const target = create();
            target.setLayouts({});
            target.setFields(FORM_CONTRACT_FIELDS);
            const effective = target.effective();
            expect(effective.fallback).toBe(true);
            expect(effective.source).toBe('empty');
            expect(effective.layout.main.sections).toHaveLength(1);
            expect(effective.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual([
                'name',
                'remark',
                'project_no',
            ]);
        });
        it('三级层级解析与逐级回退（角色 → 租户 → 平台 → 空布局）', () => {
            const target = create();
            target.setFields(FORM_CONTRACT_FIELDS);
            target.setLayouts({ platform: contractLayout(['name']), tenant: contractLayout(['name', 'remark']) });
            target.setLevel('role');
            expect(target.effective().source).toBe('tenant');
            expect(target.effective().layout.main.sections[0]?.fields).toHaveLength(2);
            target.setLevel('tenant');
            expect(target.effective().source).toBe('tenant');
            target.setLayouts({ platform: contractLayout(['name']) });
            target.setLevel('tenant');
            expect(target.effective().source).toBe('platform');
            target.setLayouts({});
            expect(target.effective().source).toBe('empty');
        });
        it('平台默认层级只读', () => {
            const target = create();
            target.setFields(FORM_CONTRACT_FIELDS);
            target.setLayouts({ platform: contractLayout(['name']) });
            target.setLevel('tenant');
            expect(target.readonly).toBe(false);
            target.setLevel('platform');
            expect(target.readonly).toBe(true);
        });
        it('结构操作：插入幂等、跨分区移动、删分区连带引用', () => {
            const target = create();
            target.setLayouts({ tenant: contractLayout(['name']) });
            target.setLevel('tenant');
            target.markBaseline();
            expect(target.addField('name')).toBe(false);
            expect(target.addField('remark')).toBe(true);
            expect(target.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark']);
            const sectionKey = target.addSection();
            expect(sectionKey).not.toBe('');
            expect(target.moveField({ fieldKey: 'remark', toSectionKey: sectionKey })).toBe(true);
            const sections = target.layout.main.sections;
            expect(sections[0]?.fields.map((field) => field.key)).toEqual(['name']);
            expect(sections[1]?.fields.map((field) => field.key)).toEqual(['remark']);
            expect(target.removeSection(sectionKey)).toBe(true);
            expect(target.layout.main.sections).toHaveLength(1);
            expect(target.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name']);
        });
        it('分区内排序按移出后索引落位', () => {
            const target = create();
            target.setLayouts({ tenant: contractLayout(['name', 'remark', 'project_no']) });
            target.setLevel('tenant');
            target.markBaseline();
            expect(target.moveField({ fieldKey: 'name', toSectionKey: 's1', index: 2 })).toBe(true);
            expect(target.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['remark', 'project_no', 'name']);
        });
        it('跨列翻转、列数夹取、标签宽度夹取', () => {
            const target = create();
            target.setLayouts({ tenant: contractLayout(['name', 'remark']) });
            target.setLevel('tenant');
            target.markBaseline();
            expect(target.toggleColSpan('name')).toBe(true);
            expect(target.layout.main.sections[0]?.fields[0]?.colSpan).toBe(true);
            expect(target.toggleColSpan('name')).toBe(true);
            expect(target.layout.main.sections[0]?.fields[0]?.colSpan).toBeUndefined();
            expect(target.setColumns('s1', 9)).toBe(true);
            expect(target.layout.main.sections[0]?.columns).toBe(3);
            expect(target.setColumns('s1', 1)).toBe(true);
            expect(target.layout.main.sections[0]?.columns).toBe(1);
            expect(target.setColumns('absent', 2)).toBe(false);
            expect(target.setLabelWidth(9999)).toBe(true);
            expect(target.layout.main.labelWidth).toBe(400);
            expect(target.setLabelPosition('left')).toBe(true);
            expect(target.layout.main.labelPosition).toBe('left');
        });
        it('查询区与明细区归一（去重保序、宽度夹取）', () => {
            const target = create();
            target.setLayouts({ tenant: contractLayout(['name']) });
            target.setLevel('tenant');
            target.markBaseline();
            expect(target.setQueryFields(['name', 'name', 'remark'])).toBe(true);
            expect(target.layout.query?.fields).toEqual(['name', 'remark']);
            expect(target.setDetailColumns([{ key: 'project_no', width: 9999 }, 'project_no', 'name'])).toBe(true);
            expect(target.layout.detail?.columns).toEqual([{ key: 'project_no', width: 800 }, { key: 'name' }]);
            expect(target.setQueryFields([])).toBe(true);
            expect(target.layout.query).toBeUndefined();
        });
        it('失效与重复引用可识别且不阻断', () => {
            const target = create();
            target.setFields(FORM_CONTRACT_FIELDS);
            target.setLayouts({ tenant: contractLayout(['name', 'absent_key']) });
            target.setLevel('tenant');
            expect(target.unknownFields()).toEqual(['absent_key']);
            expect(target.duplicateFields()).toEqual([]);
            target.setLayouts({
                tenant: {
                    main: {
                        labelPosition: 'top',
                        sections: [
                            { key: 's1', title: '', columns: 2, fields: [{ key: 'name' }] },
                            { key: 's2', title: '', columns: 2, fields: [{ key: 'name' }] },
                        ],
                    },
                },
            });
            target.setLevel('tenant');
            expect(target.duplicateFields()).toEqual(['name']);
        });
        it('校验：引用失效 / 停用 / 重复 / 空分区逐项入错', () => {
            const target = create();
            target.setFields(FORM_CONTRACT_FIELDS);
            target.setLayouts({ tenant: contractLayout(['name']) });
            target.setLevel('tenant');
            target.markBaseline();
            expect(target.validation().valid).toBe(true);
            target.setLayouts({ tenant: contractLayout(['name', 'ext_broken']) });
            target.setLevel('tenant');
            expect(target.validation().valid).toBe(false);
            expect(target.validation().errors.map((issue) => issue.kind)).toContain('disabled-field');
            const sectionKey = target.addSection();
            expect(target.validation().errors.some((issue) => issue.kind === 'empty-section' && issue.sectionKey === sectionKey)).toBe(true);
        });
        it('脏基线：改动置脏、撤销回不脏、键序无关', () => {
            const target = create();
            target.setLayouts({ tenant: contractLayout(['name']) });
            target.setLevel('tenant');
            target.markBaseline();
            expect(target.dirty).toBe(false);
            target.addField('remark');
            expect(target.dirty).toBe(true);
            expect(target.discard()).toBe(true);
            expect(target.dirty).toBe(false);
            expect(target.discard()).toBe(false);
            target.setLayouts({
                tenant: {
                    main: {
                        labelPosition: 'top',
                        sections: [{ key: 's1', title: '基本信息', columns: 2, fields: [{ key: 'name', colSpan: false }] }],
                    },
                },
            });
            target.setLevel('tenant');
            target.markBaseline();
            expect(target.dirty).toBe(false);
        });
        it('渲染输入与设计产出同形（设计 → 渲染一致）', () => {
            const target = create();
            target.setFields(FORM_CONTRACT_FIELDS);
            target.setLayouts({ tenant: contractLayout(['name', 'remark']) });
            target.setLevel('tenant');
            target.markBaseline();
            expect(layoutEqual(target.renderMetadata().layout, target.layout)).toBe(true);
            expect(target.renderMetadata()).toEqual(toRenderMetadata(target.effective()));
            expect(target.renderMetadata().fields.map((field) => field.key)).toEqual([
                'name',
                'remark',
                'project_no',
                'ext_broken',
            ]);
        });
    });
}
/**
 * 设计器编排契约（`BaseFormDesigner`；`08-6-1` 首次落地）。
 *
 * 目标约定：表单 `leave`、层级 `tenant`、初始未注入处理函数与权限上下文（按有权）；
 * 取数返回两级层布局（`tenant` 一分区一字段 / `platform` 一分区两字段）与 `FORM_CONTRACT_FIELDS`；
 * 保存返回 `{ recordVersion: 3 }`；自建字段返回 `{ fieldKey: 'ext_no', columnName: 'ext_ext_no', ddlStatus: 'pending' }`。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeFormDesignerContract(name, create) {
    /** 契约取数快照。 */
    const snapshot = {
        levels: { tenant: contractLayout(['name']), platform: contractLayout(['name', 'remark']) },
        fields: FORM_CONTRACT_FIELDS,
    };
    /** 构造已就绪且已装载的目标。 */
    const loadedTarget = async (jobs = {}) => {
        const target = create();
        target.setOperators({ codes: ['formdesign:manage'], registeredTypes: ['text', 'longtext'] });
        target.setJobs({ load: async () => snapshot, ...jobs });
        target.setReady(true);
        await target.load();
        return target;
    };
    describe(name, () => {
        it('未就绪时降级且不产生请求', async () => {
            const target = create();
            target.setOperators({ codes: ['formdesign:manage'] });
            target.setJobs({ load: async () => snapshot, save: async () => ({ recordVersion: 1 }) });
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            expect(target.readonly).toBe(true);
            await target.load();
            await expect(target.save()).resolves.toBeUndefined();
            expect(target.requestCount).toBe(0);
        });
        it('就绪但未注入处理函数时不产生请求（占位）', async () => {
            const target = create();
            target.setOperators({ codes: ['formdesign:manage'] });
            target.setReady(true);
            expect(target.degraded).toBe(false);
            await target.load();
            await expect(target.save()).resolves.toBeUndefined();
            expect(target.requestCount).toBe(0);
        });
        it('取数装载层级与字段并记基线（初始不脏）', async () => {
            const target = await loadedTarget();
            expect(target.requestCount).toBe(1);
            expect(target.phase).toBe('done');
            expect(target.fields().map((field) => field.key)).toContain('name');
            expect(target.layout().main.sections[0]?.fields.map((field) => field.key)).toEqual(['name']);
            expect(target.dirty()).toBe(false);
            expect(target.canSave).toBe(true);
            expect(target.canEdit).toBe(true);
        });
        it('只读（平台默认层级）下结构操作不动作且不写脏', async () => {
            const target = await loadedTarget();
            expect(target.setLevel('platform')).toBe(true);
            expect(target.readonly).toBe(true);
            expect(target.canEdit).toBe(false);
            expect(target.addField('project_no')).toBe(false);
            expect(target.setColumns('s1', 3)).toBe(false);
            expect(target.dirty()).toBe(false);
        });
        it('无维护权限时只读且不可编辑', async () => {
            const target = await loadedTarget();
            target.setOperators({ codes: [], registeredTypes: ['text', 'longtext'] });
            expect(target.readonly).toBe(true);
            expect(target.addField('remark')).toBe(false);
            expect(target.dirty()).toBe(false);
            target.setOperators({ codes: ['formdesign:manage'], registeredTypes: ['text', 'longtext'] });
            expect(target.canEdit).toBe(true);
            expect(target.addField('remark')).toBe(true);
        });
        it('拖拽落点：新增 / 跨分区 / 重复拖入拒绝', async () => {
            const target = await loadedTarget();
            expect(target.addField('name')).toBe(false);
            expect(target.addField('remark')).toBe(true);
            expect(target.selected()).toEqual({ kind: 'field', key: 'remark' });
            const sectionKey = target.addSection();
            expect(sectionKey).not.toBe('');
            expect(target.moveField({ fieldKey: 'remark', toSectionKey: sectionKey, fromSectionKey: 's1', crossZone: true })).toBe(true);
            const sections = target.layout().main.sections;
            expect(sections[0]?.fields.map((field) => field.key)).toEqual(['name']);
            expect(sections[1]?.fields.map((field) => field.key)).toEqual(['remark']);
        });
        it('脏判定与拦截（切换表单 / 切换层级）', async () => {
            const target = await loadedTarget();
            expect(target.needsBlock('leave')).toBe(false);
            expect(target.setFormCode('user')).toBe(true);
            target.addField('remark');
            expect(target.dirty()).toBe(true);
            expect(target.needsBlock('leave')).toBe(true);
            expect(target.needsBlock('switch-level')).toBe(true);
            expect(target.setFormCode('other')).toBe(false);
            expect(target.setLevel('role')).toBe(false);
            expect(target.discard()).toBe(true);
            expect(target.needsBlock('leave')).toBe(false);
            expect(target.setLevel('role')).toBe(true);
        });
        it('保存：成功清脏并写回层级，失败保留本地与脏标记', async () => {
            let fail = true;
            const target = await loadedTarget({
                save: async () => {
                    if (fail) {
                        throw new Error('保存失败');
                    }
                    return { recordVersion: 3 };
                },
            });
            target.addField('remark');
            await expect(target.save()).resolves.toBeUndefined();
            expect(target.phase).toBe('failed');
            expect(target.dirty()).toBe(true);
            fail = false;
            await expect(target.save()).resolves.toEqual({ recordVersion: 3 });
            expect(target.phase).toBe('done');
            expect(target.dirty()).toBe(false);
            expect(target.requestCount).toBe(3);
        });
        it('发布：未注入不动作，注入后可发布', async () => {
            const target = await loadedTarget();
            await expect(target.publish()).resolves.toBe(false);
            const published = [];
            target.setJobs({
                publish: async (input) => {
                    published.push(input.formCode);
                },
            });
            await expect(target.publish()).resolves.toBe(true);
            expect(published).toEqual(['leave']);
        });
        it('恢复默认：逐级回退（租户 → 平台）', async () => {
            const restored = [];
            const target = await loadedTarget({
                restore: async (input) => {
                    restored.push(input.level);
                },
            });
            await expect(target.restoreDefault()).resolves.toBe(true);
            expect(restored).toEqual(['tenant']);
            expect(target.layout().main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark']);
            expect(target.dirty()).toBe(false);
        });
        it('自建字段：校验不通过不请求，通过后入清单', async () => {
            const target = await loadedTarget({
                createField: async (input) => ({
                    fieldKey: input.draft.name,
                    columnName: `ext_${input.draft.name}`,
                    ddlStatus: 'pending',
                }),
            });
            const before = target.requestCount;
            await expect(target.createField({ name: '', type: 'text' })).resolves.toBeUndefined();
            await expect(target.createField({ name: 'no', type: 'richtext' })).resolves.toBeUndefined();
            await expect(target.createField({ name: 'no', type: 'select' })).resolves.toBeUndefined();
            await expect(target.createField({ name: 'name', type: 'text' })).resolves.toBeUndefined();
            expect(target.requestCount).toBe(before);
            await expect(target.createField({ name: 'project_no_new', type: 'text' })).resolves.toMatchObject({
                ddlStatus: 'pending',
            });
            expect(target.fields().map((field) => field.key)).toContain('project_no_new');
            expect(target.requestCount).toBe(before + 1);
        });
        it('DDL 重试仅对建列失败字段动作', async () => {
            const target = await loadedTarget({
                retryField: async (input) => ({ fieldKey: input.fieldKey, columnName: 'ext_ext_broken', ddlStatus: 'active' }),
            });
            await expect(target.retryField('name')).resolves.toBeUndefined();
            await expect(target.retryField('ext_broken')).resolves.toMatchObject({ ddlStatus: 'active' });
            expect(target.fields().find((field) => field.key === 'ext_broken')?.status).toBe('active');
        });
        it('进行中重复提交不动作（防重复）', async () => {
            let release = () => undefined;
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            const target = await loadedTarget({
                save: async () => {
                    await gate;
                    return { recordVersion: 1 };
                },
            });
            target.addField('remark');
            const pending = target.save();
            expect(target.busy).toBe(true);
            await expect(target.save()).resolves.toBeUndefined();
            release();
            await expect(pending).resolves.toEqual({ recordVersion: 1 });
            expect(target.requestCount).toBe(2);
        });
    });
}
