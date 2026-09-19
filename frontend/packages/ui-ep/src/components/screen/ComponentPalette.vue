<script setup lang="ts">
// 大屏组件面板（08-9-2）：按分组渲染可拖放组件；点击或拖拽上抛，由设计器驱动新增与拖拽广播。
import { paletteGroups, type ScreenComponentType } from '@bms/core'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 只读。 */
  readOnly?: boolean
  /** 禁用（占位 / 降级）。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  readOnly: false,
  disabled: false,
})

const emit = defineEmits<{
  add: [type: ScreenComponentType]
  'drag-start': [type: ScreenComponentType]
}>()

/** 分组清单。 */
const groups = paletteGroups()
const { setState } = useBaseDataState()
setState('ready')

/** 是否禁用交互。 */
function isDisabled(): boolean {
  return props.readOnly || props.disabled
}
</script>

<template>
  <div class="bms-component-palette" data-test="component-palette">
    <section v-for="group in groups" :key="group.category" class="bms-component-palette__group" :data-test="`palette-group-${group.category}`">
      <h4 class="bms-component-palette__title">{{ group.category }}</h4>
      <div class="bms-component-palette__items">
        <button
          v-for="item in group.items"
          :key="item.type"
          type="button"
          class="bms-component-palette__item"
          draggable="true"
          :data-test="`palette-${item.type}`"
          :disabled="isDisabled()"
          @click="emit('add', item.type)"
          @dragstart="emit('drag-start', item.type)"
        >
          {{ item.label }}
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.bms-component-palette {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.bms-component-palette__title {
  margin: 0 0 6px;
  color: var(--bms-color-text-secondary, #909399);
  font-size: 12px;
}
.bms-component-palette__items {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
}
.bms-component-palette__item {
  padding: 6px 8px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-md, 4px);
  background: var(--bms-color-bg, #fff);
  cursor: grab;
}
.bms-component-palette__item:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
