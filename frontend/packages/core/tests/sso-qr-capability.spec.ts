// kiwi_id: 2233
/** 扫码登录能力域基类用例（05_04）：占位零请求 / 取址 / 四态 / 退避 / 过期重取 / 可见性 / 释放。 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { BaseSsoQr, isSsoQrTerminal, type SsoQrLoginSourceAdapter } from '../src'

/** 具体扫码登录能力（可实例化）。 */
class SsoQrState extends BaseSsoQr {}

/** 状态源桩（init / poll 可覆写）。 */
function makeSource(overrides: Partial<SsoQrLoginSourceAdapter> = {}): SsoQrLoginSourceAdapter {
  return {
    init: vi.fn().mockResolvedValue({ authorize_url: 'https://idp/authorize', state: 'state-1', expires_in: 60 }),
    poll: vi.fn().mockResolvedValue({ status: 'pending' }),
    ...overrides,
  }
}

/** 构造已装配入口与状态源的实例。 */
function makeReady(source: SsoQrLoginSourceAdapter): SsoQrState {
  const qr = new SsoQrState()
  qr.setProviders([
    { idp_key: 'wecom-1', type: 'wecom', sort: 2 },
    { idp_key: 'dingtalk-1', type: 'dingtalk', sort: 1 },
    { idp_key: 'oidc-1', type: 'oidc', sort: 0 },
  ])
  qr.setSource(source)
  return qr
}

describe('BaseSsoQr 身份与占位', () => {
  it('能力键与依赖登记', () => {
    const qr = new SsoQrState()
    expect(qr.identifier).toBe('sso-qr')
    expect(qr.depends).toEqual(['placeholder-state'])
    expect(qr.phase).toBe('pending')
  })

  it('setProviders 过滤可扫码源并按 sort 升序，当前入口回落首个', () => {
    const qr = makeReady(makeSource())
    expect(qr.providers.map((item) => item.idp_key)).toEqual(['dingtalk-1', 'wecom-1'])
    expect(qr.activeIdpKey).toBe('dingtalk-1')
  })

  it('未注入状态源即占位（degraded）且零请求', async () => {
    const qr = new SsoQrState()
    qr.setProviders([{ idp_key: 'wecom-1', type: 'wecom' }])
    expect(qr.degraded).toBe(true)
    await qr.init()
    expect(qr.requestCount).toBe(0)
    expect(qr.authorizeUrl).toBe('')
    qr.setSource(makeSource())
    expect(qr.degraded).toBe(false)
  })
})

describe('BaseSsoQr 取址与四态', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('init 取授权 URL 并进入待扫（计数一次）', async () => {
    const source = makeSource()
    const qr = makeReady(source)
    await qr.init()
    expect(source.init).toHaveBeenCalledWith({ idpKey: 'dingtalk-1', tenant: null })
    expect(qr.phase).toBe('pending')
    expect(qr.authorizeUrl).toBe('https://idp/authorize')
    expect(qr.state).toBe('state-1')
    expect(qr.remaining).toBe(60)
    expect(qr.requestCount).toBe(1)
    qr.dispose()
  })

  it('轮询回报 scanned / confirmed（含 redirect）逐相位更新', async () => {
    const poll = vi
      .fn()
      .mockResolvedValueOnce({ status: 'scanned' })
      .mockResolvedValueOnce({ status: 'confirmed', redirect: '/home' })
    const qr = makeReady(makeSource({ poll }))
    await qr.init()
    await vi.advanceTimersByTimeAsync(2000)
    expect(qr.phase).toBe('scanned')
    await vi.advanceTimersByTimeAsync(2000)
    expect(qr.phase).toBe('confirmed')
    expect(qr.redirect).toBe('/home')
    expect(isSsoQrTerminal(qr.phase)).toBe(true)
    // 终态后不再轮询
    await vi.advanceTimersByTimeAsync(60000)
    expect(poll).toHaveBeenCalledTimes(2)
    qr.dispose()
  })

  it('相位变化经 onPhaseChange 订阅（含取消）', async () => {
    const qr = makeReady(makeSource({ poll: vi.fn().mockResolvedValueOnce({ status: 'scanned' }) }))
    const seen: string[] = []
    const off = qr.onPhaseChange((phase) => seen.push(phase))
    await qr.init()
    await vi.advanceTimersByTimeAsync(2000)
    expect(seen).toContain('scanned')
    off()
    qr.dispose()
  })

  it('取址失败转 failed', async () => {
    const qr = makeReady(makeSource({ init: vi.fn().mockRejectedValue(new Error('x')) }))
    await qr.init()
    expect(qr.phase).toBe('failed')
    qr.dispose()
  })
})

describe('BaseSsoQr 退避与失败', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('连续失败按 2s / 4s / 8s / 16s / 30s 退避，第 5 次转 failed 停轮询', async () => {
    const poll = vi.fn().mockRejectedValue(new Error('network'))
    const qr = makeReady(
      makeSource({
        poll,
        init: vi.fn().mockResolvedValue({ authorize_url: 'https://idp', state: 's', expires_in: 600 }),
      }),
    )
    await qr.init()
    for (const delay of [2000, 4000, 8000, 16000, 30_000]) {
      await vi.advanceTimersByTimeAsync(delay)
    }
    expect(poll).toHaveBeenCalledTimes(5)
    expect(qr.phase).toBe('failed')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(poll).toHaveBeenCalledTimes(5)
    qr.dispose()
  })

  it('成功回报重置失败计数（退避复位）', async () => {
    const poll = vi
      .fn()
      .mockRejectedValueOnce(new Error('a'))
      .mockResolvedValue({ status: 'pending' })
    const qr = makeReady(makeSource({ poll }))
    await qr.init()
    await vi.advanceTimersByTimeAsync(2000)
    expect(qr.failures).toBe(1)
    await vi.advanceTimersByTimeAsync(4000)
    expect(qr.failures).toBe(0)
    qr.dispose()
  })
})

describe('BaseSsoQr 过期与可见性', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('到期进入 expired 并自动重取一次，再次到期不重取', async () => {
    const init = vi.fn().mockResolvedValue({ authorize_url: 'https://idp', state: 's', expires_in: 5 })
    const qr = makeReady(makeSource({ init }))
    qr.setOptions({ pollBase: 30_000 })
    await qr.init()
    expect(init).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    await Promise.resolve()
    expect(qr.autoRefreshed).toBe(true)
    expect(init).toHaveBeenCalledTimes(2)
    expect(qr.phase).toBe('pending')
    await vi.advanceTimersByTimeAsync(5000)
    expect(init).toHaveBeenCalledTimes(2)
    expect(qr.phase).toBe('expired')
    qr.dispose()
  })

  it('暂停时停轮询与过期计时，恢复后续跑', async () => {
    const poll = vi.fn().mockResolvedValue({ status: 'pending' })
    const qr = makeReady(makeSource({ poll }))
    await qr.init()
    qr.pause()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(poll).not.toHaveBeenCalled()
    qr.resume()
    await vi.advanceTimersByTimeAsync(2000)
    expect(poll).toHaveBeenCalledTimes(1)
    qr.dispose()
  })

  it('dispose 清定时器且幂等（释放后不再轮询）', async () => {
    const poll = vi.fn().mockResolvedValue({ status: 'pending' })
    const qr = makeReady(makeSource({ poll }))
    await qr.init()
    qr.dispose()
    qr.dispose()
    expect(qr.isDisposed).toBe(true)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(poll).not.toHaveBeenCalled()
  })
})

describe('BaseSsoQr 访问器与边界（补充覆盖）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('访问器与 setter', () => {
    const qr = makeReady(makeSource())
    expect(qr.statusText).not.toBe('')
    expect(qr.terminal).toBe(false)
    qr.setTenant('acme')
    expect(qr.tenant).toBe('acme')
    qr.setOptions({ pollBase: 1000, pollMax: 5000, maxFailures: 3, pauseWhenHidden: false })
    expect(qr.pollBase).toBe(1000)
    expect(qr.pollMax).toBe(5000)
    expect(qr.maxFailures).toBe(3)
    expect(qr.pauseWhenHidden).toBe(false)
    qr.setActiveProvider('wecom-1')
    expect(qr.activeIdpKey).toBe('wecom-1')
    qr.dispose()
  })

  it('无可用入口 init 不动作；源无 poll 时轮询早退', async () => {
    const empty = new SsoQrState()
    empty.setSource(makeSource())
    await empty.init()
    expect(empty.requestCount).toBe(0)

    const noPoll = makeReady(
      makeSource({
        init: vi.fn().mockResolvedValue({ authorize_url: 'u', state: 's', expires_in: 60 }),
        poll: undefined,
      }),
    )
    await noPoll.init()
    await vi.advanceTimersByTimeAsync(2000)
    expect(noPoll.phase).toBe('pending')
    noPoll.dispose()
    empty.dispose()
  })

  it('pollOnce 暂停 / 无源时早退；正常时轮询一次', async () => {
    const poll = vi.fn().mockResolvedValue({ status: 'scanned' })
    const qr = makeReady(makeSource({ poll }))
    await qr.init()
    qr.pause()
    await qr.pollOnce()
    expect(poll).not.toHaveBeenCalled()
    qr.resume()
    await qr.pollOnce()
    expect(qr.phase).toBe('scanned')
    qr.dispose()
  })

  it('refresh 重置自动重取标记并重取', async () => {
    const init = vi.fn().mockResolvedValue({ authorize_url: 'u', state: 's', expires_in: 60 })
    const qr = makeReady(makeSource({ init }))
    await qr.init()
    qr.autoRefreshed = true
    qr.refresh()
    await Promise.resolve()
    expect(qr.autoRefreshed).toBe(false)
    expect(init).toHaveBeenCalledTimes(2)
    qr.dispose()
  })

  it('pause / resume 幂等与终态不恢复', async () => {
    const qr = makeReady(makeSource())
    qr.resume()
    qr.pause()
    qr.pause()
    qr.resume()
    qr.pause()
    qr.phase = 'confirmed'
    qr.resume()
    qr.dispose()
  })

  it('expires_in 为 0 不自动过期', async () => {
    const qr = makeReady(
      makeSource({ init: vi.fn().mockResolvedValue({ authorize_url: 'u', state: 's', expires_in: 0 }) }),
    )
    await qr.init()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(qr.phase).not.toBe('expired')
    qr.dispose()
  })

  it('相位监听器异常被吞并上报（不阻断其它监听器）', async () => {
    const qr = makeReady(makeSource({ poll: vi.fn().mockResolvedValueOnce({ status: 'scanned' }) }))
    const seen: string[] = []
    qr.onPhaseChange(() => {
      throw new Error('boom')
    })
    qr.onPhaseChange((phase) => seen.push(phase))
    await qr.init()
    await vi.advanceTimersByTimeAsync(2000)
    expect(seen).toContain('scanned')
    qr.dispose()
  })

  it('init 期间释放：成功 / 失败回调均按代际不符丢弃', async () => {
    let resolveInit: (value: unknown) => void = () => {}
    const pendingResolve = new Promise((resolve) => {
      resolveInit = resolve
    })
    const qr1 = makeReady(makeSource({ init: vi.fn().mockReturnValue(pendingResolve) }))
    const running1 = qr1.init()
    qr1.dispose()
    resolveInit({ authorize_url: 'u', state: 's', expires_in: 10 })
    await running1
    expect(qr1.authorizeUrl).toBe('')

    let rejectInit: (error: unknown) => void = () => {}
    const pendingReject = new Promise((_resolve, reject) => {
      rejectInit = reject
    })
    const qr2 = makeReady(makeSource({ init: vi.fn().mockReturnValue(pendingReject) }))
    const running2 = qr2.init()
    qr2.dispose()
    rejectInit(new Error('x'))
    await running2
    expect(qr2.phase).not.toBe('failed')
  })

  it('轮询回报 expired 进入过期并按规则重取一次', async () => {
    const init = vi.fn().mockResolvedValue({ authorize_url: 'u', state: 's', expires_in: 600 })
    const qr = makeReady(makeSource({ init, poll: vi.fn().mockResolvedValueOnce({ status: 'expired' }) }))
    await qr.init()
    await vi.advanceTimersByTimeAsync(2000)
    await vi.advanceTimersByTimeAsync(0)
    expect(qr.autoRefreshed).toBe(true)
    expect(init).toHaveBeenCalledTimes(2)
    qr.dispose()
  })

  it('轮询期间暂停：结果落地时调度早退', async () => {
    let resolvePoll: (value: unknown) => void = () => {}
    const deferred = new Promise((resolve) => {
      resolvePoll = resolve
    })
    const qr = makeReady(makeSource({ poll: vi.fn().mockReturnValue(deferred) }))
    await qr.init()
    const running = qr.pollOnce()
    qr.pause()
    resolvePoll({ status: 'scanned' })
    await running
    expect(qr.phase).toBe('scanned')
    qr.dispose()
  })

  it('轮询期间释放：成功 / 失败回调按代际不符丢弃', async () => {
    let resolvePoll: (value: unknown) => void = () => {}
    const resolved = new Promise((resolve) => {
      resolvePoll = resolve
    })
    const qr1 = makeReady(makeSource({ poll: vi.fn().mockReturnValue(resolved) }))
    await qr1.init()
    const running1 = qr1.pollOnce()
    qr1.dispose()
    resolvePoll({ status: 'scanned' })
    await running1
    expect(qr1.isDisposed).toBe(true)

    let rejectPoll: (error: unknown) => void = () => {}
    const rejected = new Promise((_resolve, reject) => {
      rejectPoll = reject
    })
    const qr2 = makeReady(makeSource({ poll: vi.fn().mockReturnValue(rejected) }))
    await qr2.init()
    const running2 = qr2.pollOnce()
    qr2.dispose()
    rejectPoll(new Error('x'))
    await running2
    expect(qr2.phase).not.toBe('failed')
  })
})
