<script setup lang="ts">
// 全屏容器：全屏展示（Esc 退出 / 状态同步），能力缺失降级视口铺满；首次进入显示退出提示。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'
import { canFullscreen, enterFullscreen, exitFullscreen, fullscreenElement, isFullscreen, onFullscreenChange } from '../../utils/fullscreen'
import { onGlobalKeydown } from '../../utils/keyboard'

/** 提示自动隐藏时长（毫秒）。 */
const HINT_DURATION = 3000

interface Props {
  /** 全屏态（`v-model`）。 */
  modelValue?: boolean
  /** 全屏目标（缺省容器自身）。 */
  target?: HTMLElement
  /** 进入全屏后是否显示退出提示。 */
  showHint?: boolean
  /** 退出提示文案。 */
  hint?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  target: undefined,
  showHint: true,
  hint: '按 Esc 退出全屏',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
  error: [reason: string]
}>()

const { sizeToken, isCompact } = useBaseContainer()
const root = ref<HTMLElement>()
const active = ref(props.modelValue ?? false)
const degraded = ref(false)
const hintVisible = ref(false)
let offFullscreen: () => void = () => {}
let offKeydown: () => void = () => {}
let hintTimer: ReturnType<typeof setTimeout> | undefined

function resolveTarget(): HTMLElement | undefined {
  return props.target ?? root.value
}

/** 清理提示定时器。 */
function clearHintTimer(): void {
  if (hintTimer !== undefined) {
    clearTimeout(hintTimer)
    hintTimer = undefined
  }
}

/** 显示退出提示并在时长后自动隐藏。 */
function showHintBar(): void {
  if (!props.showHint) {
    return
  }
  hintVisible.value = true
  clearHintTimer()
  hintTimer = setTimeout(() => {
    hintVisible.value = false
    hintTimer = undefined
  }, HINT_DURATION)
}

/** 手动关闭提示。 */
function dismissHint(): void {
  clearHintTimer()
  hintVisible.value = false
}

function setActive(value: boolean): void {
  if (active.value === value) {
    return
  }
  active.value = value
  if (value) {
    showHintBar()
  } else {
    dismissHint()
  }
  emit('update:modelValue', value)
  emit('change', value)
}

async function enter(): Promise<void> {
  const element = resolveTarget()
  if (element === undefined || !canFullscreen(element)) {
    degraded.value = true
    setActive(true)
    emit('error', 'unsupported')
    return
  }
  try {
    await enterFullscreen(element)
    setActive(true)
  } catch {
    degraded.value = true
    setActive(true)
    emit('error', 'rejected')
  }
}

async function exit(): Promise<void> {
  if (!degraded.value && isFullscreen()) {
    await exitFullscreen()
  }
  setActive(false)
}

function onFullscreenChangeEvent(): void {
  if (degraded.value) {
    return
  }
  setActive(isFullscreen() && fullscreenElement() === resolveTarget())
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && active.value) {
    void exit()
  }
}

watch(
  () => props.modelValue,
  (value) => {
    if (value === undefined) {
      return
    }
    if (value && !active.value) {
      void enter()
    } else if (!value && active.value) {
      void exit()
    }
  },
)

onMounted(() => {
  offFullscreen = onFullscreenChange(onFullscreenChangeEvent)
  offKeydown = onGlobalKeydown(onKeydown)
})

onBeforeUnmount(() => {
  offFullscreen()
  offKeydown()
  clearHintTimer()
})
</script>

<template>
  <div
    ref="root"
    class="bms-fullscreen-container"
    :class="{ 'is-active': active, 'is-degraded': degraded }"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
  >
    <slot />
    <div
      v-if="hintVisible"
      class="bms-fullscreen-container__hint"
      data-test="fullscreen-hint"
      @click="dismissHint"
    >
      <slot name="hint">{{ hint }}</slot>
    </div>
  </div>
</template>

<style scoped>
.bms-fullscreen-container {
  position: relative;
  box-sizing: border-box;
  overflow: auto;
  background: var(--bms-fullscreen-bg);
}

.bms-fullscreen-container:fullscreen {
  width: 100%;
  height: 100%;
  background: var(--bms-fullscreen-bg);
}

.bms-fullscreen-container.is-degraded {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: var(--bms-fullscreen-bg);
}

.bms-fullscreen-container__hint {
  position: absolute;
  top: var(--bms-space-4);
  left: 50%;
  z-index: 10;
  padding: var(--bms-space-1) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text);
  cursor: pointer;
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  box-shadow: var(--bms-shadow-sm);
  transform: translateX(-50%);
}
</style>
