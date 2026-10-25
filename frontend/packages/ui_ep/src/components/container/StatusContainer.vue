<script setup lang="ts">
// 四态容器：加载 / 就绪 / 空 / 错误受控承载（延迟防闪；空 / 错误可插槽组合 `03_02` 件）。
import { ElButton } from 'element-plus'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useBaseContainer } from '../../composables/useBaseContainer'
import { useFeedback } from '../../composables/useFeedback'
import SkeletonBlock from '../feedback/SkeletonBlock.vue'

/** 四态。 */
export type StatusContainerState = 'loading' | 'ready' | 'empty' | 'error'

/** 加载形态。 */
export type StatusContainerVariant = 'mask' | 'skeleton' | 'spin'

interface Props {
  /** 状态（受控）。 */
  status: StatusContainerState
  /** 加载形态（遮罩 / 骨架 / 旋转）。 */
  variant?: StatusContainerVariant
  /** 加载态延迟显示（毫秒，防闪烁）。 */
  delay?: number
  /** 加载文案。 */
  text?: string
  /** 空态文案（缺省内置轻量形态）。 */
  emptyText?: string
  /** 错误态文案（缺省内置轻量形态）。 */
  errorText?: string
  /** 错误态是否显示重试。 */
  retryable?: boolean
  /** 非就绪态是否保留内容挂载（保状态）。 */
  keepContent?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'mask',
  delay: 200,
  text: '加载中…',
  emptyText: '暂无数据',
  errorText: '加载失败',
  retryable: false,
  keepContent: false,
})

const emit = defineEmits<{ retry: []; 'status-change': [status: StatusContainerState] }>()

const { sizeToken, isCompact } = useBaseContainer()
const { begin, ready, empty, error } = useFeedback()

const showLoading = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function clearTimer(): void {
  if (timer !== undefined) {
    clearTimeout(timer)
    timer = undefined
  }
}

function syncFeedback(status: StatusContainerState): void {
  if (status === 'loading') {
    begin()
  } else if (status === 'empty') {
    empty()
  } else if (status === 'error') {
    error()
  } else {
    ready()
  }
}

/** 生效状态（延迟内转就绪则不显示加载态）。 */
const resolved = computed<StatusContainerState>(() =>
  props.status === 'loading' && !showLoading.value ? 'ready' : props.status,
)

watch(
  () => props.status,
  (status) => {
    syncFeedback(status)
    clearTimer()
    if (status !== 'loading') {
      showLoading.value = false
    } else if (props.delay <= 0) {
      showLoading.value = true
    } else {
      timer = setTimeout(() => {
        showLoading.value = true
      }, props.delay)
    }
    emit('status-change', status)
  },
  { immediate: true },
)

onBeforeUnmount(clearTimer)
</script>

<template>
  <div
    class="bms-status-container"
    :data-status="resolved"
    :data-variant="variant"
    :data-size="sizeToken"
    :data-density="isCompact ? 'compact' : 'default'"
  >
    <div
      v-if="keepContent || resolved === 'ready'"
      v-show="resolved === 'ready'"
      class="bms-status-container__content"
    >
      <slot />
    </div>

    <div
      v-if="resolved === 'loading'"
      class="bms-status-container__state"
      :class="`is-${variant}`"
      data-test="status-loading"
    >
      <slot name="loading">
        <slot v-if="variant === 'skeleton'" name="skeleton">
          <skeleton-block variant="list" :rows="3" />
        </slot>
        <span v-else-if="variant === 'spin'" class="bms-status-container__spinner" aria-hidden="true" />
        <span v-else class="bms-status-container__text">{{ text }}</span>
      </slot>
    </div>

    <div v-else-if="resolved === 'empty'" class="bms-status-container__state" data-test="status-empty">
      <slot name="empty">
        <span class="bms-status-container__text">{{ emptyText }}</span>
      </slot>
    </div>

    <div v-else-if="resolved === 'error'" class="bms-status-container__state" data-test="status-error">
      <slot name="error">
        <span class="bms-status-container__text">{{ errorText }}</span>
      </slot>
      <div class="bms-status-container__actions">
        <el-button v-if="retryable" data-test="status-retry" type="primary" @click="emit('retry')">重试</el-button>
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.bms-status-container {
  position: relative;
  box-sizing: border-box;
  min-height: var(--bms-loading-min-height, 120px);
}

.bms-status-container__content {
  color: var(--bms-color-text);
}

.bms-status-container__state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-4);
  color: var(--bms-color-text-secondary);
}

.bms-status-container__state.is-mask {
  position: absolute;
  inset: 0;
  background: var(--bms-color-mask-bg);
  border-radius: var(--bms-radius-md);
}

.bms-status-container__text {
  font-size: var(--bms-font-size-sm);
}

.bms-status-container__spinner {
  display: block;
  width: 20px;
  height: 20px;
  border: 2px solid var(--bms-color-border);
  border-top-color: var(--bms-color-primary);
  border-radius: 50%;
  animation: bms-status-spin 0.8s linear infinite;
}

.bms-status-container__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--bms-space-2);
}

@keyframes bms-status-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

