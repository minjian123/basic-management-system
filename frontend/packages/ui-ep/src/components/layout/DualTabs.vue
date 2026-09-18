<script setup lang="ts">
// 双层页签（表单框架）：上层业务分组，下层组内页签；下层切换不改上层。
import type { TabNavItem } from '../../composables/useTabNav'

import { useBaseLayout } from '../../composables/useBaseLayout'
import TabNavBar from './TabNavBar.vue'

interface Props {
  /** 上层页签。 */
  primary: TabNavItem[]
  /** 上层激活键。 */
  primaryKey: string
  /** 下层页签。 */
  secondary: TabNavItem[]
  /** 下层激活键。 */
  secondaryKey: string
}

defineProps<Props>()

const { hidden } = useBaseLayout()

const emit = defineEmits<{
  'update:primaryKey': [key: string]
  'update:secondaryKey': [key: string]
  select: [level: 'primary' | 'secondary', key: string]
}>()
</script>

<template>
  <div v-show="!hidden" class="bms-dual-tabs">
    <tab-nav-bar
      class="bms-dual-tabs__primary"
      :tabs="primary"
      :active-key="primaryKey"
      @select="emit('update:primaryKey', $event); emit('select', 'primary', $event)"
    />
    <tab-nav-bar
      class="bms-dual-tabs__secondary"
      :tabs="secondary"
      :active-key="secondaryKey"
      @select="emit('update:secondaryKey', $event); emit('select', 'secondary', $event)"
    />
  </div>
</template>
