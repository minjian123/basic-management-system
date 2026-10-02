// kiwi_id: 2232
/** 登录页纯函数用例（05_01）：策略渠道选形（跳过 sms）、租户归一、凭证归一（含滑块轨迹）。 */

import { describe, expect, it, vi } from 'vitest'

import { normalizeLoginTenant, pickLoginCaptchaKind, toLoginCaptcha } from '@/utils/login'
import { redirectTo } from '@/utils/navigation'

describe('登录页纯函数（Kiwi 2232）', () => {
  it('pickLoginCaptchaKind 取首个可渲染形态（slider 优先、跳过 sms、image 兜底）', () => {
    expect(pickLoginCaptchaKind(['slider', 'image'])).toBe('slider')
    expect(pickLoginCaptchaKind(['sms', 'image'])).toBe('image')
    expect(pickLoginCaptchaKind(['sms', 'slider', 'image'])).toBe('slider')
    expect(pickLoginCaptchaKind(['image'])).toBe('image')
    expect(pickLoginCaptchaKind(['image', 'slider'])).toBe('image')
  })

  it('pickLoginCaptchaKind 无可渲染渠道返回 null', () => {
    expect(pickLoginCaptchaKind(['sms'])).toBeNull()
    expect(pickLoginCaptchaKind([])).toBeNull()
    expect(pickLoginCaptchaKind(undefined)).toBeNull()
  })

  it('normalizeLoginTenant 去首尾空白；空串与未填视为不携带', () => {
    expect(normalizeLoginTenant(' acme ')).toBe('acme')
    expect(normalizeLoginTenant('acme')).toBe('acme')
    expect(normalizeLoginTenant('   ')).toBeNull()
    expect(normalizeLoginTenant('')).toBeNull()
    expect(normalizeLoginTenant(undefined)).toBeNull()
  })

  it('toLoginCaptcha 图形 / 短信带 code，滑块把轨迹点转二元组', () => {
    expect(toLoginCaptcha({ kind: 'image', captchaId: 'c1', code: 'ab12' })).toEqual({
      captcha_id: 'c1',
      kind: 'image',
      code: 'ab12',
    })
    expect(toLoginCaptcha({ kind: 'sms', captchaId: 's1', code: '123456' })).toEqual({
      captcha_id: 's1',
      kind: 'sms',
      code: '123456',
    })
    expect(
      toLoginCaptcha({
        kind: 'slider',
        captchaId: 'c2',
        trace: [
          { x: 0, y: 0, t: 0 },
          { x: 96, y: 2, t: 140 },
        ],
      }),
    ).toEqual({
      captcha_id: 'c2',
      kind: 'slider',
      code: '',
      trace: [
        [0, 0, 0],
        [96, 2, 140],
      ],
    })
  })

  it('toLoginCaptcha 滑块无轨迹时不带 trace（契约字段只产出不校验）', () => {
    expect(toLoginCaptcha({ kind: 'slider', captchaId: 'c3' })).toEqual({
      captcha_id: 'c3',
      kind: 'slider',
      code: '',
    })
  })

  it('redirectTo 走顶层地址跳转（浏览器 API 单一落点）', () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { assign })

    redirectTo('/api/identity/v1/auth/sso/keycloak/authorize')

    expect(assign).toHaveBeenCalledWith('/api/identity/v1/auth/sso/keycloak/authorize')
    vi.unstubAllGlobals()
  })
})
