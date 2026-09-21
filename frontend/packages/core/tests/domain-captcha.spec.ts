// kiwi_id: 966
/** 验证码领域纯函数用例（06_04）：归一 / 脱敏 / 校验 / 阈值 / 倒计时 / 轨迹 / 图片 / 错误码 / 策略。 */

import { describe, expect, it } from 'vitest'

import {
  CAPTCHA_ERROR_TEXTS,
  CAPTCHA_FAIL_THRESHOLD,
  CAPTCHA_IMAGE_MAX_LENGTH,
  CAPTCHA_IMAGE_MIN_LENGTH,
  CAPTCHA_KINDS,
  CAPTCHA_SCENES,
  CAPTCHA_SMS_COOLDOWN,
  CAPTCHA_SMS_LENGTH,
  CAPTCHA_TTL,
  buildCaptchaChallengeQuery,
  buildCaptchaSmsQuery,
  buildCaptchaTrace,
  buildCaptchaVerifyQuery,
  captchaImageUrl,
  captchaInputHint,
  captchaKindText,
  checkCaptchaInput,
  clampCaptchaSeconds,
  countdownText,
  defaultCaptchaPolicy,
  isCaptchaErrorCode,
  maskCaptchaPhone,
  nextCountdown,
  normalizeCaptchaChallenge,
  normalizeCaptchaKind,
  normalizeCaptchaPhone,
  normalizeCaptchaPolicy,
  normalizeCaptchaScene,
  normalizeCaptchaTrace,
  parseCaptchaSliderParams,
  resolveCaptchaErrorText,
  shouldRequireCaptcha,
} from '../src'

describe('domain/captcha 常量与枚举', () => {
  it('与后端同源：有效期 / 冷却 / 阈值 / 长度 / 场景', () => {
    expect(CAPTCHA_TTL).toBe(300)
    expect(CAPTCHA_SMS_COOLDOWN).toBe(60)
    expect(CAPTCHA_FAIL_THRESHOLD).toBe(3)
    expect(CAPTCHA_IMAGE_MIN_LENGTH).toBe(4)
    expect(CAPTCHA_IMAGE_MAX_LENGTH).toBe(6)
    expect(CAPTCHA_SMS_LENGTH).toBe(6)
    expect(CAPTCHA_KINDS).toEqual(['image', 'slider', 'sms'])
    expect(CAPTCHA_SCENES).toEqual(['login', 'reset_password', 'bind', 'unbind', 'register'])
    expect(CAPTCHA_ERROR_TEXTS[20101]).toBe('验证码错误')
  })
})

describe('形态 / 场景归一', () => {
  it('合法值透传，非法与空值回落 undefined', () => {
    expect(normalizeCaptchaKind('slider')).toBe('slider')
    expect(normalizeCaptchaKind('unknown')).toBeUndefined()
    expect(normalizeCaptchaKind(1)).toBeUndefined()
    expect(normalizeCaptchaScene('reset_password')).toBe('reset_password')
    expect(normalizeCaptchaScene('')).toBeUndefined()
  })
})

describe('normalizeCaptchaChallenge', () => {
  it('兼容 snake_case 并组装 data URL', () => {
    const challenge = normalizeCaptchaChallenge({
      captcha_id: 'c1',
      kind: 'image',
      image: 'iVBORw0KGgo=',
      expires_in: 120,
      scene: 'bind',
      payload: '{"gap_x":10}',
      target: '',
      cooldown: 0,
    })
    expect(challenge).toEqual({
      captchaId: 'c1',
      kind: 'image',
      image: 'data:image/png;base64,iVBORw0KGgo=',
      expiresIn: 120,
      scene: 'bind',
      payload: '{"gap_x":10}',
      target: '',
      cooldown: 0,
    })
  })

  it('缺编号剔除；缺省字段回落请求侧与常量', () => {
    expect(normalizeCaptchaChallenge({ kind: 'image' })).toBeUndefined()
    expect(normalizeCaptchaChallenge(null)).toBeUndefined()
    const fallback = normalizeCaptchaChallenge({ captcha_id: 's1', kind: 'sms' }, { scene: 'register', kind: 'image' })
    expect(fallback?.scene).toBe('register')
    expect(fallback?.kind).toBe('sms')
    expect(fallback?.expiresIn).toBe(CAPTCHA_TTL)
    expect(fallback?.cooldown).toBe(CAPTCHA_SMS_COOLDOWN)
  })

  it('空图片保留空串（占位未出图）', () => {
    const challenge = normalizeCaptchaChallenge({ captcha_id: 'c1', image: '' })
    expect(challenge?.image).toBe('')
  })
})

describe('captchaImageUrl', () => {
  it('base64 组装 / 前缀原样 / 非法空串', () => {
    expect(captchaImageUrl('AAAA')).toBe('data:image/png;base64,AAAA')
    expect(captchaImageUrl('data:image/png;base64,AAAA')).toBe('data:image/png;base64,AAAA')
    expect(captchaImageUrl('https://x/y.png')).toBe('https://x/y.png')
    expect(captchaImageUrl('blob:http://x')).toBe('blob:http://x')
    expect(captchaImageUrl('')).toBe('')
    expect(captchaImageUrl(undefined)).toBe('')
  })
})

describe('手机号归一与脱敏', () => {
  it('去分隔符；保留前 3 后 4；不足 8 位保留前 3；空即空', () => {
    expect(normalizeCaptchaPhone('138-0000-5678')).toBe('13800005678')
    expect(normalizeCaptchaPhone(' 138 0000 5678 ')).toBe('13800005678')
    expect(maskCaptchaPhone('13800005678')).toBe('138****5678')
    expect(maskCaptchaPhone('1234567')).toBe('123****')
    expect(maskCaptchaPhone('')).toBe('')
  })
})

describe('checkCaptchaInput', () => {
  it('空值 / 长度 / 字符集与定长覆盖', () => {
    expect(checkCaptchaInput('', 'image').valid).toBe(false)
    expect(checkCaptchaInput('ab', 'image').message).toBe('请输入 4-6 位验证码')
    expect(checkCaptchaInput('ab1', 'image').valid).toBe(false)
    expect(checkCaptchaInput('ab12', 'image').valid).toBe(true)
    expect(checkCaptchaInput('ab1-2', 'image').valid).toBe(false)
    expect(checkCaptchaInput('123456', 'sms').valid).toBe(true)
    expect(checkCaptchaInput('12345', 'sms').valid).toBe(false)
    expect(checkCaptchaInput('12345a', 'sms').valid).toBe(false)
    expect(checkCaptchaInput('abc', 'image', 3).valid).toBe(true)
    expect(checkCaptchaInput('abcd', 'image', 3).valid).toBe(false)
    expect(checkCaptchaInput('anything', 'slider').valid).toBe(true)
    expect(captchaInputHint('sms')).toBe('请输入 6 位短信验证码')
    expect(captchaInputHint('image', 5)).toBe('请输入 5 位验证码')
  })
})

describe('阈值与倒计时', () => {
  it('失败阈值：达阈值强制；非法阈值不强制', () => {
    expect(shouldRequireCaptcha(2)).toBe(false)
    expect(shouldRequireCaptcha(3)).toBe(true)
    expect(shouldRequireCaptcha(5, 5)).toBe(true)
    expect(shouldRequireCaptcha(99, 0)).toBe(false)
  })

  it('步进 / 夹取 / 文案', () => {
    expect(nextCountdown(2)).toBe(1)
    expect(nextCountdown(0)).toBe(0)
    expect(nextCountdown(-1)).toBe(0)
    expect(clampCaptchaSeconds(30.9, 60)).toBe(30)
    expect(clampCaptchaSeconds('45', 60)).toBe(45)
    expect(clampCaptchaSeconds(0, 60)).toBe(60)
    expect(clampCaptchaSeconds('bad', 60)).toBe(60)
    expect(countdownText(59)).toBe('59s')
    expect(countdownText(-2)).toBe('0s')
  })
})

describe('滑块参数与轨迹', () => {
  it('payload JSON 容错与别名', () => {
    expect(parseCaptchaSliderParams('')).toEqual({})
    expect(parseCaptchaSliderParams('not-json')).toEqual({})
    expect(parseCaptchaSliderParams('[1,2]')).toEqual({})
    expect(parseCaptchaSliderParams('{"bg":"AAAA","gap_x":12.5,"gap_y":30,"w":320,"h":160}')).toEqual({
      background: 'data:image/png;base64,AAAA',
      gapX: 13,
      gapY: 30,
      width: 320,
      height: 160,
    })
  })

  it('轨迹归一兼容数组与对象、剔除非法点；提交形态为 [x, y, t]', () => {
    expect(normalizeCaptchaTrace([[0, 0, 0], { x: 10.4, y: 2, t: 50 }, ['bad'], null])).toEqual([
      { x: 0, y: 0, t: 0 },
      { x: 10, y: 2, t: 50 },
    ])
    expect(normalizeCaptchaTrace('bad')).toEqual([])
    expect(buildCaptchaTrace([{ x: 1.6, y: 2.4, t: 30.5 }])).toEqual([[2, 2, 31]])
  })
})

describe('线参数构造', () => {
  it('出题 / 短信 / 校验（snake_case 与轨迹）', () => {
    expect(buildCaptchaChallengeQuery({ scene: 'bind', kind: 'slider' })).toEqual({ scene: 'bind', kind: 'slider' })
    expect(buildCaptchaChallengeQuery({ scene: 'bad', kind: 'bad' })).toEqual({ scene: 'login', kind: 'image' })
    expect(buildCaptchaSmsQuery({ phone: '138-0000-5678', scene: 'login' })).toEqual({
      phone: '13800005678',
      scene: 'login',
    })
    expect(
      buildCaptchaVerifyQuery({
        captchaId: 'c1',
        kind: 'slider',
        code: '',
        trace: [{ x: 0, y: 0, t: 0 }, { x: 80, y: 4, t: 120 }],
        scene: 'login',
      }),
    ).toEqual({
      captcha_id: 'c1',
      kind: 'slider',
      code: '',
      trace: [
        [0, 0, 0],
        [80, 4, 120],
      ],
      scene: 'login',
    })
  })
})

describe('错误码与策略', () => {
  it('错误码判定与文案', () => {
    expect(isCaptchaErrorCode(20101)).toBe(true)
    expect(isCaptchaErrorCode(20103)).toBe(true)
    expect(isCaptchaErrorCode(40001)).toBe(false)
    expect(isCaptchaErrorCode('20101')).toBe(false)
    expect(resolveCaptchaErrorText(20102)).toBe('验证码已失效，请重新获取')
    expect(resolveCaptchaErrorText(99999)).toBe('验证码校验失败，请重试')
  })

  it('默认策略：登录不强制、其余场景强制与常量同源', () => {
    expect(defaultCaptchaPolicy()).toEqual({
      scene: 'login',
      required: false,
      failThreshold: 3,
      ttl: 300,
      cooldown: 60,
    })
    expect(defaultCaptchaPolicy('bind').required).toBe(true)
    expect(defaultCaptchaPolicy('unknown').required).toBe(true)
  })

  it('策略归一：兼容 fail_threshold 与缺省回落', () => {
    expect(normalizeCaptchaPolicy({ scene: 'login', required: true, fail_threshold: 5, ttl: 120, cooldown: 30 })).toEqual({
      scene: 'login',
      required: true,
      failThreshold: 5,
      ttl: 120,
      cooldown: 30,
    })
    expect(normalizeCaptchaPolicy(undefined, 'reset_password')).toEqual(defaultCaptchaPolicy('reset_password'))
  })

  it('形态文案', () => {
    expect(captchaKindText('image')).toBe('图形验证码')
    expect(captchaKindText('slider')).toBe('滑块验证')
    expect(captchaKindText('sms')).toBe('短信验证码')
  })
})
