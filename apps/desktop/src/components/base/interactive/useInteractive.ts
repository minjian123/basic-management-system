/**
 * 交互片段（`interactive`）：可交互组件的公共行为。
 *
 * 契约见《组件设计 · 交互片段》：点击 / 键盘触发、`loading` / `disabled`、防抖、危险确认与埋点。
 * 片段不含具体视觉；危险确认只给「是否放行」判定（暂存待确认处理器），弹窗由容器组件承担。
 */

import { computed, ref, toValue, type MaybeRefOrGetter, type Ref } from 'vue'

import { declareFragment } from '../fragments'

/** 交互片段参数 */
export interface UseInteractiveOptions {
  loading?: MaybeRefOrGetter<boolean>
  disabled?: MaybeRefOrGetter<boolean>
  /** 防抖窗口（毫秒）；`0` 表示不防抖 */
  debounce?: MaybeRefOrGetter<number>
  /** 危险操作需二次确认（放行前暂存处理器，由容器组件确认后调 `confirm()`） */
  dangerConfirm?: MaybeRefOrGetter<boolean>
  /** 埋点回调（判定事件类型；宿主接入埋点通道） */
  onTrack?: (event: 'click' | 'confirm' | 'cancel', meta?: Record<string, unknown>) => void
}

/** 交互片段返回值 */
export interface UseInteractiveReturn {
  /** 是否可交互（非 loading、非 disabled） */
  readonly isInteractive: boolean
  readonly isLoading: boolean
  readonly isDisabled: boolean
  /** 是否需要危险确认 */
  readonly needConfirm: boolean
  /** 触发（防抖、禁用拦截与危险确认拦截）；返回是否**已执行** */
  trigger: (handler: () => void, meta?: Record<string, unknown>) => boolean
  /** 危险确认通过：执行暂存的处理器 */
  confirm: (meta?: Record<string, unknown>) => void
  /** 放弃：清空暂存处理器 */
  cancel: () => void
  /** 暂存待确认的处理器（容器组件读取以决定弹窗文案） */
  readonly pendingHandler: Ref<(() => void) | undefined>
}

const ACTIVATION_KEYS = new Set(['Enter', ' ', 'Spacebar'])

/** 键盘激活判定（Enter / Space 视为激活；返回是否属于激活键） */
export function isActivationKey(key: string): boolean {
  return ACTIVATION_KEYS.has(key)
}

/**
 * 获取交互能力。
 *
 * 用法：`const { trigger, isInteractive } = useInteractive({ loading })`；宿主把 `trigger` 挂到点击事件，
 * 危险确认开启时先拦截，确认后调用 `confirm()` 继续。
 */
export function useInteractive(options: UseInteractiveOptions = {}): UseInteractiveReturn {
  declareFragment('interactive')

  const pendingHandler = ref<(() => void) | undefined>(undefined)
  const lastTriggeredAt = ref(0)

  const isLoading = computed(() => Boolean(toValue(options.loading)))
  const isDisabled = computed(() => Boolean(toValue(options.disabled)))
  const isInteractive = computed(() => !isLoading.value && !isDisabled.value)
  const needConfirm = computed(() => Boolean(toValue(options.dangerConfirm)))

  const trigger = (handler: () => void, meta?: Record<string, unknown>): boolean => {
    if (!isInteractive.value) {
      return false
    }
    const window = Number(toValue(options.debounce) ?? 0)
    const now = Date.now()
    if (window > 0 && now - lastTriggeredAt.value < window) {
      return false
    }
    lastTriggeredAt.value = now
    if (needConfirm.value) {
      pendingHandler.value = handler
      options.onTrack?.('confirm', meta)
      return false
    }
    handler()
    options.onTrack?.('click', meta)
    return true
  }

  const confirm = (meta?: Record<string, unknown>): void => {
    const handler = pendingHandler.value
    pendingHandler.value = undefined
    if (!handler) {
      return
    }
    handler()
    options.onTrack?.('click', meta)
  }

  const cancel = (): void => {
    pendingHandler.value = undefined
    options.onTrack?.('cancel')
  }

  return {
    get isInteractive() {
      return isInteractive.value
    },
    get isLoading() {
      return isLoading.value
    },
    get isDisabled() {
      return isDisabled.value
    },
    get needConfirm() {
      return needConfirm.value
    },
    trigger,
    confirm,
    cancel,
    pendingHandler,
  }
}
