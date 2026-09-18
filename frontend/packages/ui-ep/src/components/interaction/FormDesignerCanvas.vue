<script setup lang="ts">
// 表单设计器画布（占位，08_01_02）：由 FormDesigner 异步懒加载的独立分包入口，真实实现（08_06）承载拖拽内核。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { DesignerField, DesignerSelection, FormLayout } from './FormDesigner.vue'

interface Props {
  /** 字段清单。 */
  fields?: DesignerField[]
  /** 当前层级布局。 */
  layout?: FormLayout | undefined
  /** 只读（平台默认层级 / 无权限）。 */
  readOnly?: boolean
  /** 是否存在未保存变更。 */
  dirty?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  fields: () => [],
  layout: undefined,
  readOnly: false,
  dirty: false,
})

const emit = defineEmits<{
  select: [target: DesignerSelection | null]
}>()

const { state, setState } = useBaseDataState()
watch(
  () => props.layout?.main?.sections?.length ?? 0,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

function fieldLabel(key: string): string {
  return props.fields.find((item) => item.key === key)?.label ?? key
}
</script>

<template>
  <div
    class="bms-designer-canvas"
    data-test="designer-canvas"
    data-subpackage="designer"
    :data-state="state"
    :data-readonly="readOnly"
    :data-dirty="dirty"
  >
    <p v-if="(layout?.main?.sections?.length ?? 0) === 0" data-test="canvas-empty">
      暂无布局分区（占位，真实实现支持字段拖入）
    </p>
    <div
      v-for="section in layout?.main?.sections ?? []"
      :key="section.key"
      class="bms-designer-canvas__section"
      :data-test="`designer-section-${section.key}`"
      :data-columns="section.columns"
      @click="emit('select', { kind: 'section', key: section.key })"
    >
      <strong>{{ section.title }}</strong>
      <span
        v-for="field in section.fields"
        :key="field.key"
        class="bms-designer-canvas__field"
        :data-test="`designer-field-${field.key}`"
        :data-colspan="field.colSpan || undefined"
        @click.stop="emit('select', { kind: 'field', key: field.key })"
      >
        {{ fieldLabel(field.key) }}
      </span>
    </div>
  </div>
</template>
