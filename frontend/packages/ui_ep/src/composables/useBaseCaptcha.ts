/** 验证码投影：把核心验证码族组件基类 `BaseCaptcha` 投影为组合式（挑战 / 倒计时 / 校验 / 滑块轨迹 / 阈值联动）。 */

import {
  BaseCaptcha,
  type CaptchaKind,
  type CaptchaPhase,
  type CaptchaPolicy,
  type CaptchaScene,
  type CaptchaSliderParams,
  type CaptchaSourceAdapter,
  type CaptchaTracePoint,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef, type Ref } from 'vue'

/** 具体验证码族（可实例化）。 */
class CaptchaState extends BaseCaptcha {}

/** `useBaseCaptcha` 选项。 */
export interface UseBaseCaptchaOptions {
  /** 数据通路是否就绪（缺省 false）。 */
  ready?: boolean
  /** 形态（缺省 image）。 */
  kind?: CaptchaKind
  /** 使用场景（缺省 login）。 */
  scene?: CaptchaScene
  /** 初始值。 */
  value?: string
  /** 数据源（未注入即占位零请求）。 */
  source?: CaptchaSourceAdapter
  /** 短信目标手机号。 */
  phone?: string
  /** 重发冷却（秒）。 */
  cooldown?: number
  /** 连续失败计数。 */
  failCount?: number
  /** 失败阈值。 */
  failThreshold?: number
  /** 输入定长覆盖（0 按形态缺省）。 */
  inputLength?: number
  /** 父页面强制要求。 */
  required?: boolean
  /** 件级禁用。 */
  disabled?: boolean
  /** 外部直连图片地址。 */
  imageUrl?: string
}

/** `useBaseCaptcha` 返回面（与核心方法一一对应的响应式面）。 */
export interface UseBaseCaptchaResult {
  /** 验证码族实例。 */
  captcha: BaseCaptcha
  /** 是否就绪（响应式）。 */
  ready: Ref<boolean>
  /** 是否降级（占位）态（响应式）。 */
  degraded: Ref<boolean>
  /** 生效禁用（件级禁用 ∨ 占位，响应式）。 */
  disabled: ComputedRef<boolean>
  /** 请求计数（占位态保持 0）。 */
  requestCount: Ref<number>
  /** 受控值（响应式）。 */
  value: Ref<string | undefined>
  /** 形态（响应式）。 */
  kind: Ref<CaptchaKind>
  /** 使用场景（响应式）。 */
  scene: Ref<CaptchaScene>
  /** 挑战图片地址（响应式）。 */
  imageUrl: Ref<string>
  /** 挑战编号（响应式）。 */
  challengeId: Ref<string>
  /** 形态参数原始串（响应式）。 */
  payload: Ref<string>
  /** 滑块形态参数（响应式）。 */
  sliderParams: Ref<CaptchaSliderParams>
  /** 挑战阶段（响应式）。 */
  phase: Ref<CaptchaPhase>
  /** 倒计时剩余秒数（响应式）。 */
  countdown: Ref<number>
  /** 冷却配置（响应式）。 */
  cooldown: Ref<number>
  /** 是否发送中（响应式）。 */
  sending: Ref<boolean>
  /** 是否校验中（响应式）。 */
  verifying: Ref<boolean>
  /** 是否校验通过（响应式）。 */
  passed: Ref<boolean>
  /** 是否要求验证码（响应式）。 */
  needsChallenge: Ref<boolean>
  /** 脱敏目标（响应式）。 */
  maskedTarget: Ref<string>
  /** 输入最大长度（响应式）。 */
  inputMaxLength: Ref<number>
  /** 输入提示文案（响应式）。 */
  inputHint: Ref<string>
  /** 错误码（响应式）。 */
  errorCode: Ref<number | undefined>
  /** 错误文案（响应式）。 */
  errorMessage: Ref<string>
  /** 生效错误文案（响应式，输入校验优先）。 */
  errorText: Ref<string>
  /** 是否错误态（响应式）。 */
  error: Ref<boolean>
  /** 是否空态（响应式）。 */
  empty: Ref<boolean>
  /** 是否有挑战图片（响应式）。 */
  hasImage: Ref<boolean>
  /** 滑块轨迹点（响应式）。 */
  trace: Ref<CaptchaTracePoint[]>
  /** 场景策略（响应式）。 */
  policy: Ref<CaptchaPolicy | undefined>
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: CaptchaSourceAdapter | undefined): void
  /** 切换形态。 */
  setKind(kind: CaptchaKind): void
  /** 切换场景。 */
  setScene(scene: CaptchaScene): void
  /** 设置值（归一）。 */
  setValue(value: string | undefined): void
  /** 同步受控值（件层 `modelValue` 监听用）。 */
  syncValue(value: string | undefined): void
  /** 设置手机号。 */
  setPhone(phone: string): void
  /** 设置冷却。 */
  setCooldown(seconds: number): void
  /** 设置失败计数。 */
  setFailCount(count: number): void
  /** 设置父页面强制。 */
  setRequired(value: boolean): void
  /** 设置外部直连图片。 */
  setImageUrl(url: string): void
  /** 批量装配。 */
  setOptions(options: UseBaseCaptchaOptions): void
  /** 取场景策略（一次）。 */
  loadPolicy(): Promise<void>
  /** 获取挑战。 */
  loadChallenge(): Promise<boolean>
  /** 刷新挑战（一次性失效）。 */
  refresh(): Promise<boolean>
  /** 发送短信。 */
  sendSms(): Promise<boolean>
  /** 校验输入。 */
  verify(): Promise<boolean>
  /** 提交滑块轨迹。 */
  submitSlider(): Promise<boolean>
  /** 追加轨迹点。 */
  pushTrace(point: CaptchaTracePoint): void
  /** 清空轨迹。 */
  clearTrace(): void
  /** 启动倒计时。 */
  startCountdown(seconds?: number): void
  /** 停止倒计时定时器。 */
  stopCountdown(): void
  /** 倒计时步进。 */
  tickCountdown(): void
  /** 清挑战（一次性失效）。 */
  invalidate(): void
  /** 全量复位。 */
  reset(): void
  /** 清空输入。 */
  clearInput(): void
  /** 订阅值变更。 */
  onValueChange(listener: (value: string | undefined) => void): () => void
}

/**
 * 使用验证码投影。
 *
 * @param options 选项。
 * @returns 验证码族实例与响应式面。
 */
export function useBaseCaptcha(options: UseBaseCaptchaOptions = {}): UseBaseCaptchaResult {
  const captcha = new CaptchaState()
  const localDisabled = ref(options.disabled ?? false)

  captcha.setOptions({
    ready: options.ready ?? false,
    kind: options.kind ?? 'image',
    scene: options.scene ?? 'login',
    ...(options.source === undefined ? {} : { source: options.source }),
    ...(options.phone === undefined ? {} : { phone: options.phone }),
    ...(options.cooldown === undefined ? {} : { cooldown: options.cooldown }),
    ...(options.failCount === undefined ? {} : { failCount: options.failCount }),
    ...(options.failThreshold === undefined ? {} : { failThreshold: options.failThreshold }),
    ...(options.inputLength === undefined ? {} : { inputLength: options.inputLength }),
    ...(options.required === undefined ? {} : { required: options.required }),
    ...(options.imageUrl === undefined ? {} : { imageUrl: options.imageUrl }),
  })
  if (options.value !== undefined) {
    captcha.setValue(options.value)
  }

  const ready = ref(captcha.ready)
  const degraded = ref(captcha.degraded)
  const requestCount = ref(captcha.requestCount)
  const value = ref(captcha.value)
  const kind = ref<CaptchaKind>(captcha.kind)
  const scene = ref<CaptchaScene>(captcha.scene)
  const imageUrl = ref(captcha.imageUrl)
  const challengeId = ref(captcha.challengeId)
  const payload = ref(captcha.payload)
  const sliderParams = ref<CaptchaSliderParams>(captcha.sliderParams)
  const phase = ref<CaptchaPhase>(captcha.phase)
  const countdown = ref(captcha.countdown)
  const cooldown = ref(captcha.cooldown)
  const sending = ref(captcha.sending)
  const verifying = ref(captcha.verifying)
  const passed = ref(captcha.passed)
  const needsChallenge = ref(captcha.needsChallenge)
  const maskedTarget = ref(captcha.maskedTarget)
  const inputMaxLength = ref(captcha.inputMaxLength)
  const inputHint = ref(captcha.inputHint)
  const errorCode = ref(captcha.errorCode)
  const errorMessage = ref(captcha.errorMessage)
  const errorText = ref(captcha.errorText)
  const error = ref(captcha.error)
  const empty = ref(captcha.empty)
  const hasImage = ref(captcha.hasImage)
  const trace = ref<CaptchaTracePoint[]>([...captcha.trace])
  const policy = ref<CaptchaPolicy | undefined>(captcha.policyData)

  /** 同步核心实例状态到响应式面。 */
  function sync(): void {
    ready.value = captcha.ready
    degraded.value = captcha.degraded
    requestCount.value = captcha.requestCount
    value.value = captcha.value
    kind.value = captcha.kind
    scene.value = captcha.scene
    imageUrl.value = captcha.imageUrl
    challengeId.value = captcha.challengeId
    payload.value = captcha.payload
    sliderParams.value = captcha.sliderParams
    phase.value = captcha.phase
    countdown.value = captcha.countdown
    cooldown.value = captcha.cooldown
    sending.value = captcha.sending
    verifying.value = captcha.verifying
    passed.value = captcha.passed
    needsChallenge.value = captcha.needsChallenge
    maskedTarget.value = captcha.maskedTarget
    inputMaxLength.value = captcha.inputMaxLength
    inputHint.value = captcha.inputHint
    errorCode.value = captcha.errorCode
    errorMessage.value = captcha.errorMessage
    errorText.value = captcha.errorText
    error.value = captcha.error
    empty.value = captcha.empty
    hasImage.value = captcha.hasImage
    trace.value = [...captcha.trace]
    policy.value = captcha.policyData
  }

  const off = captcha.onLifecycle((event) => {
    if (event === 'update') {
      sync()
    }
  })
  const offValue = captcha.onChange(() => sync())
  onScopeDispose(() => {
    off()
    offValue()
    captcha.dispose()
  })

  const disabled = computed(() => localDisabled.value || !ready.value)

  const api: UseBaseCaptchaResult = {
    captcha,
    ready,
    degraded,
    disabled,
    requestCount,
    value,
    kind,
    scene,
    imageUrl,
    challengeId,
    payload,
    sliderParams,
    phase,
    countdown,
    cooldown,
    sending,
    verifying,
    passed,
    needsChallenge,
    maskedTarget,
    inputMaxLength,
    inputHint,
    errorCode,
    errorMessage,
    errorText,
    error,
    empty,
    hasImage,
    trace,
    policy,
    setReady: (next) => captcha.setReady(next),
    setSource: (next) => captcha.setSource(next),
    setKind: (next) => captcha.setKind(next),
    setScene: (next) => captcha.setScene(next),
    setValue: (next) => captcha.setValue(next),
    syncValue: (next) => {
      captcha.setValue(next)
      sync()
    },
    setPhone: (next) => captcha.setPhone(next),
    setCooldown: (next) => captcha.setCooldown(next),
    setFailCount: (next) => captcha.setFailCount(next),
    setRequired: (next) => captcha.setRequired(next),
    setImageUrl: (next) => captcha.setImageUrl(next),
    setOptions: (next) => {
      if (next.disabled !== undefined) {
        localDisabled.value = next.disabled
      }
      const { disabled: _disabled, value: initialValue, ...rest } = next
      void _disabled
      captcha.setOptions(rest)
      if (initialValue !== undefined) {
        captcha.setValue(initialValue)
      }
      sync()
    },
    loadPolicy: () => captcha.loadPolicy(),
    loadChallenge: () => captcha.loadChallenge(),
    refresh: () => captcha.refresh(),
    sendSms: () => captcha.sendSms(),
    verify: () => captcha.verify(),
    submitSlider: () => captcha.submitSlider(),
    pushTrace: (point) => captcha.pushTrace(point),
    clearTrace: () => captcha.clearTrace(),
    startCountdown: (seconds) => captcha.startCountdown(seconds),
    stopCountdown: () => captcha.stopCountdown(),
    tickCountdown: () => captcha.tickCountdown(),
    invalidate: () => captcha.invalidate(),
    reset: () => captcha.reset(),
    clearInput: () => captcha.clearInput(),
    onValueChange: (listener) => captcha.onChange(listener),
  }
  return api
}
