// kiwi_id: 966
/** 验证码字段用例（06_04）：契约套件（核心 + 投影）+ 四件 + 工具（HTTP 数据源）+ 占位契约复用。 */

import { BaseError, CAPTCHA_SMS_COOLDOWN, normalizeCaptchaScene, type CaptchaKind, type CaptchaScene } from '@bms/core'
import {
  createCaptchaSourceStub,
  describeCaptchaContract,
  describePlaceholderFieldContract,
  type CaptchaContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  CaptchaField,
  ImageCaptcha,
  SliderCaptcha,
  SmsCaptcha,
  captchaSourceRegistry,
  createHttpCaptchaSource,
  registerCaptchaSource,
  useBaseCaptcha,
  type UseBaseCaptchaResult,
} from '../src'

/** 投影契约目标（基类实例 ↔ 响应式面）。 */
function makeTarget(): CaptchaContractTarget {
  const scope = effectScope()
  const api = scope.run(() => useBaseCaptcha()) as UseBaseCaptchaResult
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get requestCount() {
      return api.requestCount.value
    },
    get kind() {
      return api.kind.value
    },
    get scene() {
      return api.scene.value
    },
    get phase() {
      return api.phase.value
    },
    get imageUrl() {
      return api.imageUrl.value
    },
    get challengeId() {
      return api.challengeId.value
    },
    get payload() {
      return api.payload.value
    },
    get countdown() {
      return api.countdown.value
    },
    get cooldown() {
      return api.cooldown.value
    },
    get sending() {
      return api.sending.value
    },
    get verifying() {
      return api.verifying.value
    },
    get passed() {
      return api.passed.value
    },
    get needsChallenge() {
      return api.needsChallenge.value
    },
    get maskedTarget() {
      return api.maskedTarget.value
    },
    get inputMaxLength() {
      return api.inputMaxLength.value
    },
    get errorCode() {
      return api.errorCode.value
    },
    get errorMessage() {
      return api.errorMessage.value
    },
    get errorText() {
      return api.errorText.value
    },
    get value() {
      return api.value.value
    },
    get trace() {
      return api.trace.value
    },
    setReady: (value) => api.setReady(value),
    setSource: (source) => api.setSource(source),
    setKind: (kind) => api.setKind((kind === 'slider' || kind === 'sms' ? kind : 'image') as CaptchaKind),
    setScene: (scene) => api.setScene((normalizeCaptchaScene(scene) ?? 'login') as CaptchaScene),
    setPhone: (phone) => api.setPhone(phone),
    setCooldown: (seconds) => api.setCooldown(seconds),
    setFailCount: (count) => api.setFailCount(count),
    setRequired: (value) => api.setRequired(value),
    setValue: (value) => api.setValue(value),
    loadPolicy: () => api.loadPolicy(),
    loadChallenge: () => api.loadChallenge(),
    refresh: () => api.refresh(),
    sendSms: () => api.sendSms(),
    verify: () => api.verify(),
    submitSlider: () => api.submitSlider(),
    pushTrace: (point) => api.pushTrace(point),
    clearTrace: () => api.clearTrace(),
    startCountdown: (seconds) => api.startCountdown(seconds),
    stopCountdown: () => api.stopCountdown(),
    tickCountdown: () => api.tickCountdown(),
    dispose: () => scope.stop(),
  }
}

describeCaptchaContract('验证码契约（useBaseCaptcha 投影）', makeTarget)

describePlaceholderFieldContract('占位字段契约（验证码投影，06_01 复用）', () => {
  const scope = effectScope()
  const api = scope.run(() => useBaseCaptcha()) as UseBaseCaptchaResult
  return {
    get ready() {
      return api.ready.value
    },
    get degraded() {
      return api.degraded.value
    },
    get disabled() {
      return api.disabled.value
    },
    get requestCount() {
      return api.requestCount.value
    },
    load: () => {
      void api.loadChallenge()
      void api.loadPolicy()
    },
    setReady: (value) => api.setReady(value),
  }
})

describe('CaptchaField（分发壳，06_01 冻结契约）', () => {
  it('未就绪降级且不发请求', () => {
    const wrapper = mount(CaptchaField, { props: { modelValue: '' } })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('验证码未就绪')
    expect(wrapper.attributes('data-degraded')).toBe('true')
  })

  it('就绪图形分发：刷新按钮上抛 refresh', async () => {
    const wrapper = mount(CaptchaField, { props: { modelValue: '', ready: true, kind: 'image' } })
    expect(wrapper.find('[data-test="image-captcha"]').exists()).toBe(true)
    await wrapper.find('[data-test="captcha-send"]').trigger('click')
    expect(wrapper.emitted('refresh')).toHaveLength(1)
  })

  it('就绪短信分发：冻结倒计时文案与发送上抛', async () => {
    const wrapper = mount(CaptchaField, {
      props: { modelValue: '', ready: true, kind: 'sms', countdown: 30 },
    })
    expect(wrapper.find('[data-test="sms-captcha"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('30s')
    await wrapper.find('[data-test="captcha-send"]').trigger('click')
    expect(wrapper.emitted('send')).toHaveLength(1)
  })

  it('滑块分发与值变更上抛', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(CaptchaField, {
      props: { modelValue: '', ready: true, kind: 'slider', source: source.source },
    })
    expect(wrapper.find('[data-test="slider-captcha"]').exists()).toBe(true)

    const smsWrapper = mount(CaptchaField, {
      props: { modelValue: '', ready: true, kind: 'sms', source: source.source },
    })
    const input = smsWrapper.find('[data-test="captcha-input"]')
    await input.setValue('123456')
    expect(smsWrapper.emitted('update:modelValue')?.at(-1)).toEqual(['123456'])
    expect(smsWrapper.emitted('change')?.at(-1)).toEqual(['123456'])
  })
})

describe('ImageCaptcha（图形件）', () => {
  it('桩数据源自动出题、刷新一次性失效与空图占位', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(ImageCaptcha, { props: { ready: true, source: source.source } })
    await flushPromises()
    expect(source.calls).toEqual(['challenge'])
    const image = wrapper.find('[data-test="captcha-image"]')
    expect(image.exists()).toBe(true)
    expect(image.find('img').attributes('src')?.startsWith('data:image/png;base64,')).toBe(true)

    await wrapper.find('[data-test="captcha-send"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('refresh')).toHaveLength(1)
    expect(source.calls.filter((call) => call === 'challenge')).toHaveLength(2)

    const empty = createCaptchaSourceStub({
      challenge: async () => ({ captcha_id: 'c1', kind: 'image', image: '', expires_in: 300 }),
    })
    const emptyWrapper = mount(ImageCaptcha, { props: { ready: true, source: empty.source } })
    await flushPromises()
    expect(emptyWrapper.find('[data-test="captcha-image-empty"]').text()).toContain('待后端生成')
  })

  it('输入校验：非法上抛 invalid 且零请求；通过上抛 pass', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(ImageCaptcha, { props: { ready: true, source: source.source } })
    await flushPromises()
    const input = wrapper.find('[data-test="captcha-input"]')
    await input.setValue('ab')
    await input.trigger('keyup.enter')
    expect(wrapper.emitted('invalid')).toHaveLength(1)
    expect(source.calls.filter((call) => call === 'verify')).toHaveLength(0)

    await input.setValue('ab12')
    await input.trigger('keyup.enter')
    await flushPromises()
    expect(wrapper.emitted('pass')).toHaveLength(1)
    expect(source.calls).toContain('verify')
  })

  it('校验失败 20101：上抛 fail 并自动刷新（一次性失效）', async () => {
    const source = createCaptchaSourceStub({
      verify: async () => {
        throw Object.assign(new Error('mismatch'), { code: 20101 })
      },
    })
    const wrapper = mount(ImageCaptcha, { props: { ready: true, source: source.source } })
    await flushPromises()
    const input = wrapper.find('[data-test="captcha-input"]')
    await input.setValue('zzzz')
    await input.trigger('keyup.enter')
    await flushPromises()
    expect(wrapper.emitted('fail')?.[0]?.[0]).toMatchObject({ code: 20101 })
    expect(source.calls.filter((call) => call === 'challenge')).toHaveLength(2)
  })

  it('外部直连图片不请求挑战', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(ImageCaptcha, {
      props: { ready: true, source: source.source, imageUrl: 'https://x/captcha.png' },
    })
    await flushPromises()
    expect(source.calls).toEqual([])
    expect(wrapper.find('[data-test="captcha-image"] img').attributes('src')).toBe('https://x/captcha.png')
  })
})

describe('SmsCaptcha（短信件）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('空闲文案含冷却秒数与脱敏目标；发送启动倒计时', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(SmsCaptcha, {
      props: { ready: true, source: source.source, phone: '13800005678', countdown: 30 },
    })
    expect(wrapper.text()).toContain('30s')
    expect(wrapper.find('[data-test="captcha-target"]').text()).toContain('138****5678')

    await wrapper.find('[data-test="captcha-send"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('send')).toHaveLength(1)
    expect(source.calls).toEqual(['sendSms'])
    expect(wrapper.text()).toContain('重新发送')
    expect(wrapper.find('[data-test="captcha-countdown"]').text()).toContain('60s')
    wrapper.unmount()
  })

  it('限流 20103：上抛 rate-limit 且不启动倒计时', async () => {
    const source = createCaptchaSourceStub({
      sendSms: async () => {
        throw Object.assign(new Error('frequent'), { code: 20103 })
      },
    })
    const wrapper = mount(SmsCaptcha, {
      props: { ready: true, source: source.source, phone: '13800005678' },
    })
    await wrapper.find('[data-test="captcha-send"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('rate-limit')).toHaveLength(1)
    expect(wrapper.find('[data-test="captcha-countdown"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="captcha-error"]').text()).toContain('发送过于频繁')
  })

  it('输入校验与通过上抛', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(SmsCaptcha, {
      props: { ready: true, source: source.source, phone: '13800005678' },
    })
    await wrapper.find('[data-test="captcha-send"]').trigger('click')
    await flushPromises()
    const input = wrapper.find('[data-test="captcha-input"]')
    await input.setValue('12345')
    await input.trigger('keyup.enter')
    expect(wrapper.emitted('invalid')).toHaveLength(1)

    await input.setValue('123456')
    await input.trigger('keyup.enter')
    await flushPromises()
    expect(wrapper.emitted('pass')).toHaveLength(1)
    expect(source.calls).toContain('verify')
    wrapper.unmount()
  })
})

describe('SliderCaptcha（自绘滑块件）', () => {
  it('指针拖动采样轨迹并提交通过', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(SliderCaptcha, { props: { ready: true, source: source.source } })
    await flushPromises()
    expect(source.calls).toEqual(['challenge'])

    const handle = wrapper.find('[data-test="captcha-slider-handle"]')
    handle.element.dispatchEvent(new MouseEvent('pointerdown', { clientX: 0, bubbles: true }))
    window.dispatchEvent(new MouseEvent('pointermove', { clientX: 100 }))
    window.dispatchEvent(new MouseEvent('pointerup', { clientX: 100 }))
    await flushPromises()

    expect(wrapper.emitted('pass')).toHaveLength(1)
    const verifyQuery = source.queries.at(-1)
    expect(verifyQuery?.kind).toBe('slider')
    expect((verifyQuery?.trace as unknown[]).length).toBeGreaterThanOrEqual(2)
  })

  it('键盘可操作并提交；失败复位并刷新', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(SliderCaptcha, { props: { ready: true, source: source.source } })
    await flushPromises()
    const handle = wrapper.find('[data-test="captcha-slider-handle"]')
    await handle.trigger('keydown', { key: 'ArrowRight' })
    await handle.trigger('keydown', { key: 'ArrowRight' })
    await handle.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(wrapper.emitted('pass')).toHaveLength(1)

    const failedSource = createCaptchaSourceStub({
      verify: async () => {
        throw Object.assign(new Error('slider'), { code: 20101 })
      },
    })
    const failedWrapper = mount(SliderCaptcha, { props: { ready: true, source: failedSource.source } })
    await flushPromises()
    const failedHandle = failedWrapper.find('[data-test="captcha-slider-handle"]')
    await failedHandle.trigger('keydown', { key: 'ArrowRight' })
    await failedHandle.trigger('keydown', { key: 'ArrowRight' })
    await failedHandle.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(failedWrapper.emitted('fail')).toHaveLength(1)
    expect(failedWrapper.find('[data-test="captcha-slider-retry"]').exists()).toBe(true)
    expect(failedSource.calls.filter((call) => call === 'challenge')).toHaveLength(2)
  })

  it('未拖动不提交（零请求）', async () => {
    const source = createCaptchaSourceStub()
    const wrapper = mount(SliderCaptcha, { props: { ready: true, source: source.source } })
    await flushPromises()
    await wrapper.find('[data-test="captcha-slider-handle"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(source.calls).toEqual(['challenge'])
  })
})

describe('验证码 HTTP 数据源与注册表', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('四端点与线参数与解包', async () => {
    const fetchMock = vi.fn(async (_input: unknown, init?: RequestInit) => {
      const body = typeof init?.body === 'string' ? JSON.parse(init.body) : {}
      return {
        ok: true,
        json: async () => ({ code: 0, message: '', data: { captcha_id: 'c9', ...body } }),
      }
    })
    vi.stubGlobal('fetch', fetchMock)
    const source = createHttpCaptchaSource({ endpoint: '/api/v1' })

    await source.challenge({ scene: 'login', kind: 'image' })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v1/captcha/challenges')
    expect(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body)).toContain('"scene":"login"')

    await source.sendSms({ phone: '13800005678', scene: 'bind' })
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/api/v1/captcha/sms')
    expect(String((fetchMock.mock.calls[1]?.[1] as RequestInit).body)).toContain('"phone":"13800005678"')

    await source.verify({
      captchaId: 'c1',
      kind: 'slider',
      trace: [
        { x: 0, y: 0, t: 0 },
        { x: 80, y: 4, t: 120 },
      ],
      scene: 'login',
    })
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('/api/v1/captcha/verify')
    expect(String((fetchMock.mock.calls[2]?.[1] as RequestInit).body)).toContain('"captcha_id":"c1"')

    await source.policy({ scene: 'login' })
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain('/api/v1/captcha/scenes/login/policy')

    vi.stubGlobal('fetch', undefined)
    expect(await createHttpCaptchaSource().challenge({ scene: 'login', kind: 'image' })).toBeUndefined()
  })

  it('业务错误码抛 BaseError（20101）', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, json: async () => ({ code: 20101, message: '验证码错误', data: null }) })),
    )
    const source = createHttpCaptchaSource()
    await expect(source.verify({ captchaId: 'c1', kind: 'image', code: 'zzzz', scene: 'login' })).rejects.toBeInstanceOf(
      BaseError,
    )
  })

  it('注册表默认键 http 与自定义登记', () => {
    expect(captchaSourceRegistry.get('http')).toBeDefined()
    registerCaptchaSource('spec-captcha', () => createHttpCaptchaSource())
    expect(captchaSourceRegistry.get('spec-captcha')).toBeDefined()
  })
})

describe('验证码常量与默认值', () => {
  it('冷却缺省与后端同源', () => {
    expect(CAPTCHA_SMS_COOLDOWN).toBe(60)
  })
})
