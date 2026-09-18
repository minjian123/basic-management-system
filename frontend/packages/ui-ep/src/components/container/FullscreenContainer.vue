<script setup lang="ts">
// 全屏容器：全屏展示（Esc 退出 / 状态同步），能力缺失降级视口铺满。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'

interface Props {
  /** 全屏态（`v-model`）。 */
  modelValue?: boolean
  /** 全屏目标（缺省容器自身）。 */
  target?: HTMLElement
}

const props = withDefaults(defineProps<Props>(), { modelValue: undefined, target: undefined })

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  change: [value: boolean]
  error: [reason: string]
}>()

const { sizeToken, isCompact } = useBaseContainer()
const root = ref<HTMLElement>()
const active = ref(props.modelValue ?? false)
const degraded = ref(false)

function resolveTarget(): HTMLElement | undefined {
  return props.target ?? root.value
}

function setActive(value: boolean): void {
  if (active.value === value) {
    return
  }
  active.value = value
  emit('update:modelValue', value)
  emit('change', value)
}

async function enter(): Promise<void> {
  const element = resolveTarget()
  if (element === undefined || typeof element.requestFullscreen !== 'function') {
    degraded.value = true
    setActive(true)
    emit('error', 'unsupported')
    return
  }
  try {
    await element.requestFullscreen()
    setActive(true)
  } catch {
    degraded.value = true
    setActive(true)
    emit('error', 'rejected')
  }
}

async function exit(): Promise<void> {
  if (!degraded.value && typeof document !== 'undefined' && document.fullscreenElement != null && typeof document.exitFullscreen === 'function') {
    await document.exitFullscreen()
  }
  setActive(false)
}

function onFullscreenChange(): void {
  if (degraded.value) {
    return
  }
  setActive(typeof document !== 'undefined' && document.fullscreenElement != null && document.fullscreenElement === resolveTarget())
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
  document.addEventListener('fullscreenchange', onFullscreenChange)
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  window.removeEventListener('keydown', onKeydown)
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
  </div>
</template>
