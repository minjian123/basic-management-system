<script setup lang="ts">
// 大屏播放（08_09_02）：控制条 + 多页圆点 + 自适应舞台；多页轮播（定时 / 手动 / 暂停）、按组件取数与刷新。
// 对外契约保持 08_01_03 冻结形状（导出名 / 既有 Props / 事件 / 插槽 / data-test / 分包入口不变），仅向后兼容新增可选项。
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { BaseAccess, BaseNotice, ChartDatasetResult, ReportDataset, ScreenCanvasConfig, ScreenComponent, ScreenPlayerJobs } from '@bms/core'

import { useBaseAsyncTask } from '../../composables/useBaseAsyncTask'
import { useBaseScreenPlayer } from '../../composables/useBaseScreenPlayer'

// 播放舞台独立分包（自适应缩放 / 轮播渲染）。
const ScreenStage = defineAsyncComponent(() => import('./ScreenStage.vue'))

/** 大屏页。 */
export interface ScreenPlayerPage {
  /** 页标识。 */
  id: string
  /** 页名。 */
  name: string
  /** 单页停留时长（毫秒，可选）。 */
  duration?: number
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
  components?: ScreenComponent[]
  /** 轮播间隔（毫秒）。 */
  interval?: number
  /** 是否自动轮播。 */
  autoplay?: boolean
  /** 是否全屏。 */
  fullscreen?: boolean
  /** 降级文案。 */
  degradeText?: string
  /** 画布配置。 */
  canvas?: ScreenCanvasConfig
  /** 数据集（组件渲染用）。 */
  datasets?: ReportDataset[]
  /** 注入处理函数集（注入后驱动真实编排）。 */
  jobs?: ScreenPlayerJobs
  /** 权限上下文。 */
  access?: BaseAccess
  /** 提示通知。 */
  notice?: BaseNotice
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
  canvas: undefined,
  datasets: () => [],
  jobs: undefined,
  access: undefined,
  notice: undefined,
})

const emit = defineEmits<{
  'update:activePageId': [pageId: string]
  next: []
  prev: []
  toggle: [playing: boolean]
  refresh: []
  retry: []
  loaded: []
  failed: [{ message: string }]
  'page-change': [{ pageId: string }]
  'data-refresh': [{ pageId: string; count: number }]
}>()

const player = useBaseScreenPlayer({
  ready: props.ready,
  screenCode: props.screenCode,
  pages: props.pages,
  activePageId: props.activePageId,
  componentsByPage: props.pages.length > 0 ? { [props.activePageId]: props.components } : undefined,
  autoplay: props.autoplay,
  interval: props.interval,
  fullscreen: props.fullscreen,
  canvas: props.canvas,
  jobs: props.jobs,
  access: props.access,
  notice: props.notice,
})

const { status, progress, submit } = useBaseAsyncTask<unknown>()
/** 本地播放态（未注入处理函数时受控）。 */
const localPlaying = ref(props.autoplay)
/** 轮播计时器。 */
let timer: ReturnType<typeof setTimeout> | undefined

/** 是否注入处理函数（事件与注入双轨）。 */
const hasJobs = computed(() => props.jobs !== undefined)
/** 生效页清单。 */
const pageList = computed(() => (hasJobs.value ? player.pages.value : props.pages))
/** 生效当前页标识。 */
const activeValue = computed(() => (hasJobs.value ? player.activePageId.value : props.activePageId))
/** 生效当前页组件。 */
const currentComponents = computed<ScreenComponent[]>(() => (hasJobs.value ? player.components.value : props.components))
/** 生效播放态。 */
const playing = computed(() => (hasJobs.value ? player.playing.value : localPlaying.value))
/** 生效全屏态。 */
const isFullscreen = computed(() => (hasJobs.value ? player.fullscreen.value : props.fullscreen))
/** 各组件取数结果。 */
const dataMap = computed<Record<string, ChartDatasetResult>>(() => player.data.value as unknown as Record<string, ChartDatasetResult>)
/** 是否禁用控制（占位）。 */
const controlDisabled = computed(() => player.degraded.value)

watch(
  () => props.ready,
  (value) => player.setReady(value),
)
watch(
  () => props.pages,
  (value) => player.setPages(value),
)

/** 当前页生效停留时长。 */
const stay = computed(() => {
  const page = pageList.value.find((item) => item.id === activeValue.value)
  const fallback = props.interval > 0 ? props.interval : 5000
  return page?.duration !== undefined ? Math.max(1000, page.duration) : Math.max(1000, fallback)
})

/** 清理计时器。 */
function clearTimer(): void {
  if (timer !== undefined) {
    clearTimeout(timer)
    timer = undefined
  }
}

/** 安排下一次轮播。 */
function schedule(): void {
  clearTimer()
  if (!playing.value || pageList.value.length <= 1) {
    return
  }
  timer = setTimeout(() => {
    onNext()
  }, stay.value)
}

watch([playing, activeValue, stay], () => {
  if (playing.value) {
    schedule()
  } else {
    clearTimer()
  }
})

/** 页面可见性变化（不可见暂停调度）。 */
function onVisibility(): void {
  if (typeof document !== 'undefined' && document.hidden) {
    clearTimer()
  } else {
    schedule()
  }
}

/** 下一页。 */
function onNext(): void {
  if (hasJobs.value) {
    player.next()
    schedule()
    emit('page-change', { pageId: player.activePageId.value })
  } else {
    emit('next')
  }
}

/** 上一页。 */
function onPrev(): void {
  if (hasJobs.value) {
    player.prev()
    schedule()
    emit('page-change', { pageId: player.activePageId.value })
  } else {
    emit('prev')
  }
}

/** 切换播放 / 暂停。 */
function onToggle(): void {
  if (hasJobs.value) {
    const next = player.toggle()
    emit('toggle', next)
  } else {
    localPlaying.value = !localPlaying.value
    emit('toggle', localPlaying.value)
  }
}

/** 刷新当前页数据。 */
function onRefresh(): void {
  void submit()
  emit('refresh')
  if (hasJobs.value) {
    void player.refreshPage().then((count) => {
      emit('data-refresh', { pageId: player.activePageId.value, count })
    })
  }
}

/**
 * 切页（圆点）。
 *
 * @param pageId 页标识。
 */
function onDot(pageId: string): void {
  if (hasJobs.value) {
    player.selectPage(pageId)
    schedule()
  }
  emit('update:activePageId', pageId)
  emit('page-change', { pageId })
}

/** 全屏切换（浏览器支持时）。 */
function toggleFullscreen(): void {
  if (typeof document === 'undefined') {
    return
  }
  if (document.fullscreenElement === null) {
    void document.documentElement.requestFullscreen?.()
  } else {
    void document.exitFullscreen?.()
  }
}

onMounted(() => {
  if (hasJobs.value) {
    void player.load().then((snapshot) => {
      if (snapshot !== undefined) {
        emit('loaded')
      } else {
        emit('failed', { message: player.errorMessage.value })
      }
    })
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibility)
  }
  schedule()
})

onBeforeUnmount(() => {
  clearTimer()
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', onVisibility)
  }
})
</script>

<template>
  <div
    class="bms-screen-player"
    :data-ready="player.ready.value"
    :data-degraded="player.degraded.value"
    :data-fullscreen="isFullscreen"
  >
    <slot v-if="player.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-screen-player__controls" data-test="controls">
          <span data-test="screen-code">{{ player.player.screenCode !== '' ? player.player.screenCode : screenCode }}</span>
          <button type="button" data-test="prev" :disabled="controlDisabled" @click="onPrev">上一页</button>
          <button type="button" data-test="toggle" :disabled="controlDisabled" @click="onToggle">
            {{ playing ? '暂停' : '播放' }}
          </button>
          <button type="button" data-test="next" :disabled="controlDisabled" @click="onNext">下一页</button>
          <button type="button" data-test="refresh" :disabled="controlDisabled" @click="onRefresh">刷新</button>
          <button type="button" data-test="fullscreen" @click="toggleFullscreen">全屏</button>
          <span data-test="task-status">{{ status }}</span>
          <span v-if="progress" data-test="task-progress">{{ progress.value }}</span>
          <slot name="toolbar" />
        </div>
        <div class="bms-screen-player__dots" data-test="page-dots">
          <button
            v-for="page in pageList"
            :key="page.id"
            type="button"
            :data-test="`dot-${page.id}`"
            :data-active="page.id === activeValue || undefined"
            @click="onDot(page.id)"
          >
            {{ page.name }}
          </button>
        </div>
        <component
          :is="ScreenStage"
          :active-page-id="activeValue"
          :components="currentComponents"
          :playing="playing"
          :interval="stay"
          :canvas="player.canvas.value"
          :datasets="datasets"
          :data="dataMap"
        />
      </slot>
    </template>
  </div>
</template>

<style scoped>
.bms-screen-player {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 360px;
}
.bms-screen-player__controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
}
.bms-screen-player__dots {
  display: flex;
  gap: 6px;
  padding: 0 6px 6px;
}
.bms-screen-player__dots button[data-active='true'] {
  color: var(--bms-color-primary, #409eff);
}
</style>
