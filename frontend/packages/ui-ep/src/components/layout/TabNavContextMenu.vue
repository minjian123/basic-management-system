<script setup lang="ts">
// 页签右键菜单：刷新 / 关闭 / 关闭其他 / 关闭右侧 / 关闭全部。
import { type CSSProperties } from 'vue'

import type { TabNavItem } from '../../composables/useTabNav'

import { useBaseLayout } from '../../composables/useBaseLayout'

/** 菜单动作。 */
export type TabNavAction = 'refresh' | 'close' | 'close-others' | 'close-right' | 'close-all'

interface Props {
  /** 显隐。 */
  visible: boolean
  /** 定位 X。 */
  x?: number
  /** 定位 Y。 */
  y?: number
  /** 目标页签。 */
  item?: TabNavItem
}

const props = withDefaults(defineProps<Props>(), { x: 0, y: 0, item: undefined })
const emit = defineEmits<{ action: [action: TabNavAction] }>()

const { hidden } = useBaseLayout()

const ACTIONS: { key: TabNavAction; label: string }[] = [
  { key: 'refresh', label: '刷新' },
  { key: 'close', label: '关闭' },
  { key: 'close-others', label: '关闭其他' },
  { key: 'close-right', label: '关闭右侧' },
  { key: 'close-all', label: '关闭全部' },
]

function style(): CSSProperties {
  return { left: `${props.x}px`, top: `${props.y}px` }
}
</script>

<template>
  <div v-if="visible" v-show="!hidden" class="bms-tab-nav-context" data-test="tab-context" :style="style()">
    <button
      v-for="action in ACTIONS"
      :key="action.key"
      class="bms-tab-nav-context__item"
      :data-test="`tab-ctx-${action.key}`"
      :disabled="action.key !== 'refresh' && item?.closable === false"
      @click="emit('action', action.key)"
    >
      {{ action.label }}
    </button>
  </div>
</template>

<style scoped>
.bms-tab-nav-context {
  position: fixed;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  min-width: 140px;
  padding: var(--bms-space-1);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  box-shadow: var(--bms-shadow-md);
}

.bms-tab-nav-context__item {
  padding: var(--bms-space-2) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text);
  text-align: left;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--bms-radius-sm);
}

.bms-tab-nav-context__item:hover:not(:disabled) {
  color: var(--bms-color-primary);
  background: var(--bms-color-fill);
}

.bms-tab-nav-context__item:disabled {
  color: var(--bms-color-text-secondary);
  cursor: not-allowed;
}
</style>
