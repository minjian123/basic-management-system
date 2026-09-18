<script setup lang="ts">
// 大屏自由画布（占位，08_01_03）：由 ScreenDesigner 异步懒加载的独立分包入口，真实实现（08_09）承载绝对定位拖拽与缩放。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { ScreenComponent } from './ScreenDesigner.vue'

interface Props {
  /** 当前页组件。 */
  components?: ScreenComponent[]
  /** 当前选中组件标识。 */
  selectedId?: string
  /** 只读。 */
  readOnly?: boolean
  /** 当前页标识。 */
  activePageId?: string
}

const props = withDefaults(defineProps<Props>(), {
  components: () => [],
  selectedId: '',
  readOnly: false,
  activePageId: '',
})

const emit = defineEmits<{
  select: [id: string]
  'remove-component': [id: string]
}>()

const { state, setState } = useBaseDataState()
watch(
  () => props.components.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-screen-canvas"
    data-test="screen-canvas"
    data-subpackage="screen"
    :data-state="state"
    :data-page="activePageId"
    :data-readonly="readOnly"
  >
    <p v-if="components.length === 0" data-test="canvas-empty">当前页暂无组件（占位，真实实现支持拖放定位）</p>
    <div
      v-for="item in components"
      :key="item.id"
      class="bms-screen-canvas__item"
      :data-test="`component-${item.id}`"
      :data-type="item.type"
      :data-selected="item.id === selectedId || undefined"
      @click="emit('select', item.id)"
    >
      <span>{{ item.text || item.type }}</span>
      <button
        type="button"
        :data-test="`remove-${item.id}`"
        :disabled="readOnly"
        @click.stop="emit('remove-component', item.id)"
      >
        删除
      </button>
    </div>
  </div>
</template>
