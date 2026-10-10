/** 租户切换投影：把核心租户切换能力基类 `BaseTenant` 投影为组合式（当前租户 / 列表 / 阶段 / 编排）。 */
import { BaseTenant, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体租户件（可实例化）。 */
class Tenant extends BaseTenant {
}
/**
 * 使用租户切换投影。
 *
 * @param options 选项。
 * @returns 租户基类实例与响应式面。
 */
export function useBaseTenant(options = {}) {
    const tenant = new Tenant();
    tenant.confirmRequired = options.confirmRequired ?? true;
    if (options.steps !== undefined) {
        tenant.steps = options.steps;
    }
    if (options.theme !== undefined) {
        tenant.theme = markRaw(toRaw(options.theme));
    }
    if (options.notice !== undefined) {
        tenant.notice = markRaw(toRaw(options.notice));
    }
    if (options.context !== undefined) {
        tenant.context = markRaw(toRaw(options.context));
    }
    if (options.tenants !== undefined) {
        tenant.setTenants(options.tenants);
    }
    if (options.current !== undefined) {
        tenant.setCurrent(options.current);
    }
    const tenants = ref([...tenant.tenants]);
    const current = ref(tenant.current);
    const phase = ref(tenant.phase);
    const errorMessage = ref(tenant.errorMessage);
    const multiTenant = ref(tenant.multiTenant);
    const switching = ref(tenant.switching);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        tenants.value = [...tenant.tenants];
        current.value = tenant.current;
        phase.value = tenant.phase;
        errorMessage.value = tenant.errorMessage;
        multiTenant.value = tenant.multiTenant;
        switching.value = tenant.switching;
    };
    const off = tenant.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        tenant,
        tenants,
        current,
        phase,
        errorMessage,
        multiTenant,
        switching,
        setTenants: (list) => {
            tenant.setTenants(list);
            sync();
        },
        setCurrent: (value) => {
            tenant.setCurrent(value);
            sync();
        },
        setSteps: (steps) => {
            tenant.steps = steps;
            sync();
        },
        search: (keyword) => tenant.search(keyword),
        isCurrent: (id) => tenant.isCurrent(id),
        request: async (targetId) => {
            const ok = await tenant.request(targetId);
            sync();
            return ok;
        },
        confirm: async (targetId) => {
            const ok = await tenant.confirm(targetId);
            sync();
            return ok;
        },
        switchTo: async (targetId) => {
            const ok = await tenant.switchTo(targetId);
            sync();
            return ok;
        },
        retry: async () => {
            const ok = await tenant.retry();
            sync();
            return ok;
        },
        reset: () => {
            tenant.reset();
            sync();
        },
    };
}
