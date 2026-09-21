/**
 * 验证码领域纯函数与数据模型：形态 / 场景 / 挑战与策略归一、手机号脱敏、输入校验、阈值判定、
 * 倒计时步进、滑块轨迹归一与提交构造、图片数据 URL 组装与错误码文案。
 *
 * 与后端 `app/captcha/base.py` 同源（常量 / 场景 / 错误码子段 `201xx`）；纯数据、零依赖：
 * 不触 DOM、不请求、不依赖渲染框架与第三方库，供核心基类 / 插件工具 / 移动端同契约复用。
 */

/** 验证码有效期（秒，5 分钟；与后端 `CAPTCHA_TTL` 同源）。 */
export const CAPTCHA_TTL = 300
/** 短信重发冷却（秒；与后端 `SMS_COOLDOWN` 同源，同时为前端倒计时口径）。 */
export const CAPTCHA_SMS_COOLDOWN = 60
/** 连续失败阈值（与后端 `CAPTCHA_FAIL_THRESHOLD` 同源）。 */
export const CAPTCHA_FAIL_THRESHOLD = 3
/** 图形验证码输入长度下限（与后端出题字符数同源）。 */
export const CAPTCHA_IMAGE_MIN_LENGTH = 4
/** 图形验证码输入长度上限。 */
export const CAPTCHA_IMAGE_MAX_LENGTH = 6
/** 短信验证码输入长度。 */
export const CAPTCHA_SMS_LENGTH = 6
/** 滑块轨迹终点容差（像素下限；与后端 `SLIDER_TOLERANCE` 同源，前端仅展示校正用）。 */
export const CAPTCHA_SLIDER_TOLERANCE = 10
/** 轨迹提交最少点数（起点 + 终点）。 */
export const CAPTCHA_TRACE_MIN_POINTS = 2
/** 轨迹采样点数上限（超出丢弃，防长拖拽内存无界）。 */
export const CAPTCHA_TRACE_MAX_POINTS = 240
/** 形态枚举（与后端 `CaptchaKind` 同源）。 */
export const CAPTCHA_KINDS: readonly CaptchaKind[] = ['image', 'slider', 'sms']
/** 场景枚举（与后端 `CAPTCHA_SCENES` 同源）。 */
export const CAPTCHA_SCENES: readonly CaptchaScene[] = ['login', 'reset_password', 'bind', 'unbind', 'register']
/** 空值占位（统一占位符）。 */
export const CAPTCHA_EMPTY_VALUE = '—'
/** 占位降级文案（与 `06_01` 冻结默认一致）。 */
export const CAPTCHA_PLACEHOLDER_TEXT = '验证码未就绪（占位）'
/** 验证码输入占位提示。 */
export const CAPTCHA_INPUT_PLACEHOLDER = '请输入验证码'
/** 短信验证码输入占位提示。 */
export const CAPTCHA_SMS_INPUT_PLACEHOLDER = '请输入短信验证码'
/** 图形刷新按钮文案。 */
export const CAPTCHA_REFRESH_TEXT = '刷新'
/** 短信发送按钮文案。 */
export const CAPTCHA_SEND_TEXT = '获取验证码'
/** 短信重发按钮文案。 */
export const CAPTCHA_RESEND_TEXT = '重新发送'
/** 校验通过文案。 */
export const CAPTCHA_PASS_TEXT = '验证通过'
/** 滑块提示文案。 */
export const CAPTCHA_SLIDER_HINT = '拖动滑块到缺口位置'
/** 滑块失败重试文案。 */
export const CAPTCHA_SLIDER_RETRY_TEXT = '验证失败，请重试'
/** 后端占位未出图时的提示文案。 */
export const CAPTCHA_IMAGE_EMPTY_TEXT = '验证码图片待后端生成（占位）'
/** 挑战获取失败文案。 */
export const CAPTCHA_LOAD_ERROR_TEXT = '验证码获取失败，请重试'
/** 短信发送失败文案。 */
export const CAPTCHA_SEND_ERROR_TEXT = '验证码发送失败，请重试'
/** 校验失败通用文案（错误码未命中时回落）。 */
export const CAPTCHA_VERIFY_ERROR_TEXT = '验证码校验失败，请重试'
/** 必填 / 未完成校验提示。 */
export const CAPTCHA_REQUIRED_TEXT = '请完成验证码校验'
/** 验证码错误码文案（20101 ~ 20103，与后端认证段子段 `201xx` 同源）。 */
export const CAPTCHA_ERROR_TEXTS: Readonly<Record<number, string>> = {
  20101: '验证码错误',
  20102: '验证码已失效，请重新获取',
  20103: '发送过于频繁，请稍后再试',
}

/** 验证码形态（图形 / 滑块 / 短信）。 */
export type CaptchaKind = 'image' | 'slider' | 'sms'
/** 使用场景（与后端 `CAPTCHA_SCENES` 同源）。 */
export type CaptchaScene = 'login' | 'reset_password' | 'bind' | 'unbind' | 'register'
/** 挑战生命周期阶段（idle → loading / sending / verifying → ready / passed / failed）。 */
export type CaptchaPhase = 'idle' | 'loading' | 'sending' | 'verifying' | 'ready' | 'passed' | 'failed'
/** 输入校验结果。 */
export interface CaptchaCheckResult {
  /** 是否通过。 */
  valid: boolean
  /** 未通过时的提示文案（通过为空串）。 */
  message: string
}
/** 归一后的挑战（图片已组装 data URL；编号为一次性失效凭据）。 */
export interface CaptchaChallenge {
  /** 挑战编号（一次性失效凭据；刷新后旧编号不可复用）。 */
  captchaId: string
  /** 挑战形态。 */
  kind: CaptchaKind
  /** 挑战图片（`data:image/png;base64,…`；空串表示后端占位未出图）。 */
  image: string
  /** 有效期（秒）。 */
  expiresIn: number
  /** 使用场景。 */
  scene: string
  /** 形态参数（原始 JSON 串；滑块为背景与缺口参数）。 */
  payload: string
  /** 脱敏目标（仅短信渠道，其余为空串）。 */
  target: string
  /** 重发冷却（秒；仅短信渠道，其余为 0）。 */
  cooldown: number
}
/** 滑块形态参数（`payload` 解析结果；缺省时件层以纯轨道降级呈现）。 */
export interface CaptchaSliderParams {
  /** 背景图（data URL；缺省纯轨道降级）。 */
  background?: string
  /** 缺口横向位置（像素）。 */
  gapX?: number
  /** 缺口纵向位置（像素）。 */
  gapY?: number
  /** 画布宽度（像素）。 */
  width?: number
  /** 画布高度（像素）。 */
  height?: number
}
/** 场景策略（与后端 `CaptchaScenePolicy` 同源）。 */
export interface CaptchaPolicy {
  /** 使用场景。 */
  scene: string
  /** 该场景是否强制要求验证码。 */
  required: boolean
  /** 连续失败阈值。 */
  failThreshold: number
  /** 有效期（秒）。 */
  ttl: number
  /** 重发冷却（秒）。 */
  cooldown: number
}
/** 滑块轨迹点（`t` 为相对起点毫秒；提交后端口径为 `[x, y, t]`）。 */
export interface CaptchaTracePoint {
  /** 相对轨道左侧像素。 */
  x: number
  /** 相对轨道顶部像素。 */
  y: number
  /** 相对拖动起点毫秒。 */
  t: number
}

/**
 * 归一验证码形态（非法 / 空返回 `undefined`）。
 *
 * @param raw 原始值。
 * @returns 合法形态或 `undefined`。
 */
export function normalizeCaptchaKind(raw: unknown): CaptchaKind | undefined {
  return typeof raw === 'string' && (CAPTCHA_KINDS as readonly string[]).includes(raw)
    ? (raw as CaptchaKind)
    : undefined
}

/**
 * 归一使用场景（非法 / 空返回 `undefined`）。
 *
 * @param raw 原始值。
 * @returns 合法场景或 `undefined`。
 */
export function normalizeCaptchaScene(raw: unknown): CaptchaScene | undefined {
  return typeof raw === 'string' && (CAPTCHA_SCENES as readonly string[]).includes(raw)
    ? (raw as CaptchaScene)
    : undefined
}

/**
 * 归一挑战响应（兼容 snake_case；`captcha_id` 缺失剔除；响应缺省字段回落请求侧）。
 *
 * @param raw 原始响应数据体。
 * @param fallback 请求侧回落（场景 / 形态）。
 * @returns 归一挑战或 `undefined`。
 */
export function normalizeCaptchaChallenge(
  raw: unknown,
  fallback: { scene?: string; kind?: CaptchaKind } = {},
): CaptchaChallenge | undefined {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined
  }
  const record = raw as Record<string, unknown>
  const captchaId = readText(record.captcha_id) || readText(record.captchaId) || readText(record.challengeId)
  if (captchaId === '') {
    return undefined
  }
  const kind = normalizeCaptchaKind(record.kind) ?? fallback.kind ?? 'image'
  return {
    captchaId,
    kind,
    image: captchaImageUrl(readText(record.image) || readText(record.imageUrl)),
    expiresIn: clampCaptchaSeconds(record.expires_in ?? record.expiresIn, CAPTCHA_TTL),
    scene: readText(record.scene) || fallback.scene || 'login',
    payload: readText(record.payload),
    target: readText(record.target),
    cooldown: clampCaptchaSeconds(record.cooldown, kind === 'sms' ? CAPTCHA_SMS_COOLDOWN : 0),
  }
}

/**
 * 平台默认场景策略（登录场景首次不强制，其余场景强制；与后端默认表同源）。
 *
 * @param scene 使用场景（缺省 `login`）。
 * @returns 场景策略。
 */
export function defaultCaptchaPolicy(scene: string = 'login'): CaptchaPolicy {
  return {
    scene,
    required: scene !== 'login',
    failThreshold: CAPTCHA_FAIL_THRESHOLD,
    ttl: CAPTCHA_TTL,
    cooldown: CAPTCHA_SMS_COOLDOWN,
  }
}

/**
 * 归一场景策略（兼容 `fail_threshold`；缺省回落平台默认表）。
 *
 * @param raw 原始策略数据体。
 * @param scene 场景（响应缺省时回落）。
 * @returns 归一策略。
 */
export function normalizeCaptchaPolicy(raw: unknown, scene: CaptchaScene = 'login'): CaptchaPolicy {
  const fallback = defaultCaptchaPolicy(scene)
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return fallback
  }
  const record = raw as Record<string, unknown>
  const resolved = readText(record.scene) || scene
  return {
    scene: resolved,
    required: typeof record.required === 'boolean' ? record.required : resolved !== 'login',
    failThreshold: clampCaptchaSeconds(record.fail_threshold ?? record.failThreshold, fallback.failThreshold),
    ttl: clampCaptchaSeconds(record.ttl, fallback.ttl),
    cooldown: clampCaptchaSeconds(record.cooldown, fallback.cooldown),
  }
}

/**
 * 解析滑块形态参数（JSON 容错；兼容 `bg` / `gap_x` / `w` 等别名）。
 *
 * @param payload 形态参数原始串。
 * @returns 滑块参数（无法解析时为空对象）。
 */
export function parseCaptchaSliderParams(payload: unknown): CaptchaSliderParams {
  if (typeof payload !== 'string' || payload.trim() === '') {
    return {}
  }
  let raw: unknown
  try {
    raw = JSON.parse(payload)
  } catch {
    return {}
  }
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return {}
  }
  const record = raw as Record<string, unknown>
  const params: CaptchaSliderParams = {}
  const background = readText(record.background) || readText(record.bg) || readText(record.image)
  if (background !== '') {
    params.background = captchaImageUrl(background)
  }
  const gapX = readNonNegative(record.gap_x ?? record.gapX)
  if (gapX !== undefined) {
    params.gapX = gapX
  }
  const gapY = readNonNegative(record.gap_y ?? record.gapY)
  if (gapY !== undefined) {
    params.gapY = gapY
  }
  const width = readNonNegative(record.width ?? record.w)
  if (width !== undefined) {
    params.width = width
  }
  const height = readNonNegative(record.height ?? record.h)
  if (height !== undefined) {
    params.height = height
  }
  return params
}

/**
 * 组装挑战图片地址（base64 → `data:image/png;base64,…`；已是 data / http / blob 前缀原样）。
 *
 * @param image 图片值（base64 或地址）。
 * @returns 可用图片地址（空串原样）。
 */
export function captchaImageUrl(image: unknown): string {
  if (typeof image !== 'string') {
    return ''
  }
  const value = image.trim()
  if (value === '' || value.startsWith('data:') || value.startsWith('blob:') || /^https?:\/\//.test(value)) {
    return value
  }
  return `data:image/png;base64,${value}`
}

/**
 * 归一手机号（去空格 / 连字符）。
 *
 * @param phone 原始手机号。
 * @returns 归一手机号。
 */
export function normalizeCaptchaPhone(phone: unknown): string {
  return typeof phone === 'string' ? phone.replace(/[\s-]/g, '') : ''
}

/**
 * 手机号脱敏（保留前 3 后 4，如 `138****5678`；不足 8 位保留前 3；任何输入不原样回显）。
 *
 * @param phone 手机号。
 * @returns 脱敏手机号。
 */
export function maskCaptchaPhone(phone: unknown): string {
  const value = normalizeCaptchaPhone(phone)
  if (value === '') {
    return ''
  }
  return value.length >= 8 ? `${value.slice(0, 3)}****${value.slice(-4)}` : `${value.slice(0, 3)}****`
}

/**
 * 构造输入提示文案（按形态与定长覆盖）。
 *
 * @param kind 形态。
 * @param length 定长覆盖（> 0 生效）。
 * @returns 提示文案。
 */
export function captchaInputHint(kind: CaptchaKind, length = 0): string {
  if (kind === 'sms') {
    const expected = length > 0 ? Math.floor(length) : CAPTCHA_SMS_LENGTH
    return `请输入 ${expected} 位短信验证码`
  }
  if (length > 0) {
    return `请输入 ${Math.floor(length)} 位验证码`
  }
  return `请输入 ${CAPTCHA_IMAGE_MIN_LENGTH}-${CAPTCHA_IMAGE_MAX_LENGTH} 位验证码`
}

/**
 * 校验验证码输入（非空 + 长度 + 字符集；图形字母数字、短信纯数字）。
 *
 * @param value 输入值。
 * @param kind 形态。
 * @param length 定长覆盖（> 0 生效；缺省图形 4-6 位、短信 6 位）。
 * @returns 校验结果。
 */
export function checkCaptchaInput(value: unknown, kind: CaptchaKind, length = 0): CaptchaCheckResult {
  const text = typeof value === 'string' ? value.trim() : ''
  if (text === '') {
    return { valid: false, message: kind === 'sms' ? CAPTCHA_SMS_INPUT_PLACEHOLDER : CAPTCHA_INPUT_PLACEHOLDER }
  }
  if (kind === 'slider') {
    return { valid: true, message: '' }
  }
  if (kind === 'sms') {
    const expected = length > 0 ? Math.floor(length) : CAPTCHA_SMS_LENGTH
    if (!/^\d+$/.test(text) || text.length !== expected) {
      return { valid: false, message: captchaInputHint(kind, length) }
    }
    return { valid: true, message: '' }
  }
  const min = length > 0 ? Math.floor(length) : CAPTCHA_IMAGE_MIN_LENGTH
  const max = length > 0 ? Math.floor(length) : CAPTCHA_IMAGE_MAX_LENGTH
  if (!/^[a-zA-Z0-9]+$/.test(text) || text.length < min || text.length > max) {
    return { valid: false, message: captchaInputHint(kind, length) }
  }
  return { valid: true, message: '' }
}

/**
 * 失败阈值判定（`failCount >= threshold`；阈值 ≤ 0 或非法不强制）。
 *
 * @param failCount 连续失败计数。
 * @param threshold 阈值（缺省平台默认 3）。
 * @returns 是否达到强制要求。
 */
export function shouldRequireCaptcha(failCount: number, threshold: number = CAPTCHA_FAIL_THRESHOLD): boolean {
  if (!Number.isFinite(failCount) || !Number.isFinite(threshold) || threshold <= 0) {
    return false
  }
  return failCount >= threshold
}

/**
 * 倒计时步进（当前 > 0 减一，否则归零）。
 *
 * @param current 当前剩余秒数。
 * @returns 下一秒剩余。
 */
export function nextCountdown(current: number): number {
  if (!Number.isFinite(current) || current <= 0) {
    return 0
  }
  return Math.max(0, Math.floor(current) - 1)
}

/**
 * 秒数夹取（正数取整；非法回落 `fallback`）。
 *
 * @param value 原始值。
 * @param fallback 回落值。
 * @returns 归一秒数。
 */
export function clampCaptchaSeconds(value: unknown, fallback: number): number {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return Math.floor(value)
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    if (Number.isFinite(parsed) && parsed > 0) {
      return Math.floor(parsed)
    }
  }
  return fallback
}

/**
 * 倒计时文案（`${n}s`）。
 *
 * @param seconds 剩余秒数。
 * @returns 文案。
 */
export function countdownText(seconds: number): string {
  return `${Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0))}s`
}

/**
 * 形态展示文案。
 *
 * @param kind 形态。
 * @returns 中文文案。
 */
export function captchaKindText(kind: CaptchaKind): string {
  if (kind === 'slider') {
    return '滑块验证'
  }
  return kind === 'sms' ? '短信验证码' : '图形验证码'
}

/**
 * 归一轨迹点序列（兼容 `[x, y, t]` 数组与 `{x, y, t}` 对象；非法点剔除；非负取整）。
 *
 * @param raw 原始轨迹。
 * @returns 归一轨迹点。
 */
export function normalizeCaptchaTrace(raw: unknown): CaptchaTracePoint[] {
  if (!Array.isArray(raw)) {
    return []
  }
  const points: CaptchaTracePoint[] = []
  for (const item of raw) {
    const point = readTracePoint(item)
    if (point !== undefined) {
      points.push(point)
    }
  }
  return points
}

/**
 * 构造提交轨迹（后端口径 `[[x, y, t], …]`）。
 *
 * @param points 轨迹点。
 * @returns 线参数轨迹。
 */
export function buildCaptchaTrace(points: readonly CaptchaTracePoint[]): [number, number, number][] {
  return points.map((point) => [Math.round(point.x), Math.round(point.y), Math.round(point.t)])
}

/**
 * 构造出题线参数（`{ scene, kind }`）。
 *
 * @param input 出题输入。
 * @returns 线参数。
 */
export function buildCaptchaChallengeQuery(input: { scene?: string; kind?: string }): Record<string, unknown> {
  return {
    scene: normalizeCaptchaScene(input.scene) ?? 'login',
    kind: normalizeCaptchaKind(input.kind) ?? 'image',
  }
}

/**
 * 构造短信发送线参数（`{ phone, scene }`）。
 *
 * @param input 发送输入。
 * @returns 线参数。
 */
export function buildCaptchaSmsQuery(input: { phone?: string; scene?: string }): Record<string, unknown> {
  return {
    phone: normalizeCaptchaPhone(input.phone),
    scene: normalizeCaptchaScene(input.scene) ?? 'login',
  }
}

/**
 * 构造凭证校验线参数（`{ captcha_id, kind, code, trace, scene }`）。
 *
 * @param input 校验输入。
 * @returns 线参数。
 */
export function buildCaptchaVerifyQuery(input: {
  captchaId?: string
  kind?: string
  code?: string
  trace?: readonly CaptchaTracePoint[]
  scene?: string
}): Record<string, unknown> {
  return {
    captcha_id: input.captchaId ?? '',
    kind: normalizeCaptchaKind(input.kind) ?? 'image',
    code: input.code ?? '',
    trace: buildCaptchaTrace(input.trace ?? []),
    scene: normalizeCaptchaScene(input.scene) ?? 'login',
  }
}

/**
 * 是否验证码错误码（20101 ~ 20103）。
 *
 * @param code 错误码。
 * @returns 是否命中子段。
 */
export function isCaptchaErrorCode(code: unknown): boolean {
  return typeof code === 'number' && code in CAPTCHA_ERROR_TEXTS
}

/**
 * 错误码文案（未命中回落通用失败文案）。
 *
 * @param code 错误码。
 * @returns 中文文案。
 */
export function resolveCaptchaErrorText(code: unknown): string {
  return typeof code === 'number' && code in CAPTCHA_ERROR_TEXTS
    ? (CAPTCHA_ERROR_TEXTS[code] as string)
    : CAPTCHA_VERIFY_ERROR_TEXT
}

/**
 * 读取文本字段（非字符串返回空串）。
 *
 * @param value 原始值。
 * @returns 文本。
 */
function readText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

/**
 * 读取非负数值（非法返回 `undefined`）。
 *
 * @param value 原始值。
 * @returns 非负整数或 `undefined`。
 */
function readNonNegative(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    return Math.round(value)
  }
  return undefined
}

/**
 * 读取轨迹点（数组 / 对象两种形态）。
 *
 * @param item 原始点。
 * @returns 轨迹点或 `undefined`。
 */
function readTracePoint(item: unknown): CaptchaTracePoint | undefined {
  if (Array.isArray(item)) {
    const [x, y, t] = item as unknown[]
    return toTracePoint(x, y, t)
  }
  if (item !== null && typeof item === 'object') {
    const record = item as Record<string, unknown>
    return toTracePoint(record.x, record.y, record.t ?? record.time)
  }
  return undefined
}

/**
 * 组装轨迹点（三项均须为非负数值）。
 *
 * @param x 横坐标。
 * @param y 纵坐标。
 * @param t 相对毫秒。
 * @returns 轨迹点或 `undefined`。
 */
function toTracePoint(x: unknown, y: unknown, t: unknown): CaptchaTracePoint | undefined {
  const px = readNonNegative(x)
  const py = readNonNegative(y)
  const pt = readNonNegative(t)
  if (px === undefined || py === undefined || pt === undefined) {
    return undefined
  }
  return { x: px, y: py, t: pt }
}
