<script setup lang="ts">
// 播放舞台（占位，08_01_03）：由 ScreenPlayer 异步懒加载的独立分包入口，真实实现（08_09）承载自适应缩放与轮播渲染。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { ScreenComponent } from './ScreenDesigner.vue'

interface Props {
  /** 当前页标识。 */
  activePageId?: string
  /** 当前页组件。 */
  components?: ScreenComponent[]
  /** 是否播放中。 */
  playing?: boolean
  /** 轮播间隔（毫秒）。 */
  interval?: number
}

const props = withDefaults(defineProps<Props>(), {
  activePageId: '',
  components: () => [],
  playing: false,
  interval: 0,
})

const { state, setState } = useBaseDataState()
watch(
  () => props.components.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)
</script>

<template>
  <div
    class="bms-screen-stage"
    data-test="screen-stage"
    data-subpackage="screen-player"
    :data-state="state"
    :data-page="activePageId"
    :data-playing="playing"
    :data-interval="interval"
  >
    <p v-if="components.length === 0" data-test="stage-empty">当前页暂无组件（占位，真实实现按分辨率自适应播放）</p>
    <div v-for="item in components" :key="item.id" :data-test="`stage-${item.id}`" :data-type="item.type">
      {{ item.text || item.type }}
    </div>
  </div>
</template>
