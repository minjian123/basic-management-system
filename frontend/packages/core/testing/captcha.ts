/**
 * 验证码契约（`@bms/core/testing`）。
 *
 * 组件基类 / 投影 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、数据源注入与就绪、挑战获取与一次性失效刷新、短信发送与冷却倒计时、
 * 限流不重置、凭证校验与错误码、滑块轨迹提交与失败复位、阈值联动与场景策略、释放停表。
 */

import { describe, expect, it, vi } from 'vitest'

import type { CaptchaSourceAdapter, CaptchaTracePoint } from '../src'

/** 契约挑战编号（图形 / 滑块递增，供一次性失效断言）。 */
export const CAPTCHA_CONTRACT_IDS: readonly string[] = ['c1', 'c2', 'c3']

/** 契约短信目标（脱敏回显）。 */
export const CAPTCHA_CONTRACT_TARGET = '138****5678'

/** 验证码契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface CaptchaContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 形态。 */
  readonly kind: string
  /** 使用场景。 */
  readonly scene: string
  /** 挑战阶段。 */
  readonly phase: string
  /** 挑战图片（data URL）。 */
  readonly imageUrl: string
  /** 挑战编号。 */
  readonly challengeId: string
  /** 形态参数原始串。 */
  readonly payload: string
  /** 倒计时剩余秒数。 */
  readonly countdown: number
  /** 冷却配置（秒）。 */
  readonly cooldown: number
  /** 是否发送中。 */
  readonly sending: boolean
  /** 是否校验中。 */
  readonly verifying: boolean
  /** 是否校验通过。 */
  readonly passed: boolean
  /** 是否要求验证码（策略 / 阈值 / 父页面强制）。 */
  readonly needsChallenge: boolean
  /** 脱敏目标。 */
  readonly maskedTarget: string
  /** 输入最大长度。 */
  readonly inputMaxLength: number
  /** 错误码。 */
  readonly errorCode: number | undefined
  /** 错误文案。 */
  readonly errorMessage: string
  /** 生效错误文案（输入校验优先）。 */
  readonly errorText: string
  /** 受控值。 */
  readonly value: string | undefined
  /** 滑块轨迹点。 */
  readonly trace: readonly CaptchaTracePoint[]
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入 / 移除数据源。 */
  setSource(source: CaptchaSourceAdapter | undefined): void
  /** 切换形态。 */
  setKind(kind: string): void
  /** 切换场景。 */
  setScene(scene: string): void
  /** 设置手机号。 */
  setPhone(phone: string): void
  /** 设置冷却。 */
  setCooldown(seconds: number): void
  /** 设置失败计数。 */
  setFailCount(count: number): void
  /** 设置父页面强制。 */
  setRequired(value: boolean): void
  /** 设置受控值。 */
  setValue(value: string | undefined): void
  /** 取场景策略。 */
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
  /** 释放（可选；投影适配提供）。 */
  dispose?(): void
}

/** 数据源桩（记录调用轨迹与入参）。 */
export interface CaptchaSourceStub {
  /** 数据源实现。 */
  source: CaptchaSourceAdapter
  /** 调用轨迹。 */
  calls: string[]
  /** 查询入参轨迹。 */
  queries: Record<string, unknown>[]
}

/**
 * 创建验证码数据源桩（记录调用轨迹；挑战编号递增、短信返回脱敏目标与 60s 冷却、校验默认通过）。
 *
 * @param overrides 覆盖方法。
 * @returns 数据源桩。
 */
export function createCaptchaSourceStub(overrides: CaptchaSourceAdapter = {}): CaptchaSourceStub {
  const calls: string[] = []
  const queries: Record<string, unknown>[] = []
  let challengeCount = 0
  const source: CaptchaSourceAdapter = {
    challenge: async (query) => {
      calls.push('challenge')
      queries.push({ ...query })
      const captchaId = CAPTCHA_CONTRACT_IDS[challengeCount] ?? `c${challengeCount + 1}`
      challengeCount += 1
      return {
        captcha_id: captchaId,
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
      return {
        captcha_id: 's1',
        kind: 'sms',
        image: '',
        expires_in: 300,
        scene: query.scene,
        payload: '{}',
        target: CAPTCHA_CONTRACT_TARGET,
        cooldown: 60,
      }
    },
    verify: async (query) => {
      calls.push('verify')
      queries.push({ ...query })
      return { verified: true }
    },
    policy: async (query) => {
      calls.push('policy')
      queries.push({ ...query })
      return { scene: query.scene, required: false, fail_threshold: 3, ttl: 300, cooldown: 60 }
    },
    ...overrides,
  }
  return { source, calls, queries }
}

/**
 * 验证码契约（`06_04` 冻结；后续移动端复用同一套断言）。
 *
 * 目标约定：挑战编号递增（`c1` → `c2`）；短信目标 `138****5678`、冷却 60s；
 * 校验默认通过（可切换抛 20101 / 20102 / 20103）；策略 `fail_threshold=3`、`ttl=300`。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeCaptchaContract(name: string, create: () => CaptchaContractTarget): void {
  describe(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      const stub = createCaptchaSourceStub()
      target.setSource(stub.source)
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)

      await target.loadChallenge()
      await target.refresh()
      await target.sendSms()
      await target.verify()
      await target.submitSlider()
      await target.loadPolicy()
      expect(target.requestCount).toBe(0)
      expect(stub.calls).toEqual([])
      expect(target.challengeId).toBe('')
      expect(target.imageUrl).toBe('')
    })

    it('未注入数据源时不请求（就绪亦占位）', async () => {
      const target = create()
      target.setReady(true)
      await target.loadChallenge()
      await target.sendSms()
      await target.loadPolicy()
      expect(target.degraded).toBe(false)
      expect(target.requestCount).toBe(0)
      expect(target.challengeId).toBe('')
      expect(target.errorCode).toBeUndefined()
    })

    it('挑战获取：线参数、图片 data URL 与阶段落地', async () => {
      const target = create()
      const stub = createCaptchaSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setScene('bind')
      const ok = await target.loadChallenge()
      expect(ok).toBe(true)
      expect(stub.calls).toEqual(['challenge'])
      expect(stub.queries[0]).toEqual({ scene: 'bind', kind: 'image' })
      expect(target.challengeId).toBe('c1')
      expect(target.imageUrl.startsWith('data:image/png;base64,')).toBe(true)
      expect(target.phase).toBe('ready')
      expect(target.requestCount).toBe(1)
    })

    it('刷新一次性失效：旧编号清空、新编号不同', async () => {
      const target = create()
      const stub = createCaptchaSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      await target.loadChallenge()
      const first = target.challengeId
      target.setValue('abcd')
      await target.refresh()
      expect(target.challengeId).toBe('c2')
      expect(target.challengeId).not.toBe(first)
      expect(stub.calls.filter((call) => call === 'challenge')).toHaveLength(2)
    })

    it('短信发送：脱敏目标、冷却倒计时与冷却期内零请求', async () => {
      const target = create()
      const stub = createCaptchaSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('sms')
      target.setPhone('138-0000-5678')
      const ok = await target.sendSms()
      expect(ok).toBe(true)
      expect(stub.calls).toEqual(['sendSms'])
      expect(stub.queries[0]).toEqual({ phone: '13800005678', scene: 'login' })
      expect(target.maskedTarget).toBe(CAPTCHA_CONTRACT_TARGET)
      expect(target.countdown).toBe(60)
      expect(target.sending).toBe(false)

      await target.sendSms()
      expect(stub.calls).toEqual(['sendSms'])
      target.stopCountdown()
    })

    it('限流 20103：提示且不启动 / 不重置倒计时', async () => {
      const target = create()
      const stub = createCaptchaSourceStub({
        sendSms: async () => {
          throw Object.assign(new Error('too frequent'), { code: 20103 })
        },
      })
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('sms')
      target.setPhone('13800005678')
      const ok = await target.sendSms()
      expect(ok).toBe(false)
      expect(target.errorCode).toBe(20103)
      expect(target.errorMessage).toBe('发送过于频繁，请稍后再试')
      expect(target.countdown).toBe(0)
    })

    it('倒计时：步进到零停表', () => {
      const target = create()
      target.startCountdown(2)
      expect(target.countdown).toBe(2)
      target.tickCountdown()
      expect(target.countdown).toBe(1)
      target.tickCountdown()
      expect(target.countdown).toBe(0)
      target.stopCountdown()
    })

    it('凭证校验：通过 / 输入非法零请求 / 错误码 20101 与失效', async () => {
      const passed = create()
      const stub = createCaptchaSourceStub()
      passed.setReady(true)
      passed.setSource(stub.source)
      await passed.loadChallenge()
      passed.setValue('ab12')
      const ok = await passed.verify()
      expect(ok).toBe(true)
      expect(passed.passed).toBe(true)
      expect(passed.phase).toBe('passed')
      expect(stub.queries.at(-1)).toEqual({ captchaId: 'c1', kind: 'image', code: 'ab12', scene: 'login' })

      const invalid = create()
      const invalidStub = createCaptchaSourceStub()
      invalid.setReady(true)
      invalid.setSource(invalidStub.source)
      await invalid.loadChallenge()
      invalid.setValue('')
      expect(await invalid.verify()).toBe(false)
      expect(invalidStub.calls).toEqual(['challenge'])
      expect(invalid.errorText).not.toBe('')

      const failed = create()
      const failedStub = createCaptchaSourceStub({
        verify: async () => {
          throw Object.assign(new Error('mismatch'), { code: 20101 })
        },
      })
      failed.setReady(true)
      failed.setSource(failedStub.source)
      await failed.loadChallenge()
      failed.setValue('zzzz')
      expect(await failed.verify()).toBe(false)
      expect(failed.errorCode).toBe(20101)
      expect(failed.errorMessage).toBe('验证码错误')
      expect(failed.passed).toBe(false)
      expect(failed.challengeId).toBe('')
    })

    it('滑块：轨迹归一提交、不足点数拒绝、失败复位', async () => {
      const target = create()
      const stub = createCaptchaSourceStub()
      target.setReady(true)
      target.setSource(stub.source)
      target.setKind('slider')
      await target.loadChallenge()
      expect(target.trace).toEqual([])
      expect(await target.submitSlider()).toBe(false)
      expect(stub.calls).toEqual(['challenge'])

      target.pushTrace({ x: 0, y: 0, t: 0 })
      target.pushTrace({ x: 82.4, y: 3.6, t: 120 })
      const ok = await target.submitSlider()
      expect(ok).toBe(true)
      expect(target.passed).toBe(true)
      expect(stub.queries.at(-1)).toEqual({
        captchaId: 'c1',
        kind: 'slider',
        trace: [
          { x: 0, y: 0, t: 0 },
          { x: 82, y: 4, t: 120 },
        ],
        scene: 'login',
      })

      const failed = create()
      const failedStub = createCaptchaSourceStub({
        verify: async () => {
          throw Object.assign(new Error('slider'), { code: 20101 })
        },
      })
      failed.setReady(true)
      failed.setSource(failedStub.source)
      failed.setKind('slider')
      await failed.loadChallenge()
      failed.pushTrace({ x: 0, y: 0, t: 0 })
      failed.pushTrace({ x: 10, y: 0, t: 30 })
      expect(await failed.submitSlider()).toBe(false)
      expect(failed.trace).toEqual([])
      expect(failed.passed).toBe(false)
      expect(failed.errorCode).toBe(20101)
    })

    it('阈值联动与场景策略', async () => {
      const target = create()
      const stub = createCaptchaSourceStub({
        policy: async (query) => ({
          scene: query.scene,
          required: true,
          fail_threshold: 5,
          ttl: 120,
          cooldown: 30,
        }),
      })
      target.setReady(true)
      target.setSource(stub.source)
      expect(target.needsChallenge).toBe(false)
      target.setFailCount(3)
      expect(target.needsChallenge).toBe(true)
      target.setFailCount(0)
      target.setRequired(true)
      expect(target.needsChallenge).toBe(true)
      target.setRequired(false)

      await target.loadPolicy()
      expect(target.requestCount).toBe(1)
      expect(target.needsChallenge).toBe(true)
      expect(target.cooldown).toBe(30)
    })

    it('竞态：旧挑战响应不覆盖新响应', async () => {
      let releaseFirst: ((value: unknown) => void) | undefined
      let round = 0
      const stub = createCaptchaSourceStub({
        challenge: async () => {
          round += 1
          if (round === 1) {
            return new Promise((resolve) => {
              releaseFirst = resolve
            })
          }
          return { captcha_id: 'c2', kind: 'image', image: '', expires_in: 300, payload: '{}' }
        },
      })
      const target = create()
      target.setReady(true)
      target.setSource(stub.source)
      const first = target.loadChallenge()
      const second = target.loadChallenge()
      expect(await second).toBe(true)
      expect(target.challengeId).toBe('c2')
      releaseFirst?.({ captcha_id: 'c1', kind: 'image', image: '', expires_in: 300, payload: '{}' })
      await first
      expect(target.challengeId).toBe('c2')
    })

    it('释放后倒计时停表', () => {
      const target = create()
      if (target.dispose === undefined) {
        return
      }
      vi.useFakeTimers()
      try {
        target.startCountdown(3)
        expect(target.countdown).toBe(3)
        vi.advanceTimersByTime(1100)
        expect(target.countdown).toBe(2)
        target.dispose()
        vi.advanceTimersByTime(3000)
        expect(target.countdown).toBe(2)
      } finally {
        vi.useRealTimers()
        target.stopCountdown()
      }
    })
  })
}
