<script setup lang="ts">
// 字段权限单元格子件（08_04_02）：三态（可见 / 可编辑）语义由字段权限族基类投影承载。
import type { FieldPermCell as FieldPermItem } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseFieldPerm } from '../../composables/useBaseFieldPerm'

interface Props {
  /** 表单键。 */
  formKey?: string
  /** 字段权限项。 */
  field?: FieldPermItem
  /** 是否禁用。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  formKey: '',
  field: undefined,
  disabled: false,
})

const emit = defineEmits<{
  change: [payload: { key: 'visible' | 'editable'; value: boolean }]
}>()

const perm = useBaseFieldPerm({
  visible: props.field?.visible ?? true,
  editable: props.field?.editable ?? true,
})

watch(
  () => props.field,
  (field) => {
    perm.applyPerm({ visible: field?.visible !== false, editable: field?.editable !== false })
  },
  { immediate: true },
)

/** 是否渲染（不可见字段不渲染权限格）。 */
const rendered = computed(() => perm.rendered.value)

/** 生效禁用（权限不可编辑或外部禁用）。 */
const cellDisabled = computed(() => props.disabled || perm.effectiveDisabled.value)

/** 切换可见 / 可编辑。 */
function toggle(key: 'visible' | 'editable', value: boolean): void {
  perm.applyPerm({ [key]: value })
  emit('change', { key, value })
}
</script>

<template>
  <span
    class="bms-field-perm-cell"
    data-test="field-perm-cell"
    :data-form="formKey"
    :data-field="field?.key"
    :data-visible="perm.permVisible.value"
    :data-editable="perm.editable.value"
  >
    <label>
      可见
      <input
        type="checkbox"
        data-test="cell-visible"
        :checked="perm.permVisible.value"
        :disabled="disabled"
        @change="toggle('visible', !perm.permVisible.value)"
      />
    </label>
    <label v-if="rendered">
      可编辑
      <input
        type="checkbox"
        data-test="cell-editable"
        :checked="perm.editable.value"
        :disabled="cellDisabled"
        @change="toggle('editable', !perm.editable.value)"
      />
    </label>
  </span>
</template>
