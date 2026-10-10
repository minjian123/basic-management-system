/** 流程建模编排投影：把核心能力基类 `BaseProcessModeler` 投影为组合式（定义装载 / XML 更新与导入 / 校验合并 / 保存发布与幂等 / 脏基线与只读）。 */
import { BaseProcessModeler, } from '@bms/core';
import { computed, markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体流程建模编排件（可实例化）。 */
class ProcessModelerState extends BaseProcessModeler {
}
/**
 * 使用流程建模编排投影。
 *
 * @param options 选项。
 * @returns 编排基类实例与响应式面。
 */
export function useBaseProcessModeler(options = {}) {
    const modeler = new ProcessModelerState();
    if (options.jobs !== undefined) {
        modeler.setJobs(options.jobs);
    }
    if (options.access !== undefined) {
        modeler.setAccess(markRaw(toRaw(options.access)));
    }
    if (options.notice !== undefined) {
        modeler.setNotice(markRaw(toRaw(options.notice)));
    }
    modeler.applyDefinition({
        definitionKey: options.definitionKey,
        version: options.version,
        xml: options.xml,
    });
    modeler.setReadOnly(options.readOnly ?? false);
    modeler.setReady(options.ready ?? false);
    const ready = ref(modeler.ready);
    const degraded = ref(modeler.degraded);
    const disabled = ref(modeler.disabled);
    const readOnly = ref(modeler.readOnly);
    const busy = ref(modeler.busy);
    const phase = ref(modeler.phase);
    const definition = ref(modeler.definition);
    const xml = ref(modeler.xml);
    const dirty = ref(modeler.dirty);
    const canEdit = ref(modeler.canEdit);
    const canDeploy = ref(modeler.canDeploy);
    const selected = ref(modeler.selected);
    const validateResult = ref(modeler.validateResult);
    const errorMessage = ref(modeler.errorMessage);
    const errorTarget = ref(modeler.errorTarget);
    const requestCount = ref(modeler.requestCount);
    /** 定义标识（响应式派生）。 */
    const definitionKey = computed(() => definition.value.definitionKey);
    /** 定义名称（响应式派生）。 */
    const definitionName = computed(() => definition.value.name);
    /** 版本号（响应式派生）。 */
    const version = computed(() => definition.value.version);
    /** 从编排基类实例同步响应式面。 */
    const sync = () => {
        ready.value = modeler.ready;
        degraded.value = modeler.degraded;
        disabled.value = modeler.disabled;
        readOnly.value = modeler.readOnly;
        busy.value = modeler.busy;
        phase.value = modeler.phase;
        definition.value = modeler.definition;
        xml.value = modeler.xml;
        dirty.value = modeler.dirty;
        canEdit.value = modeler.canEdit;
        canDeploy.value = modeler.canDeploy;
        selected.value = modeler.selected;
        validateResult.value = modeler.validateResult;
        errorMessage.value = modeler.errorMessage;
        errorTarget.value = modeler.errorTarget;
        requestCount.value = modeler.requestCount;
    };
    const off = modeler.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        modeler,
        ready,
        degraded,
        disabled,
        readOnly,
        busy,
        phase,
        definitionKey,
        definitionName,
        version,
        xml,
        dirty,
        canEdit,
        canDeploy,
        selected,
        validateResult,
        errorMessage,
        errorTarget,
        requestCount,
        structure: () => modeler.structure,
        setReady: (value) => {
            modeler.setReady(value);
            sync();
        },
        setReadOnly: (value) => {
            modeler.setReadOnly(value);
            sync();
        },
        setJobs: (jobs) => {
            modeler.setJobs(jobs);
            sync();
        },
        setAccess: (access) => {
            modeler.setAccess(access === undefined ? undefined : markRaw(toRaw(access)));
            sync();
        },
        setNotice: (notice) => {
            modeler.setNotice(notice === undefined ? undefined : markRaw(toRaw(notice)));
            sync();
        },
        applyDefinition: (input) => {
            modeler.applyDefinition(input);
            sync();
        },
        load: async (definitionKey, version) => {
            const result = await modeler.load(definitionKey, version);
            sync();
            return result;
        },
        updateXml: (next) => {
            modeler.updateXml(next);
            sync();
        },
        importXml: (next) => {
            const result = modeler.importXml(next);
            sync();
            return result;
        },
        requestImport: (next) => {
            const result = modeler.requestImport(next);
            sync();
            return result;
        },
        confirmImport: () => {
            const result = modeler.confirmImport();
            sync();
            return result;
        },
        cancelImport: () => {
            modeler.cancelImport();
            sync();
        },
        exportXml: () => modeler.exportXml(),
        select: (elementId) => {
            const result = modeler.select(elementId);
            sync();
            return result;
        },
        validate: async (validateOptions) => {
            const result = await modeler.validate(validateOptions);
            sync();
            return result;
        },
        saveDraft: async () => {
            const result = await modeler.saveDraft();
            sync();
            return result;
        },
        deploy: async () => {
            const result = await modeler.deploy();
            sync();
            return result;
        },
        retry: async () => {
            const result = await modeler.retry();
            sync();
            return result;
        },
        idempotencyKey: (kind) => modeler.idempotencyKey(kind),
        discard: () => {
            modeler.discard();
            sync();
        },
        reset: () => {
            modeler.reset();
            sync();
        },
    };
}
