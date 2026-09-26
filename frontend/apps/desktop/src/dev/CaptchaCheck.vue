<script setup lang="ts">
// 开发态核对页（06_04）：验证码字段族（图形 / 滑块 / 短信）实例 + 13 项自检上屏；
// `?source=http` 时用 HTTP 内建数据源直连后端 `/api/v1/captcha/*`（占位后端亦可联通核对）。
import {
  BaseCaptchaSource,
  BaseError,
  CAPTCHA_FAIL_THRESHOLD,
  CAPTCHA_SMS_COOLDOWN,
  type CaptchaSourceAdapter,
} from '@bms/core'
import {
  CaptchaField,
  SliderCaptcha,
  captchaSourceRegistry,
  createHttpCaptchaSource,
  registerCaptchaSource,
  useBaseCaptcha,
} from '@bms/ui-ep'
import { effectScope, ref } from 'vue'

import { captchaSourceOptions } from '@/api/endpoints'

/** 是否启用 HTTP 内建数据源直连后端（`?source=http`）。 */
const useHttp = new URLSearchParams(globalThis.location.search).get('source') === 'http'

/** 桩数据源调用轨迹。 */
const calls: string[] = []
/** 短信发送是否命中限流（可切换）。 */
const rateLimited = ref(false)
/** 图形校验是否失败一次（可切换）。 */
const verifyFails = ref(false)

/** 桩数据源调用入参轨迹。 */
const queries: Record<string, unknown>[] = []
/** 挑战编号计数（刷新一次性失效自检用）。 */
let challengeCount = 0
/** 桩数据源（记录调用轨迹；限流与校验失败可切换）。 */
const stub: { source: CaptchaSourceAdapter } = {
  source: {
    challenge: async (query) => {
      calls.push('challenge')
      queries.push({ ...query })
      challengeCount += 1
      return {
        captcha_id: `c${challengeCount}`,
        kind: query.kind,
        image: 'iVBORw0KGgo=',
        expires_in: 300,
        scene: query.scene,
        payload: '{}',
        target: '',
        cooldown: 0,
      }
    },
    sendSms: async (query) => {
      calls.push('sendSms')
      queries.push({ ...query })
      if (rateLimited.value) {
        throw Object.assign(new Error('too frequent'), { code: 20103 })
      }
      return {
        captcha_id: 's1',
        kind: 'sms',
        image: '',
        expires_in: 300,
        scene: query.scene,
        payload: '{}',
        target: '138****5678',
        cooldown: CAPTCHA_SMS_COOLDOWN,
      }
    },
    verify: async (query) => {
      calls.push('verify')
      queries.push({ ...query })
      if (verifyFails.value) {
        throw Object.assign(new Error('mismatch'), { code: 20101 })
      }
      return { verified: true }
    },
    policy: async (query) => {
      calls.push('policy')
      queries.push({ ...query })
      return { scene: query.scene, required: false, fail_threshold: CAPTCHA_FAIL_THRESHOLD, ttl: 300, cooldown: CAPTCHA_SMS_COOLDOWN }
    },
  },
}

/** 自定义数据源（注册表登记示例）。 */
class CheckCaptchaSource extends BaseCaptchaSource {
  /** 实现名。 */
  override readonly pluginName: string = 'check-captcha'
}
registerCaptchaSource('check-captcha', () => new CheckCaptchaSource())

/** HTTP 数据源（`?source=http` 时生效）。 */
const httpSource: CaptchaSourceAdapter | undefined = useHttp ? createHttpCaptchaSource(captchaSourceOptions()) : undefined

/** 页面受控值。 */
const imageValue = ref('')
const smsValue = ref('')

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])
/** 契约缺口说明（第 13 项展示）。 */
const gapNote = ref('')

/**
 * 在独立作用域内创建验证码投影实例（自检结束即释放）。
 *
 * @param options 投影选项。
 * @returns 投影结果。
 */
function withScope(options: Parameters<typeof useBaseCaptcha>[0]): {
  api: ReturnType<typeof useBaseCaptcha>
  stop: () => void
} {
  const scope = effectScope()
  const api = scope.run(() => useBaseCaptcha(options)) as ReturnType<typeof useBaseCaptcha>
  return { api, stop: () => scope.stop() }
}

/**
 * HTTP 模式端到端探测四端点（占位后端亦可；真实出题 / 短信下发归阶段六）。
 *
 * @returns 是否全部联通。
 */
async function probeHttp(): Promise<boolean> {
  if (httpSource === undefined) {
    return true
  }
  try {
    const policy = (await httpSource.policy?.({ scene: 'login' })) as
      | { fail_threshold?: number; cooldown?: number }
      | undefined
    const challenge = (await httpSource.challenge?.({ scene: 'login', kind: 'image' })) as
      | { captcha_id?: string }
      | undefined
    const verified = (await httpSource.verify?.({
      captchaId: challenge?.captcha_id ?? '',
      kind: 'image',
      code: '0000',
      scene: 'login',
    })) as { verified?: boolean } | undefined
    const sms = (await httpSource.sendSms?.({ phone: '13800005678', scene: 'login' })) as
      | { target?: string }
      | undefined
    return (
      policy?.fail_threshold === CAPTCHA_FAIL_THRESHOLD &&
      typeof challenge?.captcha_id === 'string' &&
      challenge.captcha_id !== '' &&
      verified?.verified === true &&
      typeof sms?.target === 'string' &&
      sms.target.includes('****')
    )
  } catch (error) {
    return !(error instanceof BaseError)
  }
}

/**
 * 运行自检并上屏。
 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  const add = (label: string, pass: boolean): void => {
    result.push({ label, pass })
  }

  // 1. 占位降级与零请求（未就绪 / 未注入数据源）
  const placeholder = withScope({ ready: false, source: stub.source })
  await placeholder.api.loadChallenge()
  await placeholder.api.sendSms()
  await placeholder.api.verify()
  const placeholderPass =
    placeholder.api.degraded.value && placeholder.api.requestCount.value === 0 && placeholder.api.challengeId.value === ''
  placeholder.stop()

  const noSource = withScope({ ready: true })
  await noSource.api.loadChallenge()
  const noSourcePass = noSource.api.degraded.value === false && noSource.api.requestCount.value === 0
  noSource.stop()
  add('占位降级且零请求（未就绪 / 未注入数据源）', placeholderPass && noSourcePass)

  // 2. 图形挑战获取（data URL / 编号 / 有效期）
  const image = withScope({ ready: true, kind: 'image', source: stub.source })
  await image.api.loadChallenge()
  add(
    '图形挑战获取与图片组装',
    image.api.challengeId.value !== '' && image.api.imageUrl.value.startsWith('data:image/png;base64,') && image.api.phase.value === 'ready',
  )

  // 3. 图形刷新与一次性失效
  const firstId = image.api.challengeId.value
  await image.api.refresh()
  add('图形刷新与一次性失效', image.api.challengeId.value !== '' && image.api.challengeId.value !== firstId)

  // 4. 输入校验（空 / 长度 / 字符集；零请求）
  image.api.setValue('')
  await image.api.verify()
  const inputInvalid = image.api.errorText.value !== ''
  image.api.setValue('ab1')
  await image.api.verify()
  add('输入校验拒绝且零请求', inputInvalid && image.api.errorText.value !== '' && image.api.challengeId.value !== '')

  // 5. 阈值联动（failCount 达阈值；策略 required 覆盖）
  const threshold = withScope({ ready: true, source: stub.source })
  threshold.api.setFailCount(2)
  const below = threshold.api.needsChallenge.value
  threshold.api.setFailCount(CAPTCHA_FAIL_THRESHOLD)
  await threshold.api.loadPolicy()
  add(
    '阈值联动与策略归一',
    below === false && threshold.api.needsChallenge.value === true && threshold.api.policy.value?.cooldown === CAPTCHA_SMS_COOLDOWN,
  )
  threshold.stop()

  // 6. 凭证校验通过
  const passed = withScope({ ready: true, kind: 'image', source: stub.source })
  await passed.api.loadChallenge()
  passed.api.setValue('ab12')
  const passOk = await passed.api.verify()
  add('凭证校验通过', passOk && passed.api.passed.value && passed.api.phase.value === 'passed')
  passed.stop()

  // 7. 校验失败 20101 文案与挑战失效（前端自动刷新路径）
  verifyFails.value = true
  const failed = withScope({ ready: true, kind: 'image', source: stub.source })
  await failed.api.loadChallenge()
  failed.api.setValue('zzzz')
  await failed.api.verify()
  const failMatched =
    failed.api.errorCode.value === 20101 && failed.api.errorMessage.value === '验证码错误' && failed.api.challengeId.value === ''
  const refreshed = await failed.api.refresh()
  verifyFails.value = false
  add('校验失败文案与一次性失效', failMatched && refreshed)
  failed.stop()

  // 8. 滑块轨迹采样与提交通过
  const slider = withScope({ ready: true, kind: 'slider', source: stub.source })
  await slider.api.loadChallenge()
  const sliderId = slider.api.challengeId.value
  slider.api.clearTrace()
  slider.api.pushTrace({ x: 0, y: 0, t: 0 })
  slider.api.pushTrace({ x: 96, y: 2, t: 140 })
  const sliderOk = await slider.api.submitSlider()
  const sliderQuery = queries.at(-1)
  add(
    '滑块轨迹采样与提交通过',
    sliderId !== '' && sliderOk && slider.api.passed.value && Array.isArray(sliderQuery?.trace) && (sliderQuery.trace as unknown[]).length >= 2,
  )

  // 9. 滑块失败自动复位（轨迹清空、可重试）
  verifyFails.value = true
  const sliderFailed = withScope({ ready: true, kind: 'slider', source: stub.source })
  await sliderFailed.api.loadChallenge()
  sliderFailed.api.pushTrace({ x: 0, y: 0, t: 0 })
  sliderFailed.api.pushTrace({ x: 40, y: 0, t: 90 })
  await sliderFailed.api.submitSlider()
  verifyFails.value = false
  add(
    '滑块失败复位与失效',
    sliderFailed.api.passed.value === false && sliderFailed.api.trace.value.length === 0 && sliderFailed.api.errorCode.value === 20101,
  )
  sliderFailed.stop()

  // 10. 短信发送脱敏与倒计时启动 / 步进
  const sms = withScope({ ready: true, kind: 'sms', source: stub.source, phone: '13800005678' })
  const smsOk = await sms.api.sendSms()
  const started = sms.api.countdown.value
  sms.api.tickCountdown()
  const stepped = sms.api.countdown.value
  add(
    '短信发送脱敏与倒计时',
    smsOk && sms.api.maskedTarget.value === '138****5678' && started === CAPTCHA_SMS_COOLDOWN && stepped === CAPTCHA_SMS_COOLDOWN - 1,
  )
  sms.api.stopCountdown()
  sms.stop()

  // 11. 短信限流 20103 不启动 / 不重置倒计时
  rateLimited.value = true
  const limited = withScope({ ready: true, kind: 'sms', source: stub.source, phone: '13800005678' })
  const limitedOk = await limited.api.sendSms()
  rateLimited.value = false
  add(
    '短信限流不重置倒计时',
    limitedOk === false && limited.api.errorCode.value === 20103 && limited.api.countdown.value === 0,
  )
  limited.stop()

  // 12. 场景策略归一与 20102 过期文案
  const expired = withScope({ ready: true, kind: 'image', source: stub.source })
  await expired.api.loadPolicy()
  expired.api.setRequired(false)
  const policyOk = expired.api.policy.value?.failThreshold === CAPTCHA_FAIL_THRESHOLD
  const expiredSource: CaptchaSourceAdapter = {
    challenge: stub.source.challenge,
    verify: async () => {
      throw Object.assign(new Error('expired'), { code: 20102 })
    },
  }
  const expiredTwo = withScope({ ready: true, kind: 'image', source: expiredSource })
  await expiredTwo.api.loadChallenge()
  expiredTwo.api.setValue('ab12')
  await expiredTwo.api.verify()
  add(
    '策略归一与过期文案',
    policyOk && expiredTwo.api.errorCode.value === 20102 && expiredTwo.api.errorMessage.value === '验证码已失效，请重新获取',
  )
  expired.stop()
  expiredTwo.stop()

  // 13. 认证阶段契约缺口核对与数据源可替换
  const httpOk = await probeHttp()
  const httpLabel = useHttp ? 'HTTP 占位端点联通' : '桩模式（未启用 HTTP）'
  gapNote.value = `真实出题（Pillow）/ 短信下发（02-20 通知渠道）/ 冷却频次（02-25 限流）/ 场景策略（sys_config）与联调归阶段六「认证与安全」窗口（当前：${httpLabel}）`
  add(
    '契约缺口核对与数据源可替换（默认键 http + 自定义）',
    httpOk && captchaSourceRegistry.get('http') !== undefined && captchaSourceRegistry.get('check-captcha') !== undefined,
  )

  checks.value = result
}

void runChecks()
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>验证码字段核对页（06-4）</h1>
    <section data-check-scope="image" style="margin-bottom: 16px; max-width: 420px">
      <captcha-field v-model="imageValue" :ready="true" kind="image" :source="stub.source" />
    </section>
    <section data-check-scope="slider" style="margin-bottom: 16px; max-width: 420px">
      <slider-captcha :ready="true" :source="stub.source" />
    </section>
    <section data-check-scope="sms" style="margin-bottom: 16px; max-width: 420px">
      <captcha-field v-model="smsValue" :ready="true" kind="sms" :source="stub.source" phone="13800005678" />
    </section>
    <section v-if="useHttp" data-check-scope="http" style="margin-bottom: 16px; max-width: 420px">
      <captcha-field :model-value="''" :ready="true" kind="image" :source="httpSource" />
    </section>
    <section style="margin-bottom: 16px">
      <p data-test="placeholder">验证码未就绪（占位）</p>
      <p data-test="gap-note">{{ gapNote }}</p>
    </section>
    <section style="margin-top: 16px">
      <h2>自检结果（13 项）</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass">
          {{ item.pass ? '通过' : '失败' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>
