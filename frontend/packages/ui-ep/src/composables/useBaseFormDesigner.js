/** 表单设计器投影：把核心能力基类 `BaseFormDesigner` 投影为组合式（布局 / 层级 / 脏基线 / 保存发布）。 */
import { BaseFormDesigner, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体表单设计器件（可实例化）。 */
class FormDesignerState extends BaseFormDesigner {
}
/**
 * 使用表单设计器投影。
 *
 * @param options 选项。
 * @returns 设计器基类实例与响应式面。
 */
export function useBaseFormDesigner(options = {}) {
    const designer = new FormDesignerState();
    if (options.formCode !== undefined) {
        designer.setFormCode(options.formCode);
    }
    if (options.level !== undefined) {
        designer.setLevel(options.level, options.roleId);
    }
    else if (options.roleId !== undefined) {
        designer.roleId = options.roleId;
    }
    if (options.fields !== undefined) {
        designer.setFields(options.fields);
    }
    if (options.levels !== undefined) {
        designer.setLayouts(options.levels);
    }
    else if (options.layout !== undefined) {
        designer.setLayouts({ [designer.level]: options.layout });
    }
    if (options.jobs !== undefined) {
        designer.jobs = options.jobs;
    }
    if (options.access !== undefined) {
        designer.access = markRaw(toRaw(options.access));
    }
    if (options.notice !== undefined) {
        designer.notice = markRaw(toRaw(options.notice));
    }
    if (options.formMeta !== undefined) {
        designer.formMeta = markRaw(toRaw(options.formMeta));
    }
    if (options.drag !== undefined) {
        designer.drag = markRaw(toRaw(options.drag));
    }
    if (options.registeredTypes !== undefined) {
        designer.setRegisteredTypes(options.registeredTypes);
    }
    designer.setReady(options.ready ?? false);
    const ready = ref(designer.ready);
    const degraded = ref(designer.degraded);
    const readonly = ref(designer.readonly);
    const busy = ref(designer.busy);
    const phase = ref(designer.phase);
    const layout = ref(designer.layout);
    const fields = ref([...designer.fields]);
    const selected = ref(designer.selected);
    const dirty = ref(designer.dirty);
    const errorMessage = ref(designer.errorMessage);
    const fieldError = ref(designer.fieldError);
    const validation = ref(designer.validation);
    const unknownFields = ref(designer.unknownFields);
    const duplicateFields = ref(designer.duplicateFields);
    const renderMetadata = ref(designer.renderMetadata);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = designer.ready;
        degraded.value = designer.degraded;
        readonly.value = designer.readonly;
        busy.value = designer.busy;
        phase.value = designer.phase;
        layout.value = designer.layout;
        fields.value = [...designer.fields];
        selected.value = designer.selected;
        dirty.value = designer.dirty;
        errorMessage.value = designer.errorMessage;
        fieldError.value = designer.fieldError;
        validation.value = designer.validation;
        unknownFields.value = designer.unknownFields;
        duplicateFields.value = designer.duplicateFields;
        renderMetadata.value = designer.renderMetadata;
    };
    const off = designer.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    /** 包裹动作：执行后同步响应式面。 */
    const run = (action) => {
        const value = action();
        sync();
        return value;
    };
    return {
        designer,
        ready,
        degraded,
        readonly,
        busy,
        phase,
        layout,
        fields,
        selected,
        dirty,
        errorMessage,
        fieldError,
        validation,
        unknownFields,
        duplicateFields,
        renderMetadata,
        setReady: (value) => run(() => designer.setReady(value)),
        setFormCode: (formCode) => run(() => designer.setFormCode(formCode)),
        setLevel: (level, roleId) => run(() => designer.setLevel(level, roleId)),
        setFields: (value) => run(() => designer.setFields(value)),
        setLayouts: (levels) => run(() => designer.setLayouts(levels)),
        setJobs: (jobs) => run(() => designer.setJobs(jobs)),
        select: (target) => run(() => designer.select(target)),
        addField: (fieldKey, sectionKey) => run(() => designer.addField(fieldKey, sectionKey)),
        moveField: (input) => run(() => designer.moveField(input)),
        removeField: (fieldKey) => run(() => designer.removeField(fieldKey)),
        toggleColSpan: (fieldKey) => run(() => designer.toggleColSpan(fieldKey)),
        setColumns: (sectionKey, columns) => run(() => designer.setColumns(sectionKey, columns)),
        addSection: () => run(() => designer.addSection()),
        removeSection: (sectionKey) => run(() => designer.removeSection(sectionKey)),
        renameSection: (sectionKey, title) => run(() => designer.renameSection(sectionKey, title)),
        setLabelPosition: (position) => run(() => designer.setLabelPosition(position)),
        setLabelWidth: (width) => run(() => designer.setLabelWidth(width)),
        setQueryFields: (keys) => run(() => designer.setQueryFields(keys)),
        setDetailColumns: (columns) => run(() => designer.setDetailColumns(columns)),
        markBaseline: () => run(() => designer.markBaseline()),
        discard: () => run(() => designer.discard()),
        needsBlock: (action) => designer.needsBlock(action),
        load: async () => {
            const value = await designer.load();
            sync();
            return value;
        },
        save: async () => {
            const value = await designer.save();
            sync();
            return value;
        },
        publish: async () => {
            const value = await designer.publish();
            sync();
            return value;
        },
        restoreDefault: async () => {
            const value = await designer.restoreDefault();
            sync();
            return value;
        },
        createField: async (draft) => {
            const value = await designer.createField(draft);
            sync();
            return value;
        },
        retryField: async (fieldKey) => {
            const value = await designer.retryField(fieldKey);
            sync();
            return value;
        },
    };
}
