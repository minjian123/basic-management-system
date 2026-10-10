/** 权限上下文投影：把核心权限上下文能力基类 `BaseAccess` 投影为组合式（权限码集合与判定）。 */
import { BaseAccess } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体权限上下文（可实例化）。 */
class AccessState extends BaseAccess {
}
/**
 * 使用权限上下文投影。
 *
 * @param codes 初始权限码。
 * @returns 权限基类实例与响应式面。
 */
export function useBaseAccess(codes = []) {
    const access = new AccessState();
    access.setCodes(codes);
    const codesRef = ref([...access.codes]);
    const off = access.onLifecycle((event) => {
        if (event === 'update') {
            codesRef.value = [...access.codes];
        }
    });
    onScopeDispose(off);
    return {
        access,
        codes: codesRef,
        setCodes: (next) => access.setCodes(next),
        has: (code) => access.has(code),
        hasAny: (list) => access.hasAny(list),
        hasAll: (list) => access.hasAll(list),
        canAccess: (code) => (code === undefined ? true : access.has(code)),
    };
}
