// kiwi_id: 966
/** 验证码族组件基类用例（06_04）：契约套件（同一套断言）+ 身份 / 策略 / 复位 / 占位语义。 */

import { describe, expect, it } from 'vitest'

import { BaseCaptcha } from '../src'
import { createCaptchaSourceStub, describeCaptchaContract } from '../testing'

/** 具体验证码族（可实例化）。 */
class CaptchaState extends BaseCaptcha {}

describeCaptchaContract('验证码契约（核心基类）', () => new CaptchaState())

describe('BaseCaptcha 身份与配置', () => {
  it('能力键与依赖登记', () => {
    const captcha = new CaptchaState()
    expect(captcha.identifier).toBe('captcha')
    expect(captcha.depends).toEqual(['input'])
    expect(captcha.kind).toBe('image')
    expect(captcha.scene).toBe('login')
    expect(captcha.countdown).toBe(0)
    expect(captcha.degraded).toBe(true)
  })

  it('生效禁用（件级禁用 ∨ 占位）与空态', () => {
    const captcha = new CaptchaState()
    expect(captcha.effectiveDisabled).toBe(true)
    captcha.setReady(true)
    expect(captcha.effectiveDisabled).toBe(false)
    captcha.disabled = true
    expect(captcha.effectiveDisabled).toBe(true)
    expect(captcha.empty).toBe(true)
    expect(captcha.hasImage).toBe(false)
    expect(captcha.sliderReady).toBe(false)
  })

  it('切换形态清挑战与倒计时；切换场景清策略缓存', async () => {
    const captcha = new CaptchaState()
    const stub = createCaptchaSourceStub()
    captcha.setReady(true)
    captcha.setSource(stub.source)
    captcha.startCountdown(30)
    await captcha.loadPolicy()
    await captcha.loadChallenge()
    expect(captcha.challengeId).toBe('c1')
    expect(captcha.policyData?.failThreshold).toBe(3)

    captcha.setKind('sms')
    expect(captcha.challengeId).toBe('')
    expect(captcha.countdown).toBe(0)
    expect(captcha.phase).toBe('idle')

    captcha.setScene('bind')
    expect(captcha.policyData).toBeUndefined()
    await captcha.loadPolicy()
    expect(stub.queries.at(-1)).toEqual({ scene: 'bind' })
  })

  it('策略一次加载（二次零请求）且显式覆盖优先', async () => {
    const captcha = new CaptchaState()
    const stub = createCaptchaSourceStub({
      policy: async (query) => ({ scene: query.scene, required: true, fail_threshold: 5, ttl: 120, cooldown: 30 }),
    })
    captcha.setReady(true)
    captcha.setSource(stub.source)
    captcha.setCooldown(90)
    captcha.setOptions({ failThreshold: 7 })
    await captcha.loadPolicy()
    await captcha.loadPolicy()
    expect(captcha.requestCount).toBe(1)
    expect(captcha.cooldown).toBe(90)
    expect(captcha.failThreshold).toBe(7)
    expect(captcha.ttl).toBe(120)
    expect(captcha.needsChallenge).toBe(true)
  })

  it('setOptions 批量装配与受控值归一', () => {
    const captcha = new CaptchaState()
    captcha.setOptions({
      ready: true,
      kind: 'sms',
      scene: 'bind',
      phone: '138-0000-5678',
      cooldown: 45,
      failCount: 2,
      failThreshold: 2,
      inputLength: 4,
      required: false,
    })
    expect(captcha.ready).toBe(true)
    expect(captcha.kind).toBe('sms')
    expect(captcha.phone).toBe('13800005678')
    expect(captcha.cooldown).toBe(45)
    expect(captcha.needsChallenge).toBe(true)
    expect(captcha.inputMaxLength).toBe(4)
    expect(captcha.maskedTarget).toBe('138****5678')

    const changes: (string | undefined)[] = []
    captcha.onChange((value) => changes.push(value))
    captcha.setValue('123456')
    captcha.setValue('123456')
    captcha.clearInput()
    expect(changes).toEqual(['123456', undefined])
    expect(captcha.value).toBeUndefined()
  })

  it('输入错误在改值时清除', async () => {
    const captcha = new CaptchaState()
    const stub = createCaptchaSourceStub()
    captcha.setReady(true)
    captcha.setSource(stub.source)
    await captcha.loadChallenge()
    captcha.setValue('')
    await captcha.verify()
    expect(captcha.errorText).not.toBe('')
    captcha.setValue('abcd')
    expect(captcha.errorText).toBe('')
  })

  it('挑战归一失败与通路错误落错误态', async () => {
    const empty = new CaptchaState()
    empty.setReady(true)
    empty.setSource(createCaptchaSourceStub({ challenge: async () => ({}) }).source)
    expect(await empty.loadChallenge()).toBe(false)
    expect(empty.phase).toBe('failed')
    expect(empty.errorMessage).toBe('验证码获取失败，请重试')

    const boom = new CaptchaState()
    boom.setReady(true)
    boom.setSource(
      createCaptchaSourceStub({
        challenge: async () => {
          throw Object.assign(new Error('boom'), { code: 20102 })
        },
      }).source,
    )
    expect(await boom.loadChallenge()).toBe(false)
    expect(boom.errorCode).toBe(20102)
    expect(boom.errorMessage).toBe('验证码已失效，请重新获取')
  })

  it('外部直连图片不改变挑战编号；刷新清图重取', async () => {
    const captcha = new CaptchaState()
    const stub = createCaptchaSourceStub()
    captcha.setReady(true)
    captcha.setSource(stub.source)
    captcha.setImageUrl('https://x/captcha.png')
    expect(captcha.imageUrl).toBe('https://x/captcha.png')
    expect(captcha.challengeId).toBe('')
    await captcha.refresh()
    expect(captcha.challengeId).toBe('c1')
    expect(captcha.imageUrl.startsWith('data:image/png;base64,')).toBe(true)
  })

  it('reset 全量复位但保留配置与注入', async () => {
    const captcha = new CaptchaState()
    const stub = createCaptchaSourceStub()
    captcha.setReady(true)
    captcha.setSource(stub.source)
    captcha.setKind('sms')
    captcha.setPhone('13800005678')
    await captcha.loadChallenge()
    captcha.startCountdown(10)
    captcha.reset()
    expect(captcha.challengeId).toBe('')
    expect(captcha.countdown).toBe(0)
    expect(captcha.phase).toBe('idle')
    expect(captcha.source).toBe(stub.source)
    expect(captcha.phone).toBe('13800005678')
    expect(captcha.ready).toBe(true)
  })
})
