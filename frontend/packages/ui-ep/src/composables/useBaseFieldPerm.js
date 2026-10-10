/** 字段权限投影：把字段权限族组件基类 `BaseFieldPerm` 投影为组合式（可见 / 可编辑 / 必填三态与脱敏）。 */
import { BaseFieldPerm } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体字段权限件（可实例化）。 */
class FieldPermState extends BaseFieldPerm {
}
/**
 * 使用字段权限投影。
 *
 * @param options 选项。
 * @returns 字段权限基类实例与响应式面。
 */
export function useBaseFieldPerm(options = {}) {
    const perm = new FieldPermState();
    perm.applyPerm({
        visible: options.visible ?? true,
        editable: options.editable ?? true,
        required: options.required ?? false,
        mask: options.mask ?? false,
    });
    const permVisible = ref(perm.permVisible);
    const editable = ref(perm.editable);
    const permRequired = ref(perm.permRequired);
    const masked = ref(perm.masked);
    const rendered = ref(perm.rendered);
    const effectiveDisabled = ref(perm.effectiveDisabled);
    /** 从字段权限基类实例同步响应式面。 */
    const sync = () => {
        permVisible.value = perm.permVisible;
        editable.value = perm.editable;
        permRequired.value = perm.permRequired;
        masked.value = perm.masked;
        rendered.value = perm.rendered;
        effectiveDisabled.value = perm.effectiveDisabled;
    };
    const off = perm.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        perm,
        permVisible,
        editable,
        permRequired,
        masked,
        rendered,
        effectiveDisabled,
        applyPerm: (permission) => perm.applyPerm(permission),
    };
}
