/** 表单渲染器投影：把核心渲染编排能力基类 `BaseFormRenderer` 投影为组合式（三态 / 计划 / 校验 / 明细 / 提交）。 */
import { BaseFormRenderer } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体表单渲染器（可实例化）。 */
class FormRendererState extends BaseFormRenderer {
}
/**
 * 使用表单渲染器投影。
 *
 * @param options 选项。
 * @returns 渲染器基类实例与响应式面。
 */
export function useBaseFormRenderer(options = {}) {
    const renderer = new FormRendererState();
    // 跨实例基类对象经 props 进响应式会读取私有字段报错，统一 `markRaw(toRaw(x))` 隔离。
    if (options.access !== undefined) {
        renderer.setAccess(markRaw(toRaw(options.access)));
    }
    if (options.notice !== undefined) {
        renderer.setNotice(markRaw(toRaw(options.notice)));
    }
    if (options.formMeta !== undefined) {
        renderer.setFormMeta(markRaw(toRaw(options.formMeta)));
    }
    if (options.fieldPerm !== undefined) {
        renderer.setFieldPerm(markRaw(toRaw(options.fieldPerm)));
    }
    if (options.validatable !== undefined) {
        renderer.setValidatable(markRaw(toRaw(options.validatable)));
    }
    if (options.jobs !== undefined) {
        renderer.setJobs(options.jobs);
    }
    if (options.formCode !== undefined) {
        renderer.setFormCode(options.formCode);
    }
    if (options.mode !== undefined) {
        renderer.setMode(options.mode);
    }
    if (options.recordId !== undefined) {
        renderer.setRecordId(options.recordId);
    }
    renderer.setForceReadOnly(options.forceReadOnly ?? false);
    if (options.meta !== undefined) {
        renderer.setMeta(options.meta);
    }
    if (options.data !== undefined) {
        renderer.setData(options.data);
    }
    if (options.details !== undefined) {
        renderer.setDetails(options.details);
    }
    if (options.permissions !== undefined) {
        renderer.setPermissions(options.permissions);
    }
    if (options.overrides !== undefined) {
        renderer.setOverrides(options.overrides);
    }
    renderer.setReady(options.ready ?? false);
    const ready = ref(renderer.ready);
    const degraded = ref(renderer.degraded);
    const readonly = ref(renderer.readonly);
    const writable = ref(renderer.writable);
    const busy = ref(renderer.busy);
    const phase = ref(renderer.phase);
    const mode = ref(renderer.mode);
    const plan = ref(renderer.plan);
    const fields = ref(renderer.fields);
    const detailColumns = ref(renderer.detailColumns);
    const data = ref({ ...renderer.data });
    const details = ref({ ...renderer.details });
    const errors = ref([...renderer.errors]);
    const detailErrors = ref([...renderer.detailErrors]);
    const validation = ref(renderer.validation);
    const errorMessage = ref(renderer.errorMessage);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = renderer.ready;
        degraded.value = renderer.degraded;
        readonly.value = renderer.readonly;
        writable.value = renderer.writable;
        busy.value = renderer.busy;
        phase.value = renderer.phase;
        mode.value = renderer.mode;
        plan.value = renderer.plan;
        fields.value = renderer.fields;
        detailColumns.value = renderer.detailColumns;
        data.value = { ...renderer.data };
        details.value = { ...renderer.details };
        errors.value = [...renderer.errors];
        detailErrors.value = [...renderer.detailErrors];
        validation.value = renderer.validation;
        errorMessage.value = renderer.errorMessage;
    };
    const off = renderer.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        renderer,
        ready,
        degraded,
        readonly,
        writable,
        busy,
        phase,
        mode,
        plan,
        fields,
        detailColumns,
        data,
        details,
        errors,
        detailErrors,
        validation,
        errorMessage,
        setReady: (value) => {
            renderer.setReady(value);
            sync();
        },
        setMode: (next) => {
            const changed = renderer.setMode(next);
            sync();
            return changed;
        },
        setFormCode: (formCode) => {
            const changed = renderer.setFormCode(formCode);
            sync();
            return changed;
        },
        setRecordId: (recordId) => {
            renderer.setRecordId(recordId);
            sync();
        },
        setForceReadOnly: (value) => {
            renderer.setForceReadOnly(value);
            sync();
        },
        setMeta: (input) => {
            renderer.setMeta(input);
            sync();
        },
        setData: (next) => {
            renderer.setData(next);
            sync();
        },
        setDetails: (next) => {
            renderer.setDetails(next);
            sync();
        },
        setPermissions: (next) => {
            renderer.setPermissions(next);
            sync();
        },
        setOverrides: (next) => {
            renderer.setOverrides(next);
            sync();
        },
        setJobs: (jobs) => {
            renderer.setJobs(jobs);
            sync();
        },
        setFieldValue: (fieldKey, value) => {
            const changed = renderer.setFieldValue(fieldKey, value);
            sync();
            return changed;
        },
        getFieldValue: (fieldKey) => renderer.getFieldValue(fieldKey),
        setDetailRows: (detailKey, rows) => {
            const changed = renderer.setDetailRows(detailKey, rows);
            sync();
            return changed;
        },
        addDetailRow: (detailKey, row) => {
            const changed = renderer.addDetailRow(detailKey, row);
            sync();
            return changed;
        },
        removeDetailRow: (detailKey, index) => {
            const changed = renderer.removeDetailRow(detailKey, index);
            sync();
            return changed;
        },
        setDetailCell: (detailKey, index, fieldKey, value) => {
            const changed = renderer.setDetailCell(detailKey, index, fieldKey, value);
            sync();
            return changed;
        },
        validate: () => {
            const result = renderer.validate();
            sync();
            return result;
        },
        validateField: (fieldKey) => renderer.validateField(fieldKey),
        load: async () => {
            const result = await renderer.load();
            sync();
            return result;
        },
        submit: async () => {
            const result = await renderer.submit();
            sync();
            return result;
        },
        retry: async () => {
            const result = await renderer.retry();
            sync();
            return result;
        },
        reset: () => {
            renderer.reset();
            sync();
        },
    };
}
