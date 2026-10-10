/**
 * `@bms/core/testing`：契约用例工厂（仅测试消费）。
 *
 * 各渲染插件（`ui-ep` / `ui-vant`）与绑定层在自己的 spec 中调用本工厂并传入本实现，
 * 跑同一套断言——「同接口多实现」的机器保障。运行时入口（`@bms/core`）不含本入口。
 *
 * 契约面为**结构化接口**（非具体基类），实现侧可用基类实例或投影适配器接入。
 */
import { describe, expect, it } from 'vitest';
export * from './form-layout';
export * from './form-render';
export * from './message-catalog';
export * from './approval-flow';
export * from './process-modeler';
export * from './chart';
export * from './report-designer';
export * from './screen-designer';
export * from './screen-player';
export * from './table';
export * from './query-scheme';
export * from './status';
export * from './metric';
export * from './notification';
export * from './ai-assistant';
export * from './search';
export * from './org-select';
export * from './dict';
export * from './file-upload';
export * from './captcha';
export * from './multilingual-name';
export * from './module';
/**
 * 登记一个契约用例套件（「同一契约、多实现」的统一入口）。
 *
 * @param name 契约名（如「受控值契约」）。
 * @param define 套件定义体（在各实现 spec 中传入本实现后执行同一套断言）。
 */
export function describeContract(name, define) {
    describe(name, define);
}
/**
 * 值契约（`BaseValue` / `useValue` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 * @param sample 非空样例值。
 */
export function describeValueContract(name, create, sample) {
    describeContract(name, () => {
        it('初始为空态', () => {
            const target = create();
            expect(target.value).toBeUndefined();
            expect(target.isEmpty).toBe(true);
        });
        it('设置值并订阅变更（同值不重复通知）', () => {
            const target = create();
            const seen = [];
            target.onChange((value) => seen.push(value));
            target.setValue(sample);
            expect(target.value).toBe(sample);
            expect(target.isEmpty).toBe(false);
            target.setValue(sample);
            expect(seen).toEqual([sample]);
            target.setValue(undefined);
            expect(target.isEmpty).toBe(true);
            expect(seen).toEqual([sample, undefined]);
        });
    });
}
/**
 * 权限契约（`BaseAccess` / `useAccess` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePermissionContract(name, create) {
    describeContract(name, () => {
        it('设置权限码并判定（含空集边界）', () => {
            const target = create();
            target.setCodes(['a', 'b']);
            expect([...target.codes].sort()).toEqual(['a', 'b']);
            expect(target.has('a')).toBe(true);
            expect(target.has('c')).toBe(false);
            expect(target.hasAny(['c', 'b'])).toBe(true);
            expect(target.hasAny(['c'])).toBe(false);
            expect(target.hasAll(['a', 'b'])).toBe(true);
            expect(target.hasAll(['a', 'c'])).toBe(false);
            target.setCodes([]);
            expect(target.hasAny(['a'])).toBe(false);
            expect(target.hasAll([])).toBe(true);
        });
    });
}
/**
 * 反馈契约（`BaseFeedback` / `useFeedback` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeFeedbackContract(name, create) {
    describeContract(name, () => {
        it('状态机（loading → ready / empty / error）', () => {
            const target = create();
            expect(target.state).toBe('loading');
            target.setState('ready');
            expect(target.state).toBe('ready');
            target.setState('empty');
            expect(target.state).toBe('empty');
            target.setState('error');
            expect(target.state).toBe('error');
        });
        it('仅错误态且注入回调时重试', () => {
            const target = create();
            let called = 0;
            expect(target.doRetry()).toBe(false);
            target.retry = () => {
                called += 1;
            };
            target.setState('ready');
            expect(target.doRetry()).toBe(false);
            target.setState('error');
            expect(target.doRetry()).toBe(true);
            expect(called).toBe(1);
        });
    });
}
/**
 * 容器契约（`BaseContainer` / `useBaseContainer` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeContainerContract(name, create) {
    describeContract(name, () => {
        it('不可折叠时切换为空操作，可折叠时来回切换', () => {
            const target = create();
            expect(target.collapsible).toBe(false);
            target.toggleCollapse();
            expect(target.collapsed).toBe(false);
            target.collapsible = true;
            target.toggleCollapse();
            expect(target.collapsed).toBe(true);
            target.toggleCollapse();
            expect(target.collapsed).toBe(false);
        });
    });
}
/**
 * 确认契约（`useConfirm`）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeConfirmContract(name, create) {
    describeContract(name, () => {
        it('打开挂起，结算为确认', async () => {
            const target = create();
            expect(target.open).toBe(false);
            const pending = target.confirm({ title: '删除确认' });
            expect(target.open).toBe(true);
            target.resolve(true);
            await expect(pending).resolves.toBe(true);
            expect(target.open).toBe(false);
        });
        it('结算为取消', async () => {
            const target = create();
            const pending = target.confirm();
            target.resolve(false);
            await expect(pending).resolves.toBe(false);
            expect(target.open).toBe(false);
        });
    });
}
/**
 * 占位字段契约（`06_01` 冻结；真实实现 `06_04` ~ `06_07` 继续跑同一套件）。
 *
 * 断言：占位态降级且禁用、不产生后端请求；就绪态不再降级。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePlaceholderFieldContract(name, create) {
    describeContract(name, () => {
        it('未就绪时降级且禁用，不产生请求', () => {
            const target = create();
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            expect(target.disabled).toBe(true);
            expect(target.requestCount).toBe(0);
            target.load();
            expect(target.requestCount).toBe(0);
        });
        it('就绪后不再降级', () => {
            const target = create();
            target.setReady(true);
            expect(target.ready).toBe(true);
            expect(target.degraded).toBe(false);
            expect(target.disabled).toBe(false);
        });
    });
}
/**
 * 占位展示契约（`07_01` 冻结；真实实现 `07_03` ~ `07_07` 继续跑同一套件）。
 *
 * 断言：占位态降级、不产生后端请求；就绪态不再降级。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePlaceholderDisplayContract(name, create) {
    describeContract(name, () => {
        it('未就绪时降级，不产生请求', () => {
            const target = create();
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            expect(target.requestCount).toBe(0);
            target.load();
            expect(target.requestCount).toBe(0);
        });
        it('就绪后不再降级', () => {
            const target = create();
            target.setReady(true);
            expect(target.ready).toBe(true);
            expect(target.degraded).toBe(false);
        });
    });
}
/**
 * 占位交互契约（`08_01_01` 冻结；真实实现 `08_04` / `08_08` 继续跑同一套件）。
 *
 * 断言：占位态降级且禁用、不产生后端请求；就绪态不再降级、不再禁用。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePlaceholderInteractionContract(name, create) {
    describeContract(name, () => {
        it('未就绪时降级且禁用，不产生请求', () => {
            const target = create();
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            expect(target.disabled).toBe(true);
            expect(target.requestCount).toBe(0);
            target.load();
            expect(target.requestCount).toBe(0);
        });
        it('就绪后不再降级、不再禁用', () => {
            const target = create();
            target.setReady(true);
            expect(target.ready).toBe(true);
            expect(target.degraded).toBe(false);
            expect(target.disabled).toBe(false);
        });
    });
}
/**
 * 向导契约（`BaseWizard` / `useBaseWizard` 投影；`08_03_01` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：`setSteps` 传入三步 `base` / `plan`（分支，`visible: false`）/ `admin`，
 * `base` 校验器为 `() => false`（可通过 `setVisible` 驱动分支）之外的行为以本套件断言为准。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeWizardContract(name, create) {
    describeContract(name, () => {
        it('初始定位首个可见步（分支步不可见时跳过）', () => {
            const target = create();
            target.setSteps([
                { key: 'base', validate: () => true },
                { key: 'plan', visible: false, validate: () => true },
                { key: 'admin', validate: () => true },
            ]);
            expect(target.visibleKeys).toEqual(['base', 'admin']);
            expect(target.currentKey).toBe('base');
            expect(target.visited).toEqual(['base']);
        });
        it('分步校验：失败停本步并写错误文案，通过后前进并记已到达', async () => {
            const target = create();
            target.setSteps([
                { key: 'base', validate: () => '请填写名称' },
                { key: 'admin', validate: () => true },
            ]);
            await expect(target.next()).resolves.toBe(false);
            expect(target.currentKey).toBe('base');
            expect(target.stepError).toBe('请填写名称');
            target.setSteps([
                { key: 'base', validate: () => true },
                { key: 'admin', validate: () => true },
            ]);
            await expect(target.next()).resolves.toBe(true);
            expect(target.currentKey).toBe('admin');
            expect(target.stepError).toBe('');
            expect(target.visited).toEqual(['base', 'admin']);
            expect(target.prev()).toBe(true);
            expect(target.currentKey).toBe('base');
        });
        it('仅可跳「已到达」步骤', async () => {
            const target = create();
            target.setSteps([
                { key: 'base', validate: () => true },
                { key: 'plan', validate: () => true },
                { key: 'admin', validate: () => true },
            ]);
            expect(target.goTo('admin')).toBe(false);
            expect(target.currentKey).toBe('base');
            await target.next();
            expect(target.currentKey).toBe('plan');
            expect(target.goTo('base')).toBe(true);
            expect(target.currentKey).toBe('base');
        });
        it('分支隐藏当前步后回退到最近有效可见步', async () => {
            const target = create();
            target.setSteps([
                { key: 'base', validate: () => true },
                { key: 'plan', validate: () => true },
                { key: 'admin', validate: () => true },
            ]);
            await target.next();
            expect(target.currentKey).toBe('plan');
            target.setVisible('plan', false);
            expect(target.visibleKeys).toEqual(['base', 'admin']);
            expect(target.currentKey).toBe('base');
            expect(target.visited).not.toContain('plan');
        });
        it('整体校验停于首个出错步并定位', async () => {
            const target = create();
            target.setSteps([
                { key: 'base', validate: () => true },
                { key: 'admin', validate: () => '请填写账号' },
                { key: 'confirm', validate: () => false },
            ]);
            const result = await target.validateAll();
            expect(result.valid).toBe(false);
            expect(result.stepKey).toBe('admin');
            expect(target.currentKey).toBe('admin');
            expect(target.stepError).toBe('请填写账号');
        });
        it('结果态后导航不动作，重置归零', async () => {
            const target = create();
            target.setSteps([
                { key: 'base', validate: () => true },
                { key: 'admin', validate: () => true },
            ]);
            await target.next();
            target.complete({ status: 'success', title: '提交成功' });
            expect(target.isResult).toBe(true);
            await expect(target.next()).resolves.toBe(false);
            expect(target.prev()).toBe(false);
            expect(target.goTo('base')).toBe(false);
            target.reset();
            expect(target.isResult).toBe(false);
            expect(target.currentKey).toBe('base');
            expect(target.visited).toEqual(['base']);
        });
    });
}
/**
 * 偏好契约（`usePreferences` 投影 / 偏好状态编排）。
 *
 * 目标约定：默认值 `themeMode = 'light'`，租户策略将 `accent` 置为不可选（`enabled: false`）；
 * `create()` 返回「面板已打开（快照已记录）」的状态。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePreferencesContract(name, create) {
    describeContract(name, () => {
        it('写入后置脏标记，取消回滚到打开前快照', () => {
            const target = create();
            expect(target.dirty).toBe(false);
            expect(target.read().themeMode).toBe('light');
            target.setValue('themeMode', 'dark');
            expect(target.read().themeMode).toBe('dark');
            expect(target.dirty).toBe(true);
            target.cancel();
            expect(target.read().themeMode).toBe('light');
            expect(target.dirty).toBe(false);
        });
        it('保存写本地；无远端注入时置待同步标记且不发请求', async () => {
            const target = create();
            target.setValue('listDensity', 'compact');
            await expect(target.save()).resolves.toBe(false);
            expect(target.pendingSync).toBe(true);
            expect(target.read().listDensity).toBe('compact');
        });
        it('不可选项写入不生效，恢复默认跳过不可选项', async () => {
            const target = create();
            target.setValue('accent', true);
            expect(target.read().accent).toBe(false);
            expect(target.dirty).toBe(false);
            target.setValue('themeMode', 'dark');
            await target.reset();
            expect(target.read().themeMode).toBe(target.defaults().themeMode);
            expect(target.read().accent).toBe(false);
        });
    });
}
/**
 * 批量操作契约（`BaseBulkAction` / `useBaseBulkAction` 投影；`08_03_02` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：选择模式为 `cross-page`；权限上下文含 `user.enable`、不含 `user.delete`；
 * `clearAfterDone` 为真（动作完成后清空选择）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeBulkActionContract(name, create) {
    describeContract(name, () => {
        it('选中集合去重保序；page 模式翻页剔除不在当前页的键', () => {
            const target = create();
            target.setPageKeys(['1', '2']);
            target.select('2');
            target.select('1');
            target.select('1');
            expect(target.selectedKeys()).toEqual(['2', '1']);
            expect(target.count).toBe(2);
            expect(target.mode).toBe('cross-page');
        });
        it('跨页全选取总记录数，切换页后清条件全选标记', () => {
            const target = create();
            target.setTotal(120);
            target.setPageKeys(['1', '2']);
            target.select('1');
            target.selectAllAcrossPages();
            expect(target.allAcrossPages).toBe(true);
            expect(target.count).toBe(120);
            target.setPageKeys(['3', '4']);
            expect(target.allAcrossPages).toBe(false);
            expect(target.count).toBe(0);
        });
        it('权限过滤：无权动作不可见', () => {
            const target = create();
            target.setActions([
                { key: 'enable', perm: 'user.enable', run: () => ({ success: 1, failed: 0 }) },
                { key: 'delete', perm: 'user.delete', danger: true, run: () => ({ success: 1, failed: 0 }) },
            ]);
            expect(target.visibleActionKeys()).toEqual(['enable']);
        });
        it('危险动作进入确认阶段，确认后执行并按需清空', async () => {
            const target = create();
            target.setActions([{ key: 'delete', danger: true, run: () => ({ success: 1, failed: 0 }) }]);
            target.setPageKeys(['1']);
            target.select('1');
            expect(target.needsConfirm('delete')).toBe(true);
            await expect(target.request('delete')).resolves.toBeUndefined();
            expect(target.phase).toBe('confirming');
            await expect(target.confirm()).resolves.toEqual({ success: 1, failed: 0 });
            expect(target.phase).toBe('done');
            expect(target.count).toBe(0);
        });
        it('执行中重复请求不动作（防重复提交）', async () => {
            const target = create();
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            target.setActions([
                {
                    key: 'export',
                    run: async () => {
                        await gate;
                        return { success: 1, failed: 0 };
                    },
                },
            ]);
            target.setPageKeys(['1']);
            target.select('1');
            const pending = target.request('export');
            expect(target.phase).toBe('running');
            await expect(target.request('export')).resolves.toBeUndefined();
            release();
            await expect(pending).resolves.toEqual({ success: 1, failed: 0 });
        });
        it('部分成功汇总成功与失败数', async () => {
            const target = create();
            target.setActions([{ key: 'disable', run: () => ({ success: 2, failed: 1 }) }]);
            target.setPageKeys(['1', '2', '3']);
            target.selectPage();
            await expect(target.request('disable')).resolves.toEqual({ success: 2, failed: 1 });
        });
    });
}
/**
 * 主题契约（`BaseTheme` / `useBaseTheme` 投影；`08_03_02` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：初始模式 `light`、系统偏好为亮色、无品牌配置。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeThemeContract(name, create) {
    describeContract(name, () => {
        it('解析优先级：用户模式 > 品牌默认 > 平台默认', () => {
            const target = create();
            expect(target.resolved).toBe('light');
            target.setBrand({ defaultMode: 'dark' });
            expect(target.resolved).toBe('dark');
            target.setMode('light');
            expect(target.resolved).toBe('light');
            target.setMode('system');
            expect(target.resolved).toBe('light');
        });
        it('system 随系统偏好；disableDark 强制亮色', () => {
            const target = create();
            target.setMode('system');
            target.setSystemPrefersDark(true);
            expect(target.resolved).toBe('dark');
            target.setBrand({ defaultMode: 'dark', disableDark: true });
            expect(target.resolved).toBe('light');
            target.setSystemPrefersDark(false);
            expect(target.resolved).toBe('light');
        });
        it('强调色仅在品牌允许时生效；主色派生六项令牌', () => {
            const target = create();
            target.setBrand({ primaryColor: '#1677ff' });
            target.setAccent('#ff0000');
            expect(target.primary).toBe('#1677ff');
            expect(Object.keys(target.brandTokens()).length).toBe(6);
            target.setBrand({ primaryColor: '#1677ff', allowUserAccent: true });
            expect(target.primary).toBe('#ff0000');
            expect(target.brandTokens()['--bms-color-primary']).toBe('#ff0000');
            expect(target.brandTokens()['--bms-color-primary-hover']).not.toBe('#ff0000');
        });
        it('亮暗互切', () => {
            const target = create();
            target.toggle();
            expect(target.mode).toBe('dark');
            expect(target.resolved).toBe('dark');
            target.toggle();
            expect(target.mode).toBe('light');
            expect(target.resolved).toBe('light');
        });
    });
}
/**
 * 打印契约（`BasePrint` / `useBasePrint` 投影；`08_03_03` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：模板两个——`order`（三列明细 + 每页 2 行，字段 `customer` / `remark`）与 `label`（单列）；
 * 数据五行明细、`fields.customer` 有值而 `fields.remark` 缺失；
 * 水印信息注入为用户「张三」与租户「租户一」；初始未注入导出处理（占位）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePrintContract(name, create) {
    describeContract(name, () => {
        it('模板选择与纸张方向（横向交换宽高）', () => {
            const target = create();
            expect(target.templateKey).toBe('order');
            target.selectTemplate('label');
            expect(target.templateKey).toBe('label');
            target.setPaper('A5', 'landscape');
            expect(target.paperSize).toEqual({ width: 210, height: 148 });
            target.selectTemplate('absent');
            expect(target.templateKey).toBe('label');
        });
        it('预分页：每页行容量、页码连续、末页余量', () => {
            const target = create();
            expect(target.rowsPerPage).toBe(2);
            expect(target.pageRows()).toEqual([2, 2, 1]);
            expect(target.pageIndexes()).toEqual([1, 2, 3]);
            expect(target.pageCount).toBe(3);
        });
        it('字段渲染与缺失占位', () => {
            const target = create();
            expect(target.fieldText('customer')).toBe('华东制造有限公司');
            expect(target.fieldText('remark')).toBe('—');
        });
        it('水印（单据级标签 + 用户信息）与黑白', () => {
            const target = create();
            expect(target.mono).toBe(false);
            target.setWatermarkLabel('作废');
            expect(target.watermarkText).toContain('作废');
            expect(target.watermarkText).toContain('张三');
            target.setTone('mono');
            expect(target.mono).toBe(true);
        });
        it('预览显隐与缩放夹取', () => {
            const target = create();
            expect(target.previewVisible).toBe(false);
            target.open();
            expect(target.previewVisible).toBe(true);
            expect(target.setZoom(2)).toBe(1.2);
            expect(target.setZoom(0.1)).toBe(0.6);
            target.close();
            expect(target.previewVisible).toBe(false);
        });
        it('批量模式切换', () => {
            const target = create();
            expect(target.batchMode).toBe('separate');
            target.setBatchMode('merged');
            expect(target.batchMode).toBe('merged');
        });
        it('导出占位：未注入处理不动作', async () => {
            const target = create();
            await expect(target.exportPdf()).resolves.toBeUndefined();
            expect(target.phase).toBe('idle');
        });
        it('注入后导出阶段推进并保留结果', async () => {
            const target = create();
            const progress = [];
            target.setExportHandler(async (report) => {
                report(1, 3);
                progress.push(1);
                return { fileId: 'f1' };
            });
            await expect(target.exportPdf()).resolves.toEqual({ fileId: 'f1' });
            expect(target.phase).toBe('done');
            expect(progress).toEqual([1]);
        });
        it('导出失败置 failed，retry 恢复', async () => {
            const target = create();
            let fail = true;
            target.setExportHandler(async () => {
                if (fail) {
                    throw new Error('导出失败');
                }
                return { fileId: 'f2' };
            });
            await expect(target.exportPdf()).resolves.toBeUndefined();
            expect(target.phase).toBe('failed');
            fail = false;
            await expect(target.retry()).resolves.toEqual({ fileId: 'f2' });
            expect(target.phase).toBe('done');
        });
        it('导出中重复请求不动作（防重复提交）', async () => {
            const target = create();
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            target.setExportHandler(async () => {
                await gate;
                return { fileId: 'f3' };
            });
            const pending = target.exportPdf();
            expect(target.phase).toBe('exporting');
            await expect(target.exportPdf()).resolves.toBeUndefined();
            release();
            await expect(pending).resolves.toEqual({ fileId: 'f3' });
        });
        it('导出许可关闭时不可导出', async () => {
            const target = create();
            target.setExportHandler(async () => ({ fileId: 'f4' }));
            target.setAllowExport(false);
            expect(target.canExport).toBe(false);
            await expect(target.exportPdf()).resolves.toBeUndefined();
        });
    });
}
/**
 * 租户切换契约（`BaseTenant` / `useBaseTenant` 投影；`08_03_02` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：初始租户列表含 `t1`（当前，名称「租户一」，编码 `A1`，角色「管理员」）
 * 与 `t2`（名称「租户二」，编码 `B2`，角色「操作员」）；`confirmRequired` 为真。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeTenantContract(name, create) {
    describeContract(name, () => {
        it('单租户不显示入口；搜索按名称 / 编码 / 角色匹配', () => {
            const target = create();
            expect(target.multiTenant).toBe(true);
            expect(target.search('租户二')).toEqual(['t2']);
            expect(target.search('B2')).toEqual(['t2']);
            expect(target.search('操作员')).toEqual(['t2']);
            target.setTenants([{ id: 't1', name: '租户一' }]);
            expect(target.multiTenant).toBe(false);
        });
        it('确认后切换阶段依序推进并提交当前租户', async () => {
            const target = create();
            const phases = [];
            target.setSteps({
                switchSession: async () => {
                    phases.push('switching');
                },
                reloadContext: async () => {
                    phases.push('reloading');
                },
                clearCache: async () => {
                    phases.push('clearing');
                },
                navigateHome: async () => {
                    phases.push('navigating');
                },
            });
            await expect(target.request('t2')).resolves.toBe(false);
            expect(target.currentId).toBe('t1');
            await expect(target.confirm('t2')).resolves.toBe(true);
            expect(phases).toEqual(['switching', 'reloading', 'clearing', 'navigating']);
            expect(target.currentId).toBe('t2');
            expect(target.phase).toBe('done');
        });
        it('中段失败置 failed 且保留原租户；retry 从失败目标重试', async () => {
            const target = create();
            let fail = true;
            target.setSteps({
                switchSession: async () => {
                    if (fail) {
                        throw new Error('会话失效');
                    }
                },
            });
            await expect(target.switchTo('t2')).resolves.toBe(false);
            expect(target.phase).toBe('failed');
            expect(target.currentId).toBe('t1');
            fail = false;
            await expect(target.retry()).resolves.toBe(true);
            expect(target.currentId).toBe('t2');
            expect(target.phase).toBe('done');
        });
        it('切换中重复请求不动作；reset 归 idle', async () => {
            const target = create();
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            target.setSteps({
                switchSession: async () => {
                    await gate;
                },
            });
            const pending = target.switchTo('t2');
            await expect(target.switchTo('t2')).resolves.toBe(false);
            release();
            await expect(pending).resolves.toBe(true);
            target.reset();
            expect(target.phase).toBe('idle');
            expect(target.currentId).toBe('t2');
        });
    });
}
/** 契约目标约定元数据（菜单含挂接缺失项；表单含无入口项）。 */
const PERMISSION_CONTRACT_METADATA = {
    menus: [
        { id: 'menu:user', name: '用户管理', children: [{ id: 'menu:user:list', name: '用户列表' }] },
        { id: 'menu:orphan', name: '未挂接菜单' },
    ],
    forms: [
        { id: 'form:user', name: '用户表单', menuIds: ['menu:user', 'menu:user:list'] },
        { id: 'form:free', name: '无入口表单', menuIds: [] },
    ],
    actions: [{ id: 'act:user:create', name: '新增用户' }],
    fields: [
        { id: 'field:name', name: '姓名' },
        { id: 'field:salary', name: '薪资' },
    ],
    formActions: { 'form:user': ['act:user:create'] },
    formFields: { 'form:user': ['field:name', 'field:salary'] },
    dictTypes: [{ id: 'dict:user', code: 'user', name: '用户字典' }],
    extensions: [],
};
/**
 * 授权编排契约（`BasePermissionConfig` / `useBasePermissionConfig` 投影；新口径）。
 *
 * 目标约定：角色 `r1`；菜单 `menu:user`（子菜单 `menu:user:list`，关联表单 `form:user`）与挂接缺失菜单 `menu:orphan`；
 * 表单 `form:user` 含动作 `act:user:create`（默认无）与字段 `field:name` / `field:salary`（默认全开）；
 * 字典 `dict:user`；用户初始为空；初始未注入处理函数。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePermissionConfigContract(name, create) {
    /** 构造「已就绪且已装载」的目标。 */
    const readyTarget = async (grants = { roleId: 'r1' }) => {
        const target = create();
        target.setHandlers({
            loadMetadata: async () => PERMISSION_CONTRACT_METADATA,
            loadGrants: async () => grants,
        });
        target.setReady(true);
        await target.load();
        return target;
    };
    describeContract(name, () => {
        it('未就绪时降级且禁用，不产生请求', async () => {
            const target = create();
            target.setHandlers({
                loadMetadata: async () => PERMISSION_CONTRACT_METADATA,
                loadGrants: async () => ({ roleId: 'r1' }),
            });
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            expect(target.disabled).toBe(true);
            await target.load();
            expect(target.requestCount).toBe(0);
        });
        it('就绪但未注入处理函数时仍不产生请求、不再降级', async () => {
            const target = create();
            target.setReady(true);
            expect(target.degraded).toBe(false);
            expect(target.disabled).toBe(false);
            await target.load();
            expect(target.requestCount).toBe(0);
        });
        it('就绪且注入取数后装载（初始不脏、菜单未勾选）', async () => {
            const target = await readyTarget();
            expect(target.requestCount).toBe(2);
            expect(target.dirty).toBe(false);
            expect(target.menuCheckState('menu:user')).toBe('unchecked');
            expect(target.formSourceMenuIds('form:user')).toEqual([]);
        });
        it('菜单勾选：级联子树并连带关联表单（按来源）', async () => {
            const target = await readyTarget();
            expect(target.toggleMenu('menu:user')).toBe(true);
            expect(target.menuCheckState('menu:user')).toBe('checked');
            expect(target.menuCheckState('menu:user:list')).toBe('checked');
            expect(target.formSourceMenuIds('form:user')).toEqual(['menu:user', 'menu:user:list']);
        });
        it('取消菜单仅撤销本来源（其它来源保留）', async () => {
            const target = await readyTarget({
                roleId: 'r1',
                entries: [{ permType: 'form', targetId: 'form:user', sourceMenuId: '0' }],
            });
            target.toggleMenu('menu:user');
            expect(target.formSourceMenuIds('form:user')).toEqual(['0', 'menu:user', 'menu:user:list']);
            target.toggleMenu('menu:user', false);
            expect(target.formSourceMenuIds('form:user')).toEqual(['0']);
            expect(target.menuCheckState('menu:user')).toBe('unchecked');
        });
        it('挂接缺失菜单不可授予', async () => {
            const target = await readyTarget();
            expect(target.toggleMenu('menu:orphan')).toBe(false);
            expect(target.menuCheckState('menu:orphan')).toBe('unchecked');
        });
        it('三态：勾选子级父级半选，全勾则已选', async () => {
            const target = await readyTarget();
            target.toggleMenu('menu:user:list');
            expect(target.menuCheckState('menu:user')).toBe('indeterminate');
            target.toggleMenu('menu:user');
            expect(target.menuCheckState('menu:user')).toBe('checked');
        });
        it('操作权限默认无、按来源写入与撤销', async () => {
            const target = await readyTarget();
            expect(target.actionSourceMenuIds('act:user:create')).toEqual([]);
            expect(target.toggleAction('act:user:create', '0')).toBe(true);
            expect(target.toggleAction('act:user:create', 'menu:user')).toBe(true);
            expect(target.actionSourceMenuIds('act:user:create')).toEqual(['0', 'menu:user']);
            expect(target.toggleAction('act:user:create', '0', false)).toBe(true);
            expect(target.actionSourceMenuIds('act:user:create')).toEqual(['menu:user']);
        });
        it('字段权限：默认全开、只提交收窄项、editable=false 强制不可见', async () => {
            const target = await readyTarget();
            expect(target.fieldPerm('form:user', 'field:name')).toBeUndefined();
            expect(target.payloadFields()).toEqual([]);
            expect(target.setFieldPerm('form:user', 'field:name', { visible: false })).toBe(true);
            expect(target.payloadFields()).toEqual([
                { formId: 'form:user', fieldId: 'field:name', visible: false, editable: true, sourceMenuId: '0' },
            ]);
            expect(target.setFieldPerm('form:user', 'field:salary', { editable: false }, 'menu:user')).toBe(true);
            expect(target.payloadFields().find((item) => item.fieldId === 'field:salary')).toEqual({
                formId: 'form:user',
                fieldId: 'field:salary',
                visible: false,
                editable: false,
                sourceMenuId: 'menu:user',
            });
            expect(target.setFieldPerm('form:user', 'field:absent', { visible: false })).toBe(false);
        });
        it('数据权限：按字典 × 策略覆盖、空配置即无', async () => {
            const target = await readyTarget();
            expect(target.payloadDataScopes()).toEqual([]);
            expect(target.setDataScope('dict:user', 'select', [{ itemCode: 'enabled' }])).toBe(true);
            expect(target.payloadDataScopes()).toEqual([
                { dictTypeId: 'dict:user', policyType: 'select', config: [{ itemCode: 'enabled' }] },
            ]);
            target.setDataScope('dict:user', 'select', []);
            expect(target.payloadDataScopes()).toEqual([]);
        });
        it('用户分配：去重、不设上限', async () => {
            const target = await readyTarget();
            expect(target.bindUsers([{ id: 'u1', username: 'zhang', name: '张三', status: 'enabled' }])).toBe(true);
            expect(target.bindUsers([{ id: 'u1', username: 'zhang', name: '张三', status: 'enabled' }])).toBe(false);
            expect(target.userIds()).toEqual(['u1']);
            const many = Array.from({ length: 30 }, (_, index) => ({
                id: `u${index + 2}`,
                username: `x${index + 2}`,
                name: `用户${index + 2}`,
                status: 'enabled',
            }));
            target.bindUsers(many);
            expect(target.userIds()).toHaveLength(31);
        });
        it('脏基线与撤销：变更置脏，撤销回滚且不再脏', async () => {
            const target = await readyTarget();
            expect(target.dirty).toBe(false);
            target.toggleMenu('menu:user');
            expect(target.dirty).toBe(true);
            target.discard();
            expect(target.dirty).toBe(false);
            expect(target.menuCheckState('menu:user')).toBe('unchecked');
        });
        it('三类载荷幂等键：同内容同键、重复提交结果一致、变更换键', async () => {
            const target = await readyTarget();
            const keys = [];
            target.setHandlers({
                submitPermissions: async (input) => {
                    keys.push(input.idempotencyKey);
                    return { version: keys.length };
                },
                submitFields: async () => ({ version: 0 }),
                submitDataScopes: async () => ({ version: 0 }),
            });
            target.toggleMenu('menu:user');
            await target.save();
            await target.save();
            expect(keys).toHaveLength(2);
            expect(keys[0]).toBe(keys[1]);
            target.toggleAction('act:user:create', '0');
            expect(target.idempotencyKey('perm')).not.toBe(keys[1]);
        });
        it('提交阶段推进与权限上下文刷新（注入取码）', async () => {
            const target = await readyTarget();
            target.setAccess(['role:grant']);
            target.setHandlers({
                submitPermissions: async () => ({ version: 7 }),
                submitFields: async () => ({}),
                submitDataScopes: async () => ({}),
                loadPermissionCodes: async () => ['role:grant', 'user:create'],
            });
            target.toggleMenu('menu:user');
            expect(target.canSave).toBe(true);
            await target.save();
            expect(target.phase).toBe('done');
            expect(target.pendingAccessRefresh).toBe(false);
            expect([...target.accessCodes]).toContain('user:create');
        });
        it('未注入取码处理时不发请求，仅置待刷新标记', async () => {
            const target = await readyTarget();
            target.setAccess(['role:grant']);
            target.setHandlers({
                submitPermissions: async () => ({ version: 1 }),
                submitFields: async () => ({}),
                submitDataScopes: async () => ({}),
            });
            const before = target.requestCount;
            target.toggleMenu('menu:user');
            await target.save();
            expect(target.phase).toBe('done');
            expect(target.pendingAccessRefresh).toBe(true);
            expect(target.requestCount).toBe(before + 3);
        });
        it('未注入提交处理时不请求，且保留本地变更', async () => {
            const target = await readyTarget();
            const before = target.requestCount;
            target.toggleMenu('menu:user');
            await expect(target.save()).resolves.toBeUndefined();
            expect(target.requestCount).toBe(before);
            expect(target.dirty).toBe(true);
        });
        it('提交失败保留本地并按错误码定位页签，重试恢复', async () => {
            const target = await readyTarget();
            let fail = true;
            target.setHandlers({
                submitPermissions: async () => ({ version: 1 }),
                submitFields: async () => {
                    if (fail) {
                        throw Object.assign(new Error('字段不匹配'), { code: 30049 });
                    }
                    return {};
                },
                submitDataScopes: async () => ({}),
            });
            target.toggleMenu('menu:user');
            await expect(target.save()).resolves.toBeUndefined();
            expect(target.phase).toBe('failed');
            expect(target.errorTargetTab()).toBe('form');
            expect(target.dirty).toBe(true);
            fail = false;
            await target.retry();
            expect(target.phase).toBe('done');
            expect(target.dirty).toBe(false);
        });
        it('进行中重复提交不动作（防重复提交）', async () => {
            const target = await readyTarget();
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            let calls = 0;
            target.setHandlers({
                submitPermissions: async () => {
                    calls += 1;
                    await gate;
                    return { version: 3 };
                },
                submitFields: async () => ({}),
                submitDataScopes: async () => ({}),
            });
            target.toggleMenu('menu:user');
            const pending = target.save();
            expect(target.phase).toBe('saving');
            await expect(target.save()).resolves.toBeUndefined();
            release();
            await pending;
            expect(calls).toBe(1);
        });
        it('无权（缺写权限码）不可保存且不可编辑', async () => {
            const target = await readyTarget();
            target.setAccess([]);
            expect(target.canSave).toBe(false);
            expect(target.toggleMenu('menu:user')).toBe(false);
            expect(target.setFieldPerm('form:user', 'field:name', { visible: false })).toBe(false);
            target.setAccess(['role:grant']);
            expect(target.toggleMenu('menu:user')).toBe(true);
        });
    });
}
/**
 * 导入流契约（`BaseImportFlow` / `useBaseImportFlow` 投影；`08-5-1` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：业务 `users` / 中文名「用户」；文件 `users.xlsx`（1KB）；执行处理函数返回部分失败结果；
 * 「未注入执行处理」与「未就绪」两条占位路径均要求零请求。实现侧不得改动对外形状。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeImportFlowContract(name, create) {
    /** 契约文件元信息。 */
    const meta = { name: 'users.xlsx', size: 1024, lastModified: 1_700_000_000_000 };
    /** 契约文件对象（透传用）。 */
    const file = { kind: 'file', name: 'users.xlsx' };
    /** 部分失败结果。 */
    const partial = {
        total: 100,
        successCount: 98,
        failCount: 2,
        errors: [
            { row: 3, column: 'email', message: '邮箱格式非法' },
            { row: 7, message: '唯一性冲突' },
        ],
    };
    /** 构造已就绪且已选文件的目标。 */
    const readyTarget = (jobs) => {
        const target = create();
        target.setBiz('users', '用户');
        target.setJobs(jobs);
        target.setReady(true);
        target.selectFile(file, meta);
        return target;
    };
    describeContract(name, () => {
        it('未就绪时降级且不产生请求', async () => {
            const target = create();
            target.setBiz('users', '用户');
            target.setJobs({ execute: async () => partial });
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            target.selectFile(file, meta);
            await expect(target.submit()).resolves.toBeUndefined();
            expect(target.requestCount).toBe(0);
        });
        it('就绪但未注入执行处理时不产生请求（占位）', async () => {
            const target = readyTarget({});
            await expect(target.submit()).resolves.toBeUndefined();
            expect(target.requestCount).toBe(0);
        });
        it('文件校验：类型 / 大小 / 空文件不通过且不生成幂等键', () => {
            const target = create();
            target.setBiz('users', '用户');
            target.setReady(true);
            expect(target.selectFile(file, { name: 'users.txt', size: 10 })).toBe(false);
            expect(target.fileError).toContain('.xlsx');
            expect(target.selectFile(file, { name: 'users.xlsx', size: 30 * 1024 * 1024 })).toBe(false);
            expect(target.fileError).toContain('MB');
            expect(target.selectFile(file, { name: 'users.xlsx', size: 0 })).toBe(false);
            expect(target.fileError).toContain('空');
            expect(target.idempotencyKey).toBe('');
        });
        it('幂等键为内容派生：同文件同键、换文件换键、清空重置', () => {
            const target = create();
            target.setBiz('users', '用户');
            target.setReady(true);
            expect(target.selectFile(file, meta)).toBe(true);
            const first = target.idempotencyKey;
            expect(first).not.toBe('');
            expect(target.selectFile(file, meta)).toBe(true);
            expect(target.idempotencyKey).toBe(first);
            target.selectFile(file, { ...meta, size: meta.size + 1 });
            expect(target.idempotencyKey).not.toBe(first);
            target.clearFile();
            expect(target.idempotencyKey).toBe('');
        });
        it('提交：阶段推进、进度透出、结果归一与汇总态', async () => {
            const target = readyTarget({
                execute: async ({ idempotencyKey, report }) => {
                    expect(idempotencyKey).toBe(target.idempotencyKey);
                    report(30);
                    report(100);
                    return partial;
                },
            });
            await expect(target.submit()).resolves.toEqual(partial);
            expect(target.requestCount).toBe(1);
            expect(target.phase).toBe('done');
            expect(target.step).toBe('result');
            expect(target.progress).toBe(100);
            expect(target.summary).toBe('warning');
            expect(target.result()).toEqual(partial);
            expect(target.errorRows).toHaveLength(2);
            expect(target.errorPageCount).toBe(1);
        });
        it('汇总态：全部成功与无数据', async () => {
            const ok = readyTarget({ execute: async () => ({ total: 3, successCount: 3, failCount: 0 }) });
            await ok.submit();
            expect(ok.summary).toBe('success');
            const empty = readyTarget({ execute: async () => undefined });
            await empty.submit();
            expect(empty.summary).toBe('empty');
            expect(empty.result()).toEqual({ total: 0, successCount: 0, failCount: 0, errors: [] });
        });
        it('错误行分页与展示上限截断标记', async () => {
            const target = readyTarget({
                execute: async () => ({
                    total: 1500,
                    successCount: 400,
                    failCount: 1100,
                    errors: Array.from({ length: 1100 }, (_, index) => ({ row: index + 2, message: '格式非法' })),
                }),
            });
            await target.submit();
            expect(target.errorTruncated).toBe(true);
            expect(target.errorPageCount).toBe(50);
            expect(target.errorRows).toHaveLength(20);
            target.setErrorPage(2);
            expect(target.errorRows[0]?.row).toBe(22);
        });
        it('执行失败：阶段置失败、不展示错误行、重试复用同一幂等键', async () => {
            const keys = [];
            let attempt = 0;
            const target = readyTarget({
                execute: async ({ idempotencyKey }) => {
                    keys.push(idempotencyKey);
                    attempt += 1;
                    if (attempt === 1) {
                        throw new Error('文件解析失败');
                    }
                    return { total: 1, successCount: 1, failCount: 0 };
                },
            });
            await expect(target.submit()).resolves.toBeUndefined();
            expect(target.phase).toBe('failed');
            expect(target.errorRows).toHaveLength(0);
            await expect(target.retry()).resolves.toEqual({ total: 1, successCount: 1, failCount: 0, errors: [] });
            expect(keys).toHaveLength(2);
            expect(keys[0]).toBe(keys[1]);
            expect(target.phase).toBe('done');
        });
        it('进行中重复提交不动作', async () => {
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            const target = readyTarget({
                execute: async () => {
                    await gate;
                    return { total: 1, successCount: 1, failCount: 0 };
                },
            });
            const pending = target.submit();
            expect(target.busy).toBe(true);
            await expect(target.submit()).resolves.toBeUndefined();
            release();
            await expect(pending).resolves.toEqual({ total: 1, successCount: 1, failCount: 0, errors: [] });
            expect(target.requestCount).toBe(1);
        });
        it('取消：中断在途执行并复位阶段与进度', async () => {
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            const target = readyTarget({
                execute: async () => {
                    await gate;
                    return { total: 1, successCount: 1, failCount: 0 };
                },
            });
            const pending = target.submit();
            target.cancel();
            release();
            await expect(pending).resolves.toBeUndefined();
            expect(target.phase).toBe('idle');
            expect(target.progress).toBe(0);
            expect(target.result()).toBeUndefined();
        });
        it('模板与错误明细下载：注入取址后返回结果，未注入则不动作', async () => {
            const target = readyTarget({});
            await expect(target.downloadTemplate()).resolves.toBeUndefined();
            const calls = [];
            target.setJobs({
                downloadTemplate: async ({ kind, filename }) => {
                    calls.push(`${kind}:${filename}`);
                    return { url: 'https://example.test/template.xlsx' };
                },
                downloadErrors: async ({ kind, filename, idempotencyKey }) => {
                    calls.push(`${kind}:${filename}:${idempotencyKey}`);
                    return { url: 'https://example.test/errors.xlsx' };
                },
            });
            await expect(target.downloadTemplate()).resolves.toEqual({
                url: 'https://example.test/template.xlsx',
                filename: '用户-导入模板.xlsx',
            });
            await expect(target.downloadErrors()).resolves.toBeDefined();
            expect(calls[0]).toBe('template:用户-导入模板.xlsx');
            expect(calls[1]?.startsWith('errors:用户-导入错误明细-')).toBe(true);
            expect(calls[1]?.endsWith(`:${target.idempotencyKey}`)).toBe(true);
        });
    });
}
/**
 * 导出流契约（`BaseExportFlow` / `useBaseExportFlow` 投影；`08-5-1` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：业务 `users` / 中文名「用户」；默认取数参数 `{ keyword: 'a' }`、总条数 10、阈值 0（同步）；
 * 异步目标总条数 1000 / 阈值 500（经 `newTask()` 提供任务实例、`poll` 两轮完成）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeExportFlowContract(name, create) {
    /** 构造已就绪目标。 */
    const readyTarget = (jobs, input = {}) => {
        const target = create();
        target.setBiz('users', '用户');
        target.setTotal(input.total ?? 10);
        target.setThreshold(input.threshold ?? 0);
        target.setParams({ keyword: 'a' });
        target.setJobs(jobs);
        target.setReady(true);
        return target;
    };
    describeContract(name, () => {
        it('未就绪时降级且不产生请求', async () => {
            const target = create();
            target.setBiz('users', '用户');
            target.setTotal(10);
            target.setJobs({ export: async () => ({ url: 'https://example.test/1.xlsx' }) });
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            await expect(target.export()).resolves.toBeUndefined();
            expect(target.requestCount).toBe(0);
        });
        it('就绪但未注入导出处理时不产生请求（占位）', async () => {
            const target = readyTarget({});
            expect(target.exportReady).toBe(false);
            await expect(target.export()).resolves.toBeUndefined();
            expect(target.requestCount).toBe(0);
        });
        it('决策：无数据 / 选中未选 / 无权 / 外部禁用 各自不动作', async () => {
            const jobs = { export: async () => ({ url: 'https://example.test/1.xlsx' }) };
            const empty = readyTarget(jobs, { total: 0 });
            expect(empty.empty).toBe(true);
            expect(empty.canExport).toBe(false);
            await expect(empty.export()).resolves.toBeUndefined();
            const selected = readyTarget(jobs);
            selected.setScope('selected', []);
            expect(selected.canExport).toBe(false);
            await expect(selected.export()).resolves.toBeUndefined();
            const denied = readyTarget(jobs);
            denied.setAccess([]);
            expect(denied.canExport).toBe(false);
            await expect(denied.export()).resolves.toBeUndefined();
            const disabled = readyTarget(jobs);
            disabled.setDisabled(true);
            expect(disabled.canExport).toBe(false);
            await expect(disabled.export()).resolves.toBeUndefined();
            expect(empty.requestCount + selected.requestCount + denied.requestCount + disabled.requestCount).toBe(0);
        });
        it('载荷：取数参数归一、选中去重排序、明文按权限收窄', () => {
            const target = readyTarget({});
            target.setParams({ keyword: 'a', empty: '', list: [], keep: 1 });
            target.setScope('selected', ['2', 1, '2']);
            target.setPlain(true);
            expect(target.plan().params).toEqual({ keyword: 'a', keep: 1 });
            expect(target.plan().selectedIds).toEqual(['1', '2']);
            expect(target.plan().plain).toBe(false);
            expect(target.plan().filename.endsWith('.xlsx')).toBe(true);
            expect(target.asyncMode).toBe(false);
            target.setAccess(['data:plain']);
            expect(target.plan().plain).toBe(true);
        });
        it('同步导出：阶段推进、结果与下载触发', async () => {
            const downloads = [];
            const target = readyTarget({
                export: async ({ report }) => {
                    report({ value: 1, total: 10 });
                    return { url: 'https://example.test/export.xlsx', fileName: 'users.xlsx' };
                },
            });
            target.setDownload({
                download: async (input) => {
                    downloads.push(input.filename ?? '');
                    return { url: input.url ?? '', filename: input.filename ?? '' };
                },
            });
            await expect(target.export()).resolves.toMatchObject({ url: 'https://example.test/export.xlsx' });
            expect(target.phase).toBe('done');
            expect(target.requestCount).toBe(1);
            expect(target.lastResult()?.url).toBe('https://example.test/export.xlsx');
            expect(downloads).toEqual(['users.xlsx']);
        });
        it('超阈值异步：经两段轮询推进进度并结算结果', async () => {
            const attempts = [];
            const target = readyTarget({
                export: async () => ({ fileId: 'task-1' }),
                poll: async (_handle, attempt) => {
                    attempts.push(attempt);
                    return attempt < 2
                        ? { done: false, progress: { value: attempt, total: 2 } }
                        : {
                            done: true,
                            progress: { value: 2, total: 2 },
                            result: { fileId: 'file-1', fileName: 'users.xlsx', url: 'https://example.test/1.xlsx' },
                        };
                },
            }, { total: 1000, threshold: 500 });
            target.setTask(target.newTask());
            expect(target.asyncMode).toBe(true);
            await expect(target.export()).resolves.toMatchObject({ fileId: 'file-1' });
            expect(attempts).toEqual([1, 2]);
            expect(target.phase).toBe('done');
            expect(target.progress).toMatchObject({ value: 2, total: 2 });
        });
        it('异步阈值但轮询未注入：回落单次调用并按已转后台标记', async () => {
            const target = readyTarget({ export: async () => ({ fileId: 'task-1' }) }, { total: 1000, threshold: 500 });
            target.setTask(target.newTask());
            await expect(target.export()).resolves.toMatchObject({ async: true, fileId: 'task-1' });
            expect(target.phase).toBe('done');
        });
        it('失败可重试（同参数重放）', async () => {
            let attempt = 0;
            const target = readyTarget({
                export: async () => {
                    attempt += 1;
                    if (attempt === 1) {
                        throw new Error('导出失败');
                    }
                    return { url: 'https://example.test/1.xlsx' };
                },
            });
            await expect(target.export()).resolves.toBeUndefined();
            expect(target.phase).toBe('failed');
            await expect(target.retry()).resolves.toMatchObject({ url: 'https://example.test/1.xlsx' });
            expect(target.phase).toBe('done');
            expect(target.requestCount).toBe(2);
        });
        it('进行中重复提交不动作', async () => {
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            const target = readyTarget({
                export: async () => {
                    await gate;
                    return { url: 'https://example.test/1.xlsx' };
                },
            });
            const pending = target.export();
            expect(target.busy).toBe(true);
            await expect(target.export()).resolves.toBeUndefined();
            release();
            await pending;
            expect(target.requestCount).toBe(1);
        });
        it('取消：中断在途导出并复位阶段', async () => {
            let release = () => { };
            const gate = new Promise((resolve) => {
                release = resolve;
            });
            const target = readyTarget({
                export: async () => {
                    await gate;
                    return { url: 'https://example.test/1.xlsx' };
                },
            });
            const pending = target.export();
            target.cancel();
            release();
            await expect(pending).resolves.toBeUndefined();
            expect(target.phase).toBe('idle');
            expect(target.requestCount).toBe(1);
        });
    });
}
