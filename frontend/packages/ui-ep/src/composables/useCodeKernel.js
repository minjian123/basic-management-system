/** 编辑内核投影：把核心编辑器内核能力基类 `BaseEditorKernel` 投影为组合式；CodeMirror 模块级缓存，多次使用不重复加载。 */
import { BaseEditorKernel } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 模块级缓存（Promise 复用 → 不重复加载）。 */
let codeModulesPromise;
/** 模块实际加载次数（测试断言恒为 1）。 */
let codeModuleLoads = 0;
/**
 * 加载 CodeMirror 模块（模块级缓存，多次调用只加载一次）。
 *
 * @returns 模块集合。
 */
export function loadCodeModules() {
    if (!codeModulesPromise) {
        codeModuleLoads += 1;
        codeModulesPromise = Promise.all([
            import('codemirror'),
            import('@codemirror/state'),
            import('@codemirror/lang-sql'),
            import('@codemirror/lang-json'),
            import('@codemirror/lang-javascript'),
        ]).then(([cm, state, sql, json, javascript]) => {
            const stateCtor = state.EditorState;
            const viewCtor = cm.EditorView;
            return {
                basicSetup: cm.basicSetup,
                EditorView: cm.EditorView,
                EditorState: state.EditorState,
                readOnly: stateCtor.readOnly,
                editable: viewCtor.editable,
                sql: sql.sql,
                json: json.json,
                javascript: javascript.javascript,
            };
        });
    }
    return codeModulesPromise;
}
/** 取 CodeMirror 模块加载次数（测试用）。 */
export function getCodeModuleLoadCount() {
    return codeModuleLoads;
}
/** 重置模块缓存与计数（测试用）。 */
export function resetCodeModuleCache() {
    codeModulesPromise = undefined;
    codeModuleLoads = 0;
}
/** 具体编辑内核（可实例化）。 */
class CodeKernelState extends BaseEditorKernel {
}
/**
 * 使用编辑内核投影。
 *
 * @returns 编辑内核基类实例与响应式面。
 */
export function useCodeKernel() {
    const kernel = new CodeKernelState();
    kernel.mode = 'code';
    kernel.loader = () => loadCodeModules();
    const loaded = ref(kernel.loaded);
    const off = kernel.onLifecycle((event) => {
        if (event === 'update') {
            loaded.value = kernel.loaded;
        }
    });
    onScopeDispose(off);
    return {
        kernel,
        loaded,
        load: async () => {
            await kernel.load();
            loaded.value = kernel.loaded;
        },
        destroy: () => {
            kernel.destroy();
            loaded.value = kernel.loaded;
        },
    };
}
