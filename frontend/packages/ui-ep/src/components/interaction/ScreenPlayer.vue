<script setup lang="ts">
// 大屏播放（占位版，08_01_03）：契约先行冻结；数据通路未就绪时不请求、控制禁用 + 降级提示。播放舞台独立分包懒加载。
import { computed, defineAsyncComponent, ref, watch } from 'vue'

import { useBaseAsyncTask } from '../../composables/useBaseAsyncTask'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 播放舞台独立分包（自适应缩放 / 轮播，真实实现 08_09 接入）。
const ScreenStage = defineAsyncComponent(() => import('./ScreenStage.vue'))

/** 大屏页。 */
export interface ScreenPlayerPage {
  /** 页标识。 */
  id: string
  /** 页名。 */
  name: string
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 大屏标识。 */
  screenCode?: string
  /** 多页。 */
  pages?: ScreenPlayerPage[]
  /** 当前页标识。 */
  activePageId?: string
  /** 当前页组件。 */
  components?: import('./ScreenDesigner.vue').ScreenComponent[]
  /** 轮播间隔（毫秒）。 */
  interval?: number
  /** 是否自动轮播。 */
  autoplay?: boolean
  /** 是否全屏。 */
  fullscreen?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  screenCode: '',
  pages: () => [],
  activePageId: '',
  components: () => [],
  interval: 0,
  autoplay: false,
  fullscreen: false,
  degradeText: '大屏播放未就绪（占位）',
})

const emit = defineEmits<{
  'update:activePageId': [pageId: string]
  next: []
  prev: []
  toggle: [playing: boolean]
  refresh: []
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { status, progress, submit } = useBaseAsyncTask<unknown>()
const playing = ref(props.autoplay)

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
  { immediate: true },
)

/** 是否禁用控制（占位）。 */
const controlDisabled = computed(() => placeholder.disabled.value)

/** 切换播放 / 暂停。 */
function toggle(): void {
  if (controlDisabled.value) {
    return
  }
  playing.value = !playing.value
  emit('toggle', playing.value)
}

/** 刷新当前页数据（占位经异步任务）。 */
function refresh(): void {
  if (controlDisabled.value) {
    return
  }
  void submit()
  emit('refresh')
}
</script>

<template>
  <div
    class="bms-screen-player"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
    :data-fullscreen="fullscreen"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-screen-player__controls" data-test="controls">
          <button type="button" data-test="prev" :disabled="controlDisabled" @click="emit('prev')">上一页</button>
          <button type="button" data-test="toggle" :disabled="controlDisabled" @click="toggle">
            {{ playing ? '暂停' : '播放' }}
          </button>
          <button type="button" data-test="next" :disabled="controlDisabled" @click="emit('next')">下一页</button>
          <button type="button" data-test="refresh" :disabled="controlDisabled" @click="refresh">刷新</button>
          <span data-test="task-status">{{ status }}</span>
          <span v-if="progress" data-test="task-progress">{{ progress.value }}</span>
        </div>
        <component :is="ScreenStage" :active-page-id="activePageId" :components="components" :playing="playing" :interval="interval" />
      </slot>
    </template>
  </div>
</template>
