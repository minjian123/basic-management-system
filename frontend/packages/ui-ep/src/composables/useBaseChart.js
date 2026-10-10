/** 图表组件基类投影：把核心组件基类 `BaseChart` 投影为组合式（配置 / 选项 / 主题 / 四态 / 取数）。 */
import { BaseChart, normalizeChartConfig, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体图表件（可实例化）。 */
class ChartState extends BaseChart {
}
/**
 * 使用图表组件基类投影。
 *
 * @param options 选项。
 * @returns 图表基类实例与响应式面。
 */
export function useBaseChart(options = {}) {
    const chart = new ChartState();
    if (options.config !== undefined) {
        chart.setConfig(normalizeChartConfig(options.config, options.result?.columns));
    }
    else {
        chart.setChartType(options.chartType ?? 'line');
        if (options.mapping !== undefined) {
            chart.setMapping(options.mapping);
        }
    }
    if (options.result !== undefined) {
        chart.setResult(options.result);
    }
    if (options.option !== undefined) {
        chart.setRawOption(options.option);
    }
    if (options.view !== undefined) {
        chart.setView(options.view);
    }
    if (options.themeMode !== undefined) {
        chart.setThemeMode(options.themeMode);
    }
    if (options.renderMode !== undefined) {
        chart.setRenderMode(options.renderMode);
    }
    if (options.height !== undefined) {
        chart.setHeight(options.height);
    }
    if (options.tokens !== undefined) {
        chart.setTokens(options.tokens);
    }
    chart.setPrefersDark(options.prefersDark ?? false);
    if (options.jobs !== undefined) {
        chart.setJobs(options.jobs);
    }
    if (options.engine !== undefined) {
        chart.setEngine(markRaw(toRaw(options.engine)));
    }
    chart.setReady(options.ready ?? false);
    const ready = ref(chart.ready);
    const degraded = ref(chart.degraded);
    const state = ref(chart.state);
    const view = ref(chart.view);
    const config = ref(chart.config);
    const option = ref(chart.option);
    const theme = ref(chart.theme);
    const requestCount = ref(chart.requestCount);
    const errorMessage = ref(chart.errorMessage);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = chart.ready;
        degraded.value = chart.degraded;
        state.value = chart.state;
        view.value = chart.view;
        config.value = chart.config;
        option.value = chart.option;
        theme.value = chart.theme;
        requestCount.value = chart.requestCount;
        errorMessage.value = chart.errorMessage;
    };
    const off = chart.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        chart.dispose();
    });
    /** 包裹动作：执行后同步响应式面。 */
    const run = (action) => {
        const value = action();
        sync();
        return value;
    };
    return {
        chart,
        ready,
        degraded,
        state,
        view,
        config,
        option,
        theme,
        requestCount,
        errorMessage,
        setReady: (value) => run(() => chart.setReady(value)),
        setTokens: (reader) => run(() => chart.setTokens(reader)),
        setPrefersDark: (value) => run(() => chart.setPrefersDark(value)),
        setJobs: (jobs) => run(() => chart.setJobs(jobs)),
        setConfig: (value) => run(() => chart.setConfig(normalizeChartConfig(value))),
        setRawOption: (value) => run(() => chart.setRawOption(value)),
        setChartType: (kind) => run(() => chart.setChartType(kind)),
        setMapping: (mapping) => run(() => chart.setMapping(mapping)),
        setView: (next) => run(() => chart.setView(next)),
        setThemeMode: (mode) => run(() => chart.setThemeMode(mode)),
        setRenderMode: (mode) => run(() => chart.setRenderMode(mode)),
        setHeight: (height) => run(() => chart.setHeight(height)),
        setEngine: (engine) => run(() => chart.setEngine(engine === undefined ? undefined : markRaw(toRaw(engine)))),
        setResult: (result) => run(() => chart.setResult(result)),
        load: async (input) => {
            const value = await chart.load(input);
            sync();
            return value;
        },
        refresh: async () => {
            const value = await chart.refresh();
            sync();
            return value;
        },
        resize: (nowMs) => run(() => chart.resize(nowMs)),
        exportImage: (type) => chart.exportImage(type),
    };
}
