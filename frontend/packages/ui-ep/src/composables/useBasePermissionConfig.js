/** 授权编排投影（新口径）：把核心能力基类 `BasePermissionConfig` 投影为组合式（四页签 / 来源判定 / 三类提交与用户差量）。 */
import { BasePermissionConfig, PERMISSION_GRANT_CODE, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体授权编排件（可实例化）。 */
class PermissionConfigState extends BasePermissionConfig {
}
/**
 * 使用授权编排投影。
 *
 * @param options 选项。
 * @returns 编排基类实例与响应式面。
 */
export function useBasePermissionConfig(options = {}) {
    const config = new PermissionConfigState();
    config.grantPerm = options.grantPerm ?? PERMISSION_GRANT_CODE;
    if (options.jobs !== undefined) {
        config.jobs = options.jobs;
    }
    if (options.access !== undefined) {
        config.access = markRaw(toRaw(options.access));
    }
    if (options.notice !== undefined) {
        config.notice = markRaw(toRaw(options.notice));
    }
    if (options.tab !== undefined) {
        config.tab = options.tab;
    }
    if (options.roleId !== undefined) {
        config.setRole(options.roleId);
    }
    config.setReady(options.ready ?? false);
    const ready = ref(config.ready);
    const degraded = ref(config.degraded);
    const disabled = ref(config.disabled);
    const tab = ref(config.tab);
    const metadata = ref(config.metadata);
    const entries = ref(config.entries);
    const fieldEntries = ref(config.fieldEntries);
    const dataScopeEntries = ref(config.dataScopeEntries);
    const users = ref(config.users);
    const selectedMenuId = ref(config.selectedMenuId);
    const menuSubTab = ref(config.menuSubTab);
    const selectedFormId = ref(config.selectedFormId);
    const formSubTab = ref(config.formSubTab);
    const selectedDictTypeId = ref(config.selectedDictTypeId);
    const dataScopePolicy = ref(config.dataScopePolicy);
    const dirty = ref(config.dirty);
    const phase = ref(config.phase);
    const busy = ref(config.busy);
    const errorMessage = ref(config.errorMessage);
    const errorTarget = ref(config.errorTarget);
    const pendingAccessRefresh = ref(config.pendingAccessRefresh);
    const refreshError = ref(config.refreshError);
    const requestCount = ref(config.requestCount);
    const canSave = ref(config.canSave);
    const canGrant = ref(config.canGrant);
    const loadReady = ref(config.loadReady);
    const submitReady = ref(config.submitReady);
    const refreshReady = ref(config.refreshReady);
    /** 从编排基类实例同步响应式面。 */
    const sync = () => {
        ready.value = config.ready;
        degraded.value = config.degraded;
        disabled.value = config.disabled;
        tab.value = config.tab;
        metadata.value = config.metadata;
        entries.value = config.entries;
        fieldEntries.value = config.fieldEntries;
        dataScopeEntries.value = config.dataScopeEntries;
        users.value = config.users;
        selectedMenuId.value = config.selectedMenuId;
        menuSubTab.value = config.menuSubTab;
        selectedFormId.value = config.selectedFormId;
        formSubTab.value = config.formSubTab;
        selectedDictTypeId.value = config.selectedDictTypeId;
        dataScopePolicy.value = config.dataScopePolicy;
        dirty.value = config.dirty;
        phase.value = config.phase;
        busy.value = config.busy;
        errorMessage.value = config.errorMessage;
        errorTarget.value = config.errorTarget;
        pendingAccessRefresh.value = config.pendingAccessRefresh;
        refreshError.value = config.refreshError;
        requestCount.value = config.requestCount;
        canSave.value = config.canSave;
        canGrant.value = config.canGrant;
        loadReady.value = config.loadReady;
        submitReady.value = config.submitReady;
        refreshReady.value = config.refreshReady;
    };
    const off = config.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    /** 包裹「写入后同步」。 */
    const wrap = (action) => {
        action();
        sync();
    };
    return {
        config,
        ready,
        degraded,
        disabled,
        tab,
        metadata,
        entries,
        fieldEntries,
        dataScopeEntries,
        users,
        selectedMenuId,
        menuSubTab,
        selectedFormId,
        formSubTab,
        selectedDictTypeId,
        dataScopePolicy,
        dirty,
        phase,
        busy,
        errorMessage,
        errorTarget,
        pendingAccessRefresh,
        refreshError,
        requestCount,
        canSave,
        canGrant,
        loadReady,
        submitReady,
        refreshReady,
        setReady: (value) => wrap(() => config.setReady(value)),
        setTab: (next) => wrap(() => config.setTab(next)),
        setRole: (roleId) => wrap(() => config.setRole(roleId)),
        setJobs: (jobs) => wrap(() => config.setJobs(jobs)),
        setAccess: (access) => wrap(() => {
            config.access = access === undefined ? undefined : markRaw(toRaw(access));
        }),
        applyMetadata: (next) => wrap(() => config.applyMetadata(next)),
        applySnapshot: (snapshot) => wrap(() => config.applySnapshot(snapshot)),
        selectMenu: (id) => wrap(() => config.selectMenu(id)),
        setMenuSubTab: (sub) => wrap(() => config.setMenuSubTab(sub)),
        selectForm: (id) => wrap(() => config.selectForm(id)),
        setFormSubTab: (sub) => wrap(() => config.setFormSubTab(sub)),
        selectDictType: (id) => wrap(() => config.selectDictType(id)),
        setDataScopePolicy: (policy) => wrap(() => config.setDataScopePolicy(policy)),
        toggleMenu: (id, checked) => {
            const applied = config.toggleMenu(id, checked);
            sync();
            return applied;
        },
        toggleAction: (actionId, sourceMenuId, checked) => {
            const applied = config.toggleAction(actionId, sourceMenuId, checked);
            sync();
            return applied;
        },
        checkMenuState: (id) => config.checkMenuState(id),
        formSources: (formId) => config.formSources(formId),
        actionSources: (actionId) => config.actionSources(actionId),
        setFieldPerm: (formId, fieldId, patch, sourceMenuId) => {
            const applied = config.setFieldPerm(formId, fieldId, patch, sourceMenuId);
            sync();
            return applied;
        },
        setDataScope: (dictTypeId, policyType, scopeConfig) => {
            const applied = config.setDataScope(dictTypeId, policyType, scopeConfig);
            sync();
            return applied;
        },
        bindUsers: (assigned) => {
            const applied = config.bindUsers(assigned);
            sync();
            return applied;
        },
        unbindUser: (id) => {
            const applied = config.unbindUser(id);
            sync();
            return applied;
        },
        idempotencyKey: (kind) => config.idempotencyKey(kind),
        load: async () => {
            await config.load();
            sync();
        },
        save: async () => {
            const result = await config.save();
            sync();
            return result;
        },
        refreshAccess: async () => {
            const result = await config.refreshAccess();
            sync();
            return result;
        },
        retry: async () => {
            const result = await config.retry();
            sync();
            return result;
        },
        reset: () => wrap(() => config.reset()),
        discard: () => wrap(() => config.discard()),
    };
}
