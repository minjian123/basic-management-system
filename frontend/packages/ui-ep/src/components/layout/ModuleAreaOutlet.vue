<script setup lang="ts">
// 模块区域插槽：按区域标识渲染注册表中该区域的模块项（只读消费；空区域渲染为空，不兜底）。
import type { FrontendRegistries } from '@bms/core'

import { useModuleArea } from '../../composables/useModuleArea'

interface Props {
  /** 区域标识（点分，如 `layout.header`）。 */
  area: string
  /** 宿主注册表集合。 */
  registries: FrontendRegistries
  /** 装配版本号（装配 / 释放后自增，用于重算）。 */
  revision?: number
}

const props = withDefaults(defineProps<Props>(), { revision: 0 })

const { hidden, items, resolve } = useModuleArea({
  area: () => props.area,
  registries: props.registries,
  revision: () => props.revision,
})
</script>

<template>
  <div v-show="!hidden" class="bms-module-area-outlet" :data-area="area">
    <component :is="resolve(item.component)" v-for="item in items" :key="item.key" />
  </div>
</template>

<style scoped>
.bms-module-area-outlet {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm, 4px);
  min-width: 0;
}
</style>
