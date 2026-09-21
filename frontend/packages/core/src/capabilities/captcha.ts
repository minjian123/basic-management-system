/**
 * 验证码族组件基类：图形 / 滑块 / 短信三形态的挑战获取与刷新、短信发送与倒计时、
 * 凭证校验与错误分类、滑块轨迹提交与失败复位、失败阈值联动与释放。
 *
 * 全链：`BaseComponent → BasePlaceholderState → BaseValue → BaseField → BaseInput → BaseCaptcha → 具体件`。
 * 数据通路经注入式 `CaptchaSourceAdapter`（可替换实现经 `CaptchaSourceRegistry` 登记），**未注入即占位零请求**；
 * 核心不依赖 Vue / DOM / 浏览器 API（倒计时定时器为环境级能力，随释放停表）。
 */

import { BaseInput } from './input'
import type { CaptchaSourceAdapter } from './captcha-source'
import {
  CAPTCHA_FAIL_THRESHOLD,
  CAPTCHA_IMAGE_MAX_LENGTH,
  CAPTCHA_LOAD_ERROR_TEXT,
  CAPTCHA_SEND_ERROR_TEXT,
  CAPTCHA_SMS_COOLDOWN,
  CAPTCHA_SMS_LENGTH,
  CAPTCHA_TTL,
  CAPTCHA_TRACE_MAX_POINTS,
  CAPTCHA_TRACE_MIN_POINTS,
  captchaImageUrl,
  captchaInputHint,
  checkCaptchaInput,
  clampCaptchaSeconds,
  isCaptchaErrorCode,
  maskCaptchaPhone,
  nextCountdown,
  normalizeCaptchaChallenge,
  normalizeCaptchaPhone,
  normalizeCaptchaPolicy,
  normalizeCaptchaTrace,
  parseCaptchaSliderParams,
  resolveCaptchaErrorText,
  shouldRequireCaptcha,
  type CaptchaChallenge,
  type CaptchaKind,
  type CaptchaPhase,
  type CaptchaPolicy,
  type CaptchaScene,
  type CaptchaSliderParams,
  type CaptchaTracePoint,
} from '../domain/captcha'

/** 验证码族批量装配选项（件层用；缺省项不覆盖）。 */
export interface CaptchaOptions {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 形态。 */
  kind?: CaptchaKind
  /** 使用场景。 */
  scene?: CaptchaScene
  /** 数据源（未注入即占位零请求）。 */
  source?: CaptchaSourceAdapter
  /** 短信目标手机号。 */
  phone?: string
  /** 重发冷却（秒）。 */
  cooldown?: number
  /** 有效期（秒）。 */
  ttl?: number
  /** 连续失败计数。 */
  failCount?: number
  /** 失败阈值。 */
  failThreshold?: number
  /** 输入定长覆盖（0 按形态缺省）。 */
  inputLength?: number
  /** 父页面强制要求。 */
  required?: boolean
  /** 外部直连图片地址。 */
  imageUrl?: string
}

/** 验证码族组件基类（抽象）。 */
export abstract class BaseCaptcha extends BaseInput<string> {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'captcha'
  /** 依赖登记。 */
  override readonly depends = ['input']
  /** 数据通路是否就绪（占位语义，缺省 `false`）。 */
  ready = false
  /** 形态。 */
  kind: CaptchaKind = 'image'
  /** 使用场景。 */
  scene: CaptchaScene = 'login'
  /** 当前挑战图片（data URL 或外部直连）。 */
  imageUrl = ''
  /** 挑战编号（一次性失效凭据）。 */
  challengeId = ''
  /** 形态参数原始串（滑块）。 */
  payload = ''
  /** 服务端脱敏目标（短信）。 */
  target = ''
  /** 短信目标原文（展示一律脱敏）。 */
  phone = ''
  /** 有效期（秒）。 */
  ttl: number = CAPTCHA_TTL
  /** 冷却时长配置（秒；可经 Props / 场景策略覆盖）。 */
  cooldown: number = CAPTCHA_SMS_COOLDOWN
  /** 活动倒计时剩余秒数。 */
  countdown = 0
  /** 连续失败计数（阈值联动；由父页面同步）。 */
  failCount = 0
  /** 失败阈值。 */
  failThreshold: number = CAPTCHA_FAIL_THRESHOLD
  /** 输入定长覆盖（0 按形态缺省：图形 4-6 / 短信 6）。 */
  inputLength = 0
  /** 父页面强制要求（与策略 / 阈值并集）。 */
  required = false
  /** 挑战生命周期阶段。 */
  phase: CaptchaPhase = 'idle'
  /** 是否发送中。 */
  sending = false
  /** 是否校验中。 */
  verifying = false
  /** 是否校验通过。 */
  passed = false
  /** 输入校验错误文案。 */
  inputError = ''
  /** 错误码。 */
  errorCode: number | undefined
  /** 错误文案。 */
  errorMessage = ''
  /** 场景策略（`loadPolicy` 归一结果）。 */
  policyData: CaptchaPolicy | undefined
  /** 滑块轨迹点（采样）。 */
  readonly trace: CaptchaTracePoint[] = []
  /** 验证码数据源（注入式；未注入即占位零请求）。 */
  source: CaptchaSourceAdapter | undefined

  /** 倒计时定时器（随释放停表）。 */
  #countdownTimer: ReturnType<typeof setInterval> | undefined
  /** 挑战请求序号（防旧响应覆盖）。 */
  #challengeSeq = 0
  /** 短信请求序号。 */
  #smsSeq = 0
  /** 校验请求序号。 */
  #verifySeq = 0
  /** 策略是否已加载（一次；场景 / 数据源变更后重置）。 */
  #policyLoaded = false

  /** 生效禁用（件级禁用 ∨ 占位）。 */
  get effectiveDisabled(): boolean {
    return this.disabled || !this.ready
  }

  /** 是否可获取挑战（就绪 ∧ 数据源覆写 `challenge`）。 */
  get canLoad(): boolean {
    return this.ready && typeof this.source?.challenge === 'function'
  }

  /** 是否可发送短信（就绪 ∧ 覆写 `sendSms` ∧ 手机号非空 ∧ 倒计时为 0 ∧ 非发送中）。 */
  get canSendSms(): boolean {
    return (
      this.ready &&
      typeof this.source?.sendSms === 'function' &&
      normalizeCaptchaPhone(this.phone) !== '' &&
      this.countdown === 0 &&
      !this.sending
    )
  }

  /** 是否可校验（就绪 ∧ 覆写 `verify` ∧ 有挑战编号 ∧ 非校验中）。 */
  get canVerify(): boolean {
    return (
      this.ready &&
      typeof this.source?.verify === 'function' &&
      this.challengeId !== '' &&
      !this.verifying
    )
  }

  /** 是否要求验证码（父页面强制 ∨ 策略强制 ∨ 失败达阈值）。 */
  get needsChallenge(): boolean {
    return this.required || this.policyData?.required === true || shouldRequireCaptcha(this.failCount, this.failThreshold)
  }

  /** 脱敏目标（服务端 `target` 优先，缺省本地脱敏；不原样回显手机号）。 */
  get maskedTarget(): string {
    if (this.target !== '') {
      return this.target
    }
    return maskCaptchaPhone(this.phone)
  }

  /** 输入最大长度（定长覆盖优先，否则按形态：短信 6 / 图形 6）。 */
  get inputMaxLength(): number {
    if (this.inputLength > 0) {
      return Math.floor(this.inputLength)
    }
    return this.kind === 'sms' ? CAPTCHA_SMS_LENGTH : CAPTCHA_IMAGE_MAX_LENGTH
  }

  /** 输入提示文案。 */
  get inputHint(): string {
    return captchaInputHint(this.kind, this.inputLength)
  }

  /** 错误文案（输入校验优先）。 */
  get errorText(): string {
    return this.inputError !== '' ? this.inputError : this.errorMessage
  }

  /** 是否错误态。 */
  get error(): boolean {
    return this.errorCode !== undefined || this.inputError !== ''
  }

  /** 是否空态（无挑战 ∧ 无错误 ∧ 非加载中）。 */
  get empty(): boolean {
    return this.challengeId === '' && this.imageUrl === '' && this.phase !== 'loading' && this.errorCode === undefined
  }

  /** 是否有挑战图片。 */
  get hasImage(): boolean {
    return this.imageUrl !== ''
  }

  /** 滑块交互是否可呈现（就绪且形态为滑块）。 */
  get sliderReady(): boolean {
    return this.kind === 'slider' && this.ready
  }

  /** 滑块形态参数（`payload` 解析结果）。 */
  get sliderParams(): CaptchaSliderParams {
    return parseCaptchaSliderParams(this.payload)
  }

  /** 是否图形形态。 */
  get isImage(): boolean {
    return this.kind === 'image'
  }

  /** 是否滑块形态。 */
  get isSlider(): boolean {
    return this.kind === 'slider'
  }

  /** 是否短信形态。 */
  get isSms(): boolean {
    return this.kind === 'sms'
  }

  /**
   * 注入 / 移除验证码数据源（移除即回落占位零请求；策略随数据源变更重取）。
   *
   * @param source 数据源适配器；`undefined` 表示移除。
   */
  setSource(source: CaptchaSourceAdapter | undefined): void {
    this.source = source
    this.#policyLoaded = false
    this.emitUpdate()
  }

  /**
   * 切换形态（清挑战 / 错误 / 轨迹 / 倒计时与通过态）。
   *
   * @param kind 形态。
   */
  setKind(kind: CaptchaKind): void {
    if (this.kind === kind) {
      return
    }
    this.kind = kind
    this.reset()
  }

  /**
   * 切换使用场景（清策略缓存，不自行取数）。
   *
   * @param scene 使用场景。
   */
  setScene(scene: CaptchaScene): void {
    if (this.scene === scene) {
      return
    }
    this.scene = scene
    this.#policyLoaded = false
    this.policyData = undefined
    this.emitUpdate()
  }

  /**
   * 设置短信目标手机号（归一写入）。
   *
   * @param phone 手机号。
   */
  setPhone(phone: string): void {
    this.phone = normalizeCaptchaPhone(phone)
    this.emitUpdate()
  }

  /**
   * 设置重发冷却（非法回落缺省 60s）。
   *
   * @param seconds 冷却秒数。
   */
  setCooldown(seconds: number): void {
    this.cooldown = clampCaptchaSeconds(seconds, CAPTCHA_SMS_COOLDOWN)
    this.emitUpdate()
  }

  /**
   * 设置连续失败计数（阈值联动）。
   *
   * @param count 失败计数。
   */
  setFailCount(count: number): void {
    const next = Number.isFinite(count) && count > 0 ? Math.floor(count) : 0
    if (this.failCount === next) {
      return
    }
    this.failCount = next
    this.emitUpdate()
  }

  /**
   * 设置父页面强制要求。
   *
   * @param value 是否强制。
   */
  setRequired(value: boolean): void {
    if (this.required === value) {
      return
    }
    this.required = value
    this.emitUpdate()
  }

  /**
   * 设置外部直连图片（不改变挑战编号；空串清除）。
   *
   * @param url 图片地址。
   */
  setImageUrl(url: string): void {
    this.imageUrl = captchaImageUrl(url)
    this.emitUpdate()
  }

  /**
   * 替换轨迹点序列（非法点剔除并受上限约束）。
   *
   * @param points 轨迹点。
   */
  setTrace(points: readonly CaptchaTracePoint[]): void {
    const next = normalizeCaptchaTrace(points).slice(0, CAPTCHA_TRACE_MAX_POINTS)
    this.trace.splice(0, this.trace.length, ...next)
    this.emitUpdate()
  }

  /**
   * 批量装配（仅覆盖显式传入项；合并为一次更新广播）。
   *
   * @param options 装配选项。
   */
  setOptions(options: CaptchaOptions): void {
    if (options.ready !== undefined) {
      this.ready = options.ready
    }
    if (options.kind !== undefined) {
      this.kind = options.kind
    }
    if (options.scene !== undefined) {
      this.scene = options.scene
    }
    if (options.source !== undefined) {
      this.source = options.source
      this.#policyLoaded = false
    }
    if (options.phone !== undefined) {
      this.phone = normalizeCaptchaPhone(options.phone)
    }
    if (options.cooldown !== undefined) {
      this.cooldown = clampCaptchaSeconds(options.cooldown, CAPTCHA_SMS_COOLDOWN)
    }
    if (options.ttl !== undefined) {
      this.ttl = clampCaptchaSeconds(options.ttl, CAPTCHA_TTL)
    }
    if (options.failCount !== undefined) {
      this.failCount = Number.isFinite(options.failCount) && options.failCount > 0 ? Math.floor(options.failCount) : 0
    }
    if (options.failThreshold !== undefined) {
      this.failThreshold = clampCaptchaSeconds(options.failThreshold, CAPTCHA_FAIL_THRESHOLD)
    }
    if (options.inputLength !== undefined) {
      this.inputLength = Number.isFinite(options.inputLength) && options.inputLength > 0 ? Math.floor(options.inputLength) : 0
    }
    if (options.required !== undefined) {
      this.required = options.required
    }
    if (options.imageUrl !== undefined) {
      this.imageUrl = captchaImageUrl(options.imageUrl)
    }
    this.emitUpdate()
  }

  /**
   * 设置值（清输入校验错误）。
   *
   * @param value 输入值。
   */
  override setValue(value: string | undefined): void {
    super.setValue(value)
    if (this.inputError !== '') {
      this.inputError = ''
      this.emitUpdate()
    }
  }

  /**
   * 取场景策略（一次；未就绪 / 未覆写即零请求）。
   *
   * @returns 无。
   */
  async loadPolicy(): Promise<void> {
    const source = this.source
    if (!this.ready || source === undefined || typeof source.policy !== 'function' || this.#policyLoaded) {
      return
    }
    this.markLoaded()
    try {
      const raw = await source.policy({ scene: this.scene })
      if (raw === undefined) {
        return
      }
      const policy = normalizeCaptchaPolicy(raw, this.scene)
      this.policyData = policy
      this.#policyLoaded = true
      if (policy.ttl > 0) {
        this.ttl = policy.ttl
      }
      // 显式 Props 覆盖优先：仅当仍为平台缺省值时采纳策略值
      if (policy.cooldown > 0 && this.cooldown === CAPTCHA_SMS_COOLDOWN) {
        this.cooldown = policy.cooldown
      }
      if (policy.failThreshold > 0 && this.failThreshold === CAPTCHA_FAIL_THRESHOLD) {
        this.failThreshold = policy.failThreshold
      }
      this.emitUpdate()
    } catch (error) {
      this.applyError(error, CAPTCHA_LOAD_ERROR_TEXT, 'BaseCaptcha.loadPolicy')
    }
  }

  /**
   * 获取挑战（图形 / 滑块；未就绪 / 未覆写即零请求）。
   *
   * @returns 是否成功落地挑战。
   */
  async loadChallenge(): Promise<boolean> {
    const source = this.source
    if (!this.canLoad || source === undefined) {
      return false
    }
    const token = (this.#challengeSeq += 1)
    this.markLoaded()
    this.phase = 'loading'
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw = await source.challenge?.({ scene: this.scene, kind: this.kind })
      if (token !== this.#challengeSeq) {
        return false
      }
      const challenge = normalizeCaptchaChallenge(raw, { scene: this.scene, kind: this.kind })
      if (challenge === undefined) {
        this.phase = 'failed'
        this.errorCode = undefined
        this.errorMessage = CAPTCHA_LOAD_ERROR_TEXT
        this.emitUpdate()
        return false
      }
      this.applyChallenge(challenge)
      return true
    } catch (error) {
      if (token !== this.#challengeSeq) {
        return false
      }
      this.phase = 'failed'
      this.applyError(error, CAPTCHA_LOAD_ERROR_TEXT, 'BaseCaptcha.loadChallenge')
      return false
    }
  }

  /**
   * 刷新挑战（先失效旧编号再取新挑战；一次性失效口径与后端一致）。
   *
   * @returns 是否成功落地新挑战。
   */
  async refresh(): Promise<boolean> {
    this.invalidate()
    return this.loadChallenge()
  }

  /**
   * 发送短信验证码（成功启动倒计时；限流命中不启动 / 不重置倒计时）。
   *
   * @returns 是否发送成功。
   */
  async sendSms(): Promise<boolean> {
    const source = this.source
    if (!this.canSendSms || source === undefined) {
      return false
    }
    const token = (this.#smsSeq += 1)
    this.markLoaded()
    this.sending = true
    this.phase = 'sending'
    this.errorCode = undefined
    this.errorMessage = ''
    this.inputError = ''
    this.emitUpdate()
    try {
      const raw = await source.sendSms?.({ phone: normalizeCaptchaPhone(this.phone), scene: this.scene })
      if (token !== this.#smsSeq) {
        return false
      }
      this.sending = false
      const challenge = normalizeCaptchaChallenge(raw, { scene: this.scene, kind: 'sms' })
      if (challenge === undefined) {
        this.phase = 'failed'
        this.errorMessage = CAPTCHA_SEND_ERROR_TEXT
        this.emitUpdate()
        return false
      }
      this.challengeId = challenge.captchaId
      if (challenge.target !== '') {
        this.target = challenge.target
      }
      const cooldown = challenge.cooldown > 0 ? challenge.cooldown : this.cooldown
      this.cooldown = cooldown
      this.startCountdown(cooldown)
      this.phase = 'ready'
      this.emitUpdate()
      return true
    } catch (error) {
      if (token !== this.#smsSeq) {
        return false
      }
      this.sending = false
      const code = readErrorCode(error)
      if (code === 20103) {
        // 限流：仅提示，不启动 / 不重置倒计时（与后端冷却一致）
        this.errorCode = 20103
        this.errorMessage = resolveCaptchaErrorText(20103)
        this.phase = 'failed'
        this.reportError(error, { scope: 'BaseCaptcha.sendSms' })
        this.emitUpdate()
        return false
      }
      this.phase = 'failed'
      this.applyError(error, CAPTCHA_SEND_ERROR_TEXT, 'BaseCaptcha.sendSms')
      return false
    }
  }

  /**
   * 校验当前输入（图形 / 短信；滑块转发轨迹提交）。
   *
   * @returns 是否校验通过。
   */
  async verify(): Promise<boolean> {
    if (this.kind === 'slider') {
      return this.submitSlider()
    }
    const check = checkCaptchaInput(this.value, this.kind, this.inputLength)
    if (!check.valid) {
      this.inputError = check.message
      this.emitUpdate()
      return false
    }
    const source = this.source
    if (!this.canVerify || source === undefined) {
      return false
    }
    const token = (this.#verifySeq += 1)
    this.markLoaded()
    this.verifying = true
    this.phase = 'verifying'
    this.inputError = ''
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw = await source.verify?.({
        captchaId: this.challengeId,
        kind: this.kind,
        code: (this.value ?? '').trim(),
        scene: this.scene,
      })
      if (token !== this.#verifySeq) {
        return false
      }
      this.verifying = false
      if (!readVerified(raw)) {
        this.applyVerifyFailure(20101)
        return false
      }
      this.passed = true
      this.phase = 'passed'
      this.emitUpdate()
      return true
    } catch (error) {
      if (token !== this.#verifySeq) {
        return false
      }
      this.verifying = false
      this.applyVerifyFailure(readErrorCode(error), error, 'BaseCaptcha.verify')
      return false
    }
  }

  /**
   * 提交滑块轨迹（不足最少点数拒绝且零请求；失败清轨迹并失效挑战）。
   *
   * @returns 是否校验通过。
   */
  async submitSlider(): Promise<boolean> {
    if (this.kind !== 'slider' || this.trace.length < CAPTCHA_TRACE_MIN_POINTS) {
      return false
    }
    const source = this.source
    if (!this.canVerify || source === undefined) {
      return false
    }
    const token = (this.#verifySeq += 1)
    this.markLoaded()
    this.verifying = true
    this.phase = 'verifying'
    this.inputError = ''
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
    try {
      const raw = await source.verify?.({
        captchaId: this.challengeId,
        kind: 'slider',
        trace: [...this.trace],
        scene: this.scene,
      })
      if (token !== this.#verifySeq) {
        return false
      }
      this.verifying = false
      if (!readVerified(raw)) {
        this.applyVerifyFailure(20101)
        return false
      }
      this.passed = true
      this.phase = 'passed'
      this.emitUpdate()
      return true
    } catch (error) {
      if (token !== this.#verifySeq) {
        return false
      }
      this.verifying = false
      this.applyVerifyFailure(readErrorCode(error), error, 'BaseCaptcha.submitSlider')
      return false
    }
  }

  /**
   * 追加轨迹采样点（非滑块形态或超上限丢弃）。
   *
   * @param point 轨迹点。
   */
  pushTrace(point: CaptchaTracePoint): void {
    if (this.kind !== 'slider' || this.trace.length >= CAPTCHA_TRACE_MAX_POINTS) {
      return
    }
    const [normalized] = normalizeCaptchaTrace([point])
    if (normalized === undefined) {
      return
    }
    this.trace.push(normalized)
    this.emitUpdate()
  }

  /** 清空轨迹。 */
  clearTrace(): void {
    if (this.trace.length === 0) {
      return
    }
    this.trace.splice(0, this.trace.length)
    this.emitUpdate()
  }

  /**
   * 启动 / 重置倒计时（定时器随生命周期；到零停表）。
   *
   * @param seconds 冷却秒数（缺省取当前配置）。
   */
  startCountdown(seconds?: number): void {
    const total = clampCaptchaSeconds(seconds, this.cooldown > 0 ? this.cooldown : CAPTCHA_SMS_COOLDOWN)
    if (total <= 0) {
      return
    }
    this.stopCountdown()
    this.countdown = total
    this.#countdownTimer = setInterval(() => this.tickCountdown(), 1000)
    this.emitUpdate()
  }

  /** 倒计时步进（到零停表）。 */
  tickCountdown(): void {
    if (this.countdown <= 0) {
      this.stopCountdown()
      return
    }
    this.countdown = nextCountdown(this.countdown)
    if (this.countdown === 0) {
      this.stopCountdown()
    }
    this.emitUpdate()
  }

  /** 停止倒计时定时器（不清剩余秒数）。 */
  stopCountdown(): void {
    if (this.#countdownTimer !== undefined) {
      clearInterval(this.#countdownTimer)
      this.#countdownTimer = undefined
    }
  }

  /** 清挑战（编号 / 图片 / 参数 / 轨迹 / 通过态；保留配置与注入）。 */
  invalidate(): void {
    this.challengeId = ''
    this.imageUrl = ''
    this.payload = ''
    this.passed = false
    this.trace.splice(0, this.trace.length)
    this.emitUpdate()
  }

  /** 全量复位（挑战 / 输入 / 错误 / 轨迹 / 倒计时 / 通过态；保留配置与注入）。 */
  reset(): void {
    this.stopCountdown()
    this.countdown = 0
    this.challengeId = ''
    this.imageUrl = ''
    this.payload = ''
    this.passed = false
    this.phase = 'idle'
    this.sending = false
    this.verifying = false
    this.inputError = ''
    this.errorCode = undefined
    this.errorMessage = ''
    this.trace.splice(0, this.trace.length)
    this.emitUpdate()
  }

  /** 清空输入与输入校验错误。 */
  clearInput(): void {
    this.inputError = ''
    this.setValue(undefined)
  }

  /** 释放钩子：停止倒计时定时器。 */
  protected override onDispose(): void {
    this.stopCountdown()
  }

  /**
   * 落地挑战（编号 / 图片 / 参数 / 有效期 / 脱敏目标 / 冷却配置）。
   *
   * @param challenge 归一挑战。
   */
  private applyChallenge(challenge: CaptchaChallenge): void {
    this.challengeId = challenge.captchaId
    this.imageUrl = challenge.image
    this.payload = challenge.payload
    if (challenge.expiresIn > 0) {
      this.ttl = challenge.expiresIn
    }
    if (challenge.target !== '') {
      this.target = challenge.target
    }
    if (challenge.kind === 'sms' && challenge.cooldown > 0) {
      this.cooldown = challenge.cooldown
    }
    this.phase = 'ready'
    this.passed = false
    this.inputError = ''
    this.errorCode = undefined
    this.errorMessage = ''
    this.emitUpdate()
  }

  /**
   * 应用校验失败（文案 + 挑战失效；图形 / 滑块由件层自动刷新）。
   *
   * @param code 错误码（缺省按 20101）。
   * @param error 原始错误（可选，用于上报）。
   * @param scope 上报域（可选）。
   */
  private applyVerifyFailure(code: number | undefined, error?: unknown, scope?: string): void {
    const resolved = isCaptchaErrorCode(code) ? (code as number) : 20101
    this.passed = false
    this.phase = 'failed'
    this.errorCode = resolved
    this.errorMessage = resolveCaptchaErrorText(resolved)
    this.invalidate()
    if (error !== undefined) {
      this.reportError(error, { scope: scope ?? 'BaseCaptcha.verify' })
    }
    this.emitUpdate()
  }

  /**
   * 应用通路错误（错误码文案优先，回落兜底文案）。
   *
   * @param error 原始错误。
   * @param fallback 兜底文案。
   * @param scope 上报域。
   */
  private applyError(error: unknown, fallback: string, scope: string): void {
    const code = readErrorCode(error)
    this.errorCode = code
    this.errorMessage = isCaptchaErrorCode(code) ? resolveCaptchaErrorText(code) : fallback
    this.reportError(error, { scope })
    this.emitUpdate()
  }

  /** 广播更新（已释放则忽略）。 */
  private emitUpdate(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}

/**
 * 读取校验通过标记（非对象 / `verified === false` 视为未通过）。
 *
 * @param raw 原始响应。
 * @returns 是否通过。
 */
function readVerified(raw: unknown): boolean {
  if (raw === undefined || raw === null) {
    return false
  }
  if (typeof raw === 'object' && !Array.isArray(raw) && (raw as { verified?: unknown }).verified === false) {
    return false
  }
  return true
}

/**
 * 读取错误码（兼容 `code` / `errorCode`）。
 *
 * @param error 原始错误。
 * @returns 错误码或 `undefined`。
 */
function readErrorCode(error: unknown): number | undefined {
  if (error !== null && typeof error === 'object') {
    const raw = error as { code?: unknown; errorCode?: unknown }
    const code = typeof raw.code === 'number' ? raw.code : raw.errorCode
    if (typeof code === 'number' && Number.isFinite(code)) {
      return code
    }
  }
  return undefined
}
