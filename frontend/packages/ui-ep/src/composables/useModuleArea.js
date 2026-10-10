/**
 * 模块区域插槽投影：承接布局与容器组件基类投影，并按区域标识解析已登记区域项（只读消费）；
 * 并承载**具名插槽显式上下文通道**（宿主页提供 → 区域项只读取得，需求 `05-11`）。
 */
import { computed, defineAsyncComponent, inject, provide, readonly, ref, toValue, watch, } from 'vue';
import { useBaseContainer } from './useBaseContainer';
import { useBaseLayout } from './useBaseLayout';
/**
 * 区域项稳定排序（顺序提示升序，同值保持登记序）。
 *
 * @param left 左项。
 * @param right 右项。
 */
function compareItems(left, right) {
    return left.order - right.order;
}
/**
 * 使用模块区域插槽投影。
 *
 * @param options 选项。
 * @returns 区域项与解析面。
 */
export function useModuleArea(options) {
    const layout = useBaseLayout();
    const container = useBaseContainer();
    const revision = computed(() => toValue(options.revision ?? 0));
    const permissionCodes = computed(() => toValue(options.permissionCodes ?? []));
    /** 已解析挂接组件（按函数标识复用，避免重复创建异步组件）。 */
    const resolved = new WeakMap();
    /** 读取当前区域项（按显示条件与权限过滤后保序）。 */
    function readItems() {
        const area = toValue(options.area);
        return options.registries.pageArea
            .resolveByArea(area, { permissionCodes: permissionCodes.value })
            .map((record) => ({
            key: record.key,
            order: record.order,
            component: record.component,
            title: record.title,
            icon: record.icon,
        }))
            .sort(compareItems);
    }
    const items = ref(readItems());
    watch([() => toValue(options.area), revision, permissionCodes], () => {
        items.value = readItems();
    });
    /**
     * 解析挂接组件（函数视为异步加载器）。
     *
     * @param component 挂接组件。
     */
    function resolve(component) {
        if (typeof component !== 'function') {
            return component;
        }
        const key = component;
        const hit = resolved.get(key);
        if (hit !== undefined) {
            return hit;
        }
        const async = defineAsyncComponent(component);
        resolved.set(key, async);
        return async;
    }
    return {
        hidden: layout.hidden,
        container,
        items,
        isEmpty: computed(() => items.value.length === 0),
        resolve,
    };
}
/** 具名插槽上下文注入键（宿主页与插件均不直接使用）。 */
export const MODULE_SLOT_CONTEXT_KEY = Symbol('bms.module-slot-context');
/**
 * 提供具名插槽上下文（**区域插槽件内部使用**）。
 *
 * 上下文以**冻结浅拷贝**提供：区域项（插件）侧改动不生效；未声明即为 `undefined`（插件自行降级）。
 *
 * @param context 上下文来源（响应式；宿主页声明的作用实体标识等）。
 */
export function provideModuleSlotContext(context) {
    const source = computed(() => {
        const value = toValue(context);
        return value === undefined ? undefined : Object.freeze({ ...value });
    });
    provide(MODULE_SLOT_CONTEXT_KEY, readonly(source));
}
/**
 * 读取具名插槽上下文（**区域项组件消费**）。
 *
 * 非路由承载宿主页（表单框架记录页签等）的作用实体标识经此取得；未注入时为 `undefined`。
 *
 * @returns 只读上下文（调用方自行降级：不假定存在、不发起请求）。
 */
export function useModuleSlotContext() {
    const source = inject(MODULE_SLOT_CONTEXT_KEY, undefined);
    return computed(() => source?.value);
}
/**
 * 读取具名插槽上下文的单个字段（**区域项组件消费**）。
 *
 * @param key 字段名。
 * @returns 字段值（未注入或键缺失时为 `undefined`）。
 */
export function useModuleSlotField(key) {
    const context = useModuleSlotContext();
    return computed(() => context.value?.[key]);
}
