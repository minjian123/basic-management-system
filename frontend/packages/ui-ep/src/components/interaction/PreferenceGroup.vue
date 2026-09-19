<script setup lang="ts">
// 偏好分组容器：分组标题 / 描述 + 偏好项插槽（可折叠；供偏好面板与独立设置页复用）。
import { watch } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

interface Props {
  /** 分组标题。 */
  title: string
  /** 分组描述。 */
  description?: string
  /** 是否可折叠。 */
  collapsible?: boolean
  /** 折叠态（`v-model:collapsed`）。 */
  collapsed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  description: '',
  collapsible: false,
  collapsed: false,
})

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
}>()

const {
  collapsed: collapsedState,
  setCollapsible,
  setCollapsed,
  toggle,
} = useBaseContainer({
  collapsible: props.collapsible,
  collapsed: props.collapsed,
})

watch(
  () => props.collapsible,
  (value) => setCollapsible(value),
)
watch(
  () => props.collapsed,
  (value) => setCollapsed(value),
)
watch(collapsedState, (value) => emit('update:collapsed', value))
</script>

<template>
  <section class="bms-preference-group" :data-collapsed="collapsedState ? 'true' : 'false'">
    <header class="bms-preference-group__header">
      <button
        v-if="collapsible"
        type="button"
        class="bms-preference-group__toggle"
        data-test="preference-group-toggle"
        @click="toggle"
      >
        <span class="bms-preference-group__arrow">{{ collapsedState ? '▸' : '▾' }}</span>
        <span class="bms-preference-group__title">{{ title }}</span>
      </button>
      <span v-else class="bms-preference-group__title" data-test="preference-group-title">{{ title }}</span>
      <slot name="extra" />
    </header>
    <p v-if="description && !collapsedState" class="bms-preference-group__description">
      {{ description }}
    </p>
    <div v-show="!collapsedState" class="bms-preference-group__body" data-test="preference-group-body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.bms-preference-group {
  margin-bottom: var(--bms-spacing-lg, 16px);
}

.bms-preference-group__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bms-spacing-md, 8px);
}

.bms-preference-group__toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 4px);
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-preference-group__title {
  font-weight: 600;
  font-size: 13px;
}

.bms-preference-group__description {
  margin: var(--bms-spacing-sm, 4px) 0 0;
  color: var(--bms-color-text-secondary, #909399);
  font-size: 12px;
}

.bms-preference-group__body {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md, 8px);
  margin-top: var(--bms-spacing-md, 8px);
}
</style>
