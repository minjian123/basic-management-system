/** 根系基类用例（Kiwi 699）：通用字段 / 配置解析 / 日志与错误上报 / i18n / 生命周期钩子 / 组件包装。 */

import { effectScope, h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BaseFrontend,
  configureFrontendBase,
  getFrontendRuntimeConfig,
  resetFrontendBaseConfig,
  setFrontendSinks,
  type ErrorRecord,
  type FrontendBaseOptions,
  type LogRecord,
} from '@/base/BaseFrontend'
import BaseFrontendWrapper from '@/base/BaseFrontend.vue'
import { useFrontendBase, type UseFrontendBaseReturn } from '@/base/useFrontendBase'

import { mountWithPlugins } from './helpers/mount'

/** 记录 sink 产物（并清空上一条用例注入的 sink） */
function createRecorder() {
  const logs: LogRecord[] = []
  const errors: ErrorRecord[] = []
  setFrontendSinks({
    log: (record) => logs.push(record),
    error: (record) => errors.push(record),
  })
  return { logs, errors }
}

/**
 * 演示子类：钩子在基类构造内触发，此时子类字段初始化器尚未执行，
 * 故用闭包数组记录而非子类字段。
 */
function createDemo(options?: FrontendBaseOptions) {
  const hooks: string[] = []
  class DemoFrontend extends BaseFrontend {
    protected override onBaseCreated(): void {
      hooks.push('created')
    }

    protected override onBaseDisposed(): void {
      hooks.push('disposed')
    }
  }
  return { instance: new DemoFrontend(options), hooks }
}

describe('根系基类（Kiwi 699）', () => {
  beforeEach(() => {
    resetFrontendBaseConfig()
    setFrontendSinks({ log: undefined, error: undefined })
    vi.useRealTimers()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
    resetFrontendBaseConfig()
  })

  it('通用字段：命名空间与实例标识取默认与显式值', () => {
    expect(createDemo().instance.ns).toBe('bms')
    expect(createDemo().instance.identifier).toBe('bms')

    const { instance } = createDemo({ ns: 'demo', identifier: 'demo-1' })
    expect(instance.ns).toBe('demo')
    expect(instance.identifier).toBe('demo-1')

    expect(createDemo({ ns: '  ' }).instance.ns).toBe('bms')
    expect(createDemo({ ns: 'demo' }).instance.identifier).toBe('demo')
  })

  it('env 与 config 实时读运行期配置，且 config 按命名空间解析并冻结', () => {
    const { instance } = createDemo({ ns: 'demo' })
    expect(instance.env).toBe('dev')

    configureFrontendBase({
      env: 'prod',
      values: { 'app.title': '全局标题', 'demo.title': '局部标题', 'demo.size': 3 },
    })
    expect(instance.env).toBe('prod')

    const config = instance.config
    expect(config['app.title']).toBe('全局标题')
    expect(config.title).toBe('局部标题')
    expect(config['demo.title']).toBeUndefined()
    expect(Object.isFrozen(config)).toBe(true)

    expect(instance.getConfig('title')).toBe('局部标题')
    expect(instance.getConfig('size')).toBe(3)
    expect(instance.getConfig('missing')).toBeUndefined()
    expect(instance.getConfig('missing', 'fallback')).toBe('fallback')
  })

  it('构建期解析：VITE_APP_ENV 合法值生效、非法值回退、VITE_* 键名归一', () => {
    vi.stubEnv('VITE_DEMO_KEY', 'v1')
    vi.stubEnv('VITE_APP_ENV', 'test')
    resetFrontendBaseConfig()
    expect(getFrontendRuntimeConfig().env).toBe('test')
    expect(getFrontendRuntimeConfig().values['demo-key']).toBe('v1')
    expect(getFrontendRuntimeConfig().values['app-env']).toBeUndefined()

    vi.stubEnv('VITE_APP_ENV', 'weird')
    resetFrontendBaseConfig()
    expect(getFrontendRuntimeConfig().env).toBe('dev')

    configureFrontendBase({ env: 'prod' })
    expect(getFrontendRuntimeConfig().env).toBe('prod')
  })

  it('log 分级过滤并输出结构化记录', () => {
    const { logs } = createRecorder()
    const { instance } = createDemo({ ns: 'demo' })
    configureFrontendBase({ logLevel: 'warn' })

    instance.log('debug', 'debug-1')
    instance.log('info', 'info-1')
    expect(logs).toHaveLength(0)

    instance.log('warn', 'warn-1', { code: 1 })
    expect(logs).toHaveLength(1)
    expect(logs[0]).toMatchObject({
      level: 'warn',
      ns: 'demo',
      identifier: 'demo',
      message: 'warn-1',
      repeat: 1,
      meta: { code: 1 },
    })
    expect(Number.isNaN(Date.parse(logs[0]?.timestamp ?? ''))).toBe(false)
  })

  it('同指纹窗口内折叠，窗口过期后以累计次数汇总输出', () => {
    const { logs } = createRecorder()
    const { instance } = createDemo({ ns: 'demo' })
    configureFrontendBase({ logLevel: 'debug', windowMs: 1000 })
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-16T00:00:00.000Z'))

    instance.log('info', 'same')
    vi.setSystemTime(new Date('2026-09-16T00:00:00.200Z'))
    instance.log('info', 'same')
    instance.log('info', 'same')
    expect(logs).toHaveLength(1)

    vi.setSystemTime(new Date('2026-09-16T00:00:01.500Z'))
    instance.log('info', 'same')
    expect(logs).toHaveLength(2)
    expect(logs[1]?.repeat).toBe(4)

    instance.log('info', 'other')
    expect(logs).toHaveLength(3)
  })

  it('reportError 归一化各类入参、去重限流且不抛错', () => {
    const { errors } = createRecorder()
    const { instance } = createDemo({ ns: 'demo' })

    instance.reportError(new TypeError('boom'))
    expect(errors[0]).toMatchObject({
      ns: 'demo',
      identifier: 'demo',
      name: 'TypeError',
      message: 'boom',
      repeat: 1,
    })
    expect(errors[0]?.stack).toContain('boom')

    instance.reportError('plain')
    expect(errors[1]).toMatchObject({ name: 'Error', message: 'plain' })

    instance.reportError({ code: 40001 })
    expect(errors[2]?.message).toBe('{"code":40001}')

    const circular: Record<string, unknown> = {}
    circular.self = circular
    expect(() => instance.reportError(circular)).not.toThrow()
    expect(errors[3]?.message).toBe('[object Object]')

    instance.reportError('plain')
    expect(errors).toHaveLength(4)
  })

  it('sink 抛错被吞掉并降级输出，不影响调用方', () => {
    setFrontendSinks({
      log: () => {
        throw new Error('log sink boom')
      },
      error: () => {
        throw new Error('error sink boom')
      },
    })
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { instance } = createDemo({ ns: 'demo' })
    configureFrontendBase({ logLevel: 'debug' })

    expect(() => instance.log('error', 'x')).not.toThrow()
    expect(() => instance.reportError(new Error('y'))).not.toThrow()
    expect(errorSpy).toHaveBeenCalled()
  })

  it('t 命中翻译、缺词回退 key 原文', () => {
    const { instance } = createDemo()
    expect(instance.t('app.title')).toBe('BMS 基础管理系统')
    expect(instance.t('nope.key')).toBe('nope.key')
  })

  it('生命周期钩子：构造触发 onBaseCreated，dispose 幂等触发 onBaseDisposed', () => {
    const { instance, hooks } = createDemo()
    expect(hooks).toEqual(['created'])

    instance.dispose()
    instance.dispose()
    expect(hooks).toEqual(['created', 'disposed'])
  })

  it('组合式：字段与方法等价，作用域释放时自动 dispose', () => {
    const disposeSpy = vi.spyOn(BaseFrontend.prototype, 'dispose')
    const { logs } = createRecorder()
    configureFrontendBase({ logLevel: 'debug' })

    const scope = effectScope()
    const base = scope.run(() => useFrontendBase({ ns: 'composable' }))
    expect(base).toBeDefined()
    expect(base?.ns).toBe('composable')
    expect(base?.identifier).toBe('composable')
    expect(base?.env).toBe('dev')
    expect(Object.isFrozen(base?.config)).toBe(true)

    base?.log('info', 'hello')
    expect(logs[0]).toMatchObject({ ns: 'composable', message: 'hello', repeat: 1 })

    scope.stop()
    expect(disposeSpy).toHaveBeenCalledTimes(1)
  })

  it('组合式：作用域外可用并可手动释放', () => {
    const { logs } = createRecorder()
    configureFrontendBase({ logLevel: 'debug' })

    const base = useFrontendBase({ ns: 'outside', identifier: 'outside-1' })
    expect(base.identifier).toBe('outside-1')
    expect(base.getConfig('missing', 7)).toBe(7)

    base.reportError('oops')
    base.log('info', 'ok')
    expect(logs).toHaveLength(1)
    expect(() => base.dispose()).not.toThrow()
  })

  it('组件包装：挂载发 created、插槽下发根系能力、卸载发 disposed 并释放根系', () => {
    const disposeSpy = vi.spyOn(BaseFrontend.prototype, 'dispose')
    createRecorder()
    configureFrontendBase({ logLevel: 'debug' })

    const wrapper = mountWithPlugins(BaseFrontendWrapper, {
      props: { ns: 'wrapped', identifier: 'wrapped-1' },
      slots: {
        default: (slotProps: { base: UseFrontendBaseReturn }) =>
          h('span', { class: 'probe' }, `${slotProps.base.ns}:${slotProps.base.identifier}`),
      },
    })
    expect(wrapper.find('.probe').text()).toBe('wrapped:wrapped-1')
    expect(wrapper.emitted('created')).toHaveLength(1)

    wrapper.unmount()
    expect(wrapper.emitted('disposed')).toHaveLength(1)
    // 组件卸载既触发组件作用域的自动释放，也由包装显式释放（幂等，故断言「已调用」）
    expect(disposeSpy).toHaveBeenCalled()
  })
})
