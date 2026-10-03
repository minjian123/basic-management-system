/** 扫码登录投影：把核心扫码登录能力域基类 `BaseSsoQr` 投影为组合式（相位 / 授权 URL / 轮询 / 过期 / 可见性）。 */

import {
  BaseSsoQr,
  isSsoQrTerminal,
  type SsoQrLoginSourceAdapter,
  type SsoQrPhase,
  type SsoQrProviderLike,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体扫码登录能力（可实例化）。 */
class SsoQrState extends BaseSsoQr {}

/** `useBaseSsoQr` 选项。 */
export interface UseBaseSsoQrOptions {
  /** 数据通路是否就绪（缺省 true）。 */
  ready?: boolean
  /** 可扫码入口（原始清单，内部过滤）。 */
  providers?: readonly SsoQrProviderLike[]
  /** 状态源（未注入即占位零请求）。 */
  source?: SsoQrLoginSourceAdapter
  /** 租户编码。 */
  tenant?: string | null
  /** 轮询间隔基数（毫秒）。 */
  pollBase?: number
  /** 轮询退避上限（毫秒）。 */
  pollMax?: number
  /** 连续失败阈值。 */
  maxFailures?: number
  /** 页面隐藏时是否暂停轮询。 */
  pauseWhenHidden?: boolean
}

/** `useBaseSsoQr` 返回面。 */
export interface UseBaseSsoQrResult {
  /** 扫码登录能力实例。 */
  instance: BaseSsoQr
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 当前相位（响应式）。 */
  phase: Ref<SsoQrPhase>
  /** 相位文案（响应式）。 */
  statusText: ComputedRef<string>
  /** 授权 URL（响应式）。 */
  authorizeUrl: Ref<string>
  /** 可扫码入口（响应式）。 */
  providers: Ref<SsoQrProviderLike[]>
  /** 当前 IdP 标识（响应式）。 */
  activeIdpKey: Ref<string | null>
  /** 确认后的完成跳转地址（响应式）。 */
  redirect: Ref<string | undefined>
  /** 剩余有效期（秒，响应式）。 */
  remaining: Ref<number>
  /** 是否无可扫码入口（响应式）。 */
  empty: ComputedRef<boolean>
  /** 是否终态（响应式）。 */
  terminal: ComputedRef<boolean>
  /** 设置入口清单。 */
  setProviders(providers: readonly SsoQrProviderLike[]): void
  /** 切换当前入口。 */
  setActiveProvider(idpKey: string | null): void
  /** 注入 / 移除状态源。 */
  setSource(source: SsoQrLoginSourceAdapter | undefined): void
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 批量设置选项。 */
  setOptions(options: UseBaseSsoQrOptions): void
  /** 初始化（取授权 URL + 起轮询）。 */
  init(): Promise<void>
  /** 手动刷新。 */
  refresh(): void
  /** 暂停轮询。 */
  pause(): void
  /** 恢复轮询。 */
  resume(): void
}

/**
 * 使用扫码登录投影。
 *
 * @param options 选项。
 * @returns 扫码登录实例与响应式面。
 */
export function useBaseSsoQr(options: UseBaseSsoQrOptions = {}): UseBaseSsoQrResult {
  const instance = new SsoQrState()
  instance.setOptions({
    ...(options.pollBase === undefined ? {} : { pollBase: options.pollBase }),
    ...(options.pollMax === undefined ? {} : { pollMax: options.pollMax }),
    ...(options.maxFailures === undefined ? {} : { maxFailures: options.maxFailures }),
    ...(options.pauseWhenHidden === undefined ? {} : { pauseWhenHidden: options.pauseWhenHidden }),
  })
  instance.setTenant(options.tenant ?? null)
  if (options.ready !== undefined) {
    instance.setReady(options.ready)
  }
  if (options.source !== undefined) {
    instance.setSource(options.source)
  }
  if (options.providers !== undefined) {
    instance.setProviders(options.providers)
  }

  const ready = ref(instance.ready)
  const degraded = ref(instance.degraded)
  const phase = ref<SsoQrPhase>(instance.phase)
  const authorizeUrl = ref(instance.authorizeUrl)
  const providers = ref<SsoQrProviderLike[]>([...instance.providers])
  const activeIdpKey = ref<string | null>(instance.activeIdpKey)
  const redirect = ref<string | undefined>(instance.redirect)
  const remaining = ref(instance.remaining)

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    ready.value = instance.ready
    degraded.value = instance.degraded
    phase.value = instance.phase
    authorizeUrl.value = instance.authorizeUrl
    providers.value = [...instance.providers]
    activeIdpKey.value = instance.activeIdpKey
    redirect.value = instance.redirect
    remaining.value = instance.remaining
  }

  const off = instance.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  onScopeDispose(() => {
    off()
    instance.dispose()
  })

  const statusText = computed(() => instance.statusText)
  const empty = computed(() => providers.value.length === 0)
  const terminal = computed(() => isSsoQrTerminal(phase.value))

  return {
    instance,
    ready,
    degraded,
    phase,
    statusText,
    authorizeUrl,
    providers,
    activeIdpKey,
    redirect,
    remaining,
    empty,
    terminal,
    setProviders: (next) => {
      instance.setProviders(next)
      sync()
    },
    setActiveProvider: (next) => {
      instance.setActiveProvider(next)
      sync()
    },
    setSource: (next) => {
      instance.setSource(next)
      sync()
    },
    setReady: (next) => {
      instance.setReady(next)
      sync()
    },
    setOptions: (next) => {
      instance.setOptions({
        ...(next.pollBase === undefined ? {} : { pollBase: next.pollBase }),
        ...(next.pollMax === undefined ? {} : { pollMax: next.pollMax }),
        ...(next.maxFailures === undefined ? {} : { maxFailures: next.maxFailures }),
        ...(next.pauseWhenHidden === undefined ? {} : { pauseWhenHidden: next.pauseWhenHidden }),
      })
      sync()
    },
    init: () => instance.init(),
    refresh: () => instance.refresh(),
    pause: () => instance.pause(),
    resume: () => instance.resume(),
  }
}
