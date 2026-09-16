<script setup lang="ts">
/**
 * 加载遮罩容器（《组件设计 · 加载遮罩容器》）：异步区域四态统一。
 *
 * - 四态互斥：`loading（延迟后）> error > empty > content`，仅当前态渲染；
 * - `delay` 防闪烁（快请求不显示加载态；显示后即时隐藏）；
 * - 内置轻量加载形态（双端同款零依赖）：`mask` / `skeleton` / `spin`；`#loading` 插槽可自定义；
 * - `empty` / `error` 以插槽为主（建议传入域 03 的 `EmptyState` / `ErrorPage` 获完整视觉），
 *   缺省最小文本；错误态内置重试按钮（点击自锁，`loading` 变化复位）；
 * - `minHeight` 缺省由样式覆盖点 `--bms-loading-min-height` 控制（不造正式令牌）。
 */

import { computed, onBeforeUnmount, ref, useAttrs, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useComponentBase } from '@bms/vue'

import { resolveSize } from './size'

const props = withDefaults(
  defineProps<{
    /** 加载中（经 `delay` 防闪烁后显示） */
    loading?: boolean
    /** 加载形态（内置实现） */
    mode?: 'mask' | 'skeleton' | 'spin'
    /** 延迟显示（ms；快请求不显示加载态） */
    delay?: number
    /** 空态 */
    empty?: boolean
    /** 错误信息（用户可读文本；缺省用 i18n） */
    error?: string | false
    /** 状态区最小高度（数字按 px）；缺省由 `--bms-loading-min-height` 控制 */
    minHeight?: number | string
  }>(),
  {
    loading: false,
    mode: 'mask',
    delay: 200,
    empty: false,
    error: false,
    minHeight: undefined,
  },
)

const emit = defineEmits<{
  retry: []
}>()

const { t } = useI18n()
const base = useComponentBase({ ns: 'bms', identifier: 'loading-container' })
const attrs = useAttrs()

const showLoading = ref(false)
let delayTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.loading,
  (next) => {
    if (delayTimer !== null) {
      clearTimeout(delayTimer)
      delayTimer = null
    }
    if (!next) {
      showLoading.value = false
      return
    }
    if (props.delay > 0) {
      delayTimer = setTimeout(() => {
        delayTimer = null
        showLoading.value = true
      }, props.delay)
    } else {
      showLoading.value = true
    }
  },
  { immediate: true },
)

const state = computed<'loading' | 'error' | 'empty' | 'content'>(() => {
  if (showLoading.value) {
    return 'loading'
  }
  if (props.error !== false) {
    return 'error'
  }
  if (props.empty) {
    return 'empty'
  }
  return 'content'
})

const errorText = computed(() =>
  typeof props.error === 'string' && props.error.length > 0 ? props.error : t('container.loadingFailed'),
)

/** 重试自锁（防重复点击；`loading` 变化复位） */
const retryLocked = ref(false)

watch(
  () => props.loading,
  (next) => {
    if (next) {
      retryLocked.value = false
    }
  },
)

function onRetry(): void {
  if (retryLocked.value) {
    return
  }
  retryLocked.value = true
  emit('retry')
}

const statusStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {}
  const minHeight = resolveSize(props.minHeight)
  if (minHeight) {
    style.minHeight = minHeight
  }
  return style
})

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [
      base.nsClass('loading-container'),
      base.nsClass(`loading-container--${state.value}`),
      cls,
    ],
    style: sty,
    ...rest,
  })
})

onBeforeUnmount(() => {
  if (delayTimer !== null) {
    clearTimeout(delayTimer)
    delayTimer = null
  }
})

defineExpose({
  get state(): 'loading' | 'error' | 'empty' | 'content' {
    return state.value
  },
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('loading-container')">
    <div
      v-if="state === 'loading'"
      :class="[base.nsClass('loading-container-status'), base.nsClass(`loading-container-status--${mode}`)]"
      :style="statusStyle"
      role="status"
      data-testid="loading-state"
    >
      <slot name="loading">
        <div
          v-if="mode === 'skeleton'"
          :class="base.nsClass('loading-container-skeleton')"
          aria-hidden="true"
        >
          <span />
          <span />
        </div>
        <div
          v-else-if="mode === 'spin'"
          :class="base.nsClass('loading-container-spin')"
          aria-hidden="true"
        />
        <div v-else :class="base.nsClass('loading-container-mask')" aria-hidden="true" />
      </slot>
    </div>

    <div
      v-else-if="state === 'error'"
      :class="base.nsClass('loading-container-status')"
      :style="statusStyle"
      role="alert"
      data-testid="error-state"
    >
      <slot name="error" :retry="onRetry" :message="errorText">
        <p :class="base.nsClass('loading-container-text')">{{ errorText }}</p>
        <button
          type="button"
          :class="base.nsClass('loading-container-retry')"
          :disabled="retryLocked"
          data-testid="retry-button"
          @click="onRetry"
        >
          {{ t('container.retry') }}
        </button>
      </slot>
    </div>

    <div
      v-else-if="state === 'empty'"
      :class="base.nsClass('loading-container-status')"
      :style="statusStyle"
      role="status"
      data-testid="empty-state"
    >
      <slot name="empty">
        <p :class="base.nsClass('loading-container-text')">{{ t('container.emptyText') }}</p>
      </slot>
    </div>

    <template v-else>
      <slot />
    </template>
  </div>
</template>

<style scoped>
.bms-loading-container-status {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bms-space-3);
  min-height: var(--bms-loading-min-height, 80px);
  padding: var(--bms-space-4);
}

.bms-loading-container-status--mask {
  background: color-mix(in srgb, var(--bms-color-bg-page) 72%, transparent);
}

.bms-loading-container-mask {
  width: 100%;
  min-height: 48px;
  border-radius: var(--bms-radius-sm);
  background: color-mix(in srgb, var(--bms-color-border) 28%, transparent);
}

.bms-loading-container-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  width: 100%;
}

.bms-loading-container-skeleton span {
  display: block;
  height: 12px;
  border-radius: var(--bms-radius-sm);
  background: linear-gradient(
    90deg,
    var(--bms-color-bg-page) 25%,
    var(--bms-color-border) 37%,
    var(--bms-color-bg-page) 63%
  );
  background-size: 400% 100%;
  animation: bms-loading-skeleton 1.4s ease infinite;
}

.bms-loading-container-skeleton span:last-child {
  width: 64%;
}

.bms-loading-container-spin {
  width: 24px;
  height: 24px;
  border: 2px solid var(--bms-color-border);
  border-top-color: var(--bms-color-primary);
  border-radius: 50%;
  animation: bms-loading-spin 0.8s linear infinite;
}

.bms-loading-container-text {
  margin: 0;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.bms-loading-container-retry {
  padding: var(--bms-space-1) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-primary);
  background: transparent;
  border: 1px solid var(--bms-color-primary);
  border-radius: var(--bms-radius-sm);
  cursor: pointer;
}

.bms-loading-container-retry:hover:not(:disabled) {
  color: var(--bms-color-bg);
  background: var(--bms-color-primary);
}

.bms-loading-container-retry:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@keyframes bms-loading-skeleton {
  0% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0 50%;
  }
}

@keyframes bms-loading-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
