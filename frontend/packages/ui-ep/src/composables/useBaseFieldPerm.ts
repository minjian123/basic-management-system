/** 字段权限投影：把字段权限族组件基类 `BaseFieldPerm` 投影为组合式（可见 / 可编辑 / 必填三态与脱敏）。 */

import { BaseFieldPerm, type FieldPermission } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体字段权限件（可实例化）。 */
class FieldPermState extends BaseFieldPerm {}

/** 选项。 */
export interface UseBaseFieldPermOptions {
  /** 权限可见（缺省 `true`）。 */
  visible?: boolean
  /** 权限可编辑（缺省 `true`）。 */
  editable?: boolean
  /** 权限必填（缺省 `false`）。 */
  required?: boolean
  /** 是否脱敏（缺省 `false`）。 */
  mask?: boolean
}

/** `useBaseFieldPerm` 返回面。 */
export interface UseBaseFieldPermResult {
  /** 字段权限基类实例。 */
  perm: BaseFieldPerm
  /** 权限可见（响应式）。 */
  permVisible: Ref<boolean>
  /** 权限可编辑（响应式）。 */
  editable: Ref<boolean>
  /** 权限必填（响应式）。 */
  permRequired: Ref<boolean>
  /** 是否脱敏（响应式）。 */
  masked: Ref<boolean>
  /** 是否渲染（不可见不渲染，响应式）。 */
  rendered: Ref<boolean>
  /** 生效禁用态（响应式）。 */
  effectiveDisabled: Ref<boolean>
  /** 应用字段权限（缺省项不变）。 */
  applyPerm: (permission: FieldPermission) => void
}

/**
 * 使用字段权限投影。
 *
 * @param options 选项。
 * @returns 字段权限基类实例与响应式面。
 */
export function useBaseFieldPerm(options: UseBaseFieldPermOptions = {}): UseBaseFieldPermResult {
  const perm = new FieldPermState()
  perm.applyPerm({
    visible: options.visible ?? true,
    editable: options.editable ?? true,
    required: options.required ?? false,
    mask: options.mask ?? false,
  })

  const permVisible = ref(perm.permVisible)
  const editable = ref(perm.editable)
  const permRequired = ref(perm.permRequired)
  const masked = ref(perm.masked)
  const rendered = ref(perm.rendered)
  const effectiveDisabled = ref(perm.effectiveDisabled)

  /** 从字段权限基类实例同步响应式面。 */
  const sync = (): void => {
    permVisible.value = perm.permVisible
    editable.value = perm.editable
    permRequired.value = perm.permRequired
    masked.value = perm.masked
    rendered.value = perm.rendered
    effectiveDisabled.value = perm.effectiveDisabled
  }

  const off = perm.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(off)

  return {
    perm,
    permVisible,
    editable,
    permRequired,
    masked,
    rendered,
    effectiveDisabled,
    applyPerm: (permission) => perm.applyPerm(permission),
  }
}
