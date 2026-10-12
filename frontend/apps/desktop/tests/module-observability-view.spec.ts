// kiwi_id: 982
/**
 * 模块观测面板视图用例（开发态 dev-only 路由 `/dev/module-observability`）：
 * 按模块耗时列（resolve / setup / mount / 渲染）、错误 / 守卫决策 / Web Vitals 四个区块、
 * 刷新与清空记录，以及「加载器未装载」「清单缺省字段」等回落分支。
 *
 * 依赖注入口径：视图只依赖 `@/module/host` 的加载器与 `@/observability` 的遥测快照，
 * 故以可变桩精确驱动各分支（真实遥测聚合已由 module-observability.spec.ts 覆盖）。
 */

import { flushPromises, mount, type DOMWrapper, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/** 模块加载器桩（`undefined` 驱动「清单未装载」分支）。 */
interface LoaderStub {
  names(): string[]
  entryOf(name: string): { version?: string; mode?: string; enabled?: boolean } | undefined
  isMounted(name: string): boolean
}

/** 可变注入状态（`vi.mock` 工厂经 `vi.hoisted` 读取）。 */
const state = vi.hoisted(() => ({
  loader: undefined as LoaderStub | undefined,
  snapshot: {} as Record<string, unknown>,
  resetCalls: 0,
}))

vi.mock('@/module/host', () => ({ getModuleLoader: () => state.loader }))
vi.mock('@/observability', () => ({
  moduleSnapshot: () => state.snapshot,
  resetModuleTelemetry: () => {
    state.resetCalls += 1
  },
}))

import ModuleObservabilityView from '@/views/ModuleObservabilityView.vue'

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver（同 RoleView 用例口径）。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

/** 完整加载器桩：demo 有入口与挂载、ghost 缺版本 / 形态且停用 / 未挂载、untracked 均缺省。 */
function fullLoader(): LoaderStub {
  return {
    names: () => ['demo', 'ghost', 'untracked'],
    entryOf: (name: string) =>
      name === 'demo'
        ? { version: '0.2.0', mode: 'remote', enabled: true }
        : name === 'ghost'
          ? { version: undefined, mode: undefined, enabled: false }
          : undefined,
    // 未挂载返回 `undefined`：驱动 `?? false` 回落（动态加载器能力的防御分支）。
    isMounted: (name: string) => (name === 'demo' ? true : (undefined as unknown as boolean)),
  }
}

/** 完整快照桩：模块 load / errors / vitals 与平台 errors / vitals / guards 齐备。 */
function fullSnapshot(): Record<string, unknown> {
  return {
    modules: {
      demo: {
        version: '0.1.0',
        load: [
          { phase: 'resolve', durationMs: 12.34 },
          { phase: 'setup', durationMs: 5 },
          { phase: 'mount', durationMs: 7 },
          { phase: 'custom', durationMs: 9 },
        ],
        errors: [{ version: '0.1.0', phase: 'mount', message: 'boom', at: '2026-10-12T00:00:00.000Z' }],
        vitals: [{ metric: 'LCP', value: 1234, rating: 'good', at: '2026-10-12T00:00:00.000Z' }],
      },
      // 无版本号（入口版本缺省时回落快照版本）、无错误、无 vitals、仅一条 resolve。
      ghost: { version: '9.9.9', load: [{ phase: 'resolve', durationMs: 3 }], errors: [], vitals: [] },
    },
    platform: {
      errors: [{ version: '', phase: 'runtime', message: '平台错', at: '2026-10-12T00:00:01.000Z' }],
      vitals: [{ metric: 'CLS', value: 0.01, rating: 'good', at: '2026-10-12T00:00:01.000Z' }],
      guards: [{ decision: 'allow', path: '/', reason: 'session-ready', at: '2026-10-12T00:00:01.000Z' }],
    },
  }
}

/** 空快照桩：模块分组与平台记录均缺省（清空记录后口径）。 */
function emptySnapshot(): Record<string, unknown> {
  return { modules: {}, platform: { errors: [], vitals: [], guards: [] } }
}

/** 挂载面板并等待表格渲染。 */
async function mountView(): Promise<VueWrapper> {
  const wrapper = mount(ModuleObservabilityView)
  await flushPromises()
  return wrapper
}

/** 按文案取按钮（未命中返回 `undefined`）。 */
function buttonByText(wrapper: VueWrapper, text: string): DOMWrapper<Element> | undefined {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}

let wrapper: VueWrapper | undefined

beforeEach(() => {
  state.loader = fullLoader()
  state.snapshot = fullSnapshot()
  state.resetCalls = 0
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
})

describe('模块观测面板视图（Kiwi 982）', () => {
  it('模块与耗时：入口 / 快照 / 缺省三态回落，毫秒按 null 展示破折号', async () => {
    wrapper = await mountView()
    const rows = wrapper.findAll('.el-table__row')
    const text = rows.map((row) => row.text())

    // demo：入口版本 0.2.0、形态 remote、可见、已挂载、resolve 12 ms（四舍五入）、render 无记录为破折号。
    const demo = text.find((item) => item.includes('demo')) ?? ''
    expect(demo).toContain('0.2.0')
    expect(demo).toContain('remote')
    expect(demo).toContain('是')
    expect(demo).toContain('12 ms')
    expect(demo).toContain('—')
    expect(demo).toContain('1')

    // ghost：入口缺版本回落快照版本 9.9.9、缺形态为空串、停用、未挂载、resolve 3 ms、setup / mount / render 无记录。
    const ghost = text.find((item) => item.includes('ghost')) ?? ''
    expect(ghost).toContain('9.9.9')
    expect(ghost).toContain('停用')
    expect(ghost).toContain('否')
    expect(ghost).toContain('3 ms')

    // untracked：入口与快照均缺省（版本空串、形态空串、可见默认、未挂载、全部耗时破折号）。
    expect(text.some((item) => item.includes('untracked'))).toBe(true)
  })

  it('错误 / 守卫 / Web Vitals 区块：模块与平台记录合并展示', async () => {
    wrapper = await mountView()

    const errors = wrapper.find('[data-test="observability-errors"]')
    const guards = wrapper.find('[data-test="observability-guards"]')
    const vitals = wrapper.find('[data-test="observability-vitals"]')

    expect(errors.text()).toContain('boom')
    expect(errors.text()).toContain('平台错')
    expect(guards.text()).toContain('session-ready')
    expect(vitals.text()).toContain('LCP')
    expect(vitals.text()).toContain('CLS')
  })

  it('刷新：加载器未装载时按空清单渲染（不抛错）', async () => {
    state.loader = undefined
    wrapper = await mountView()

    buttonByText(wrapper, '刷新')?.trigger('click')
    await flushPromises()

    // 模块表无行（加载器未装载 → 名称清单为空）；错误 / 守卫 / Vitals 三表仍按平台快照渲染。
    expect(wrapper.find('[data-test="observability-modules"]').findAll('.el-table__row')).toHaveLength(0)
  })

  it('清空记录：重置遥测并刷新；分组 / 平台记录缺省时按空表渲染', async () => {
    wrapper = await mountView()

    state.snapshot = emptySnapshot()
    buttonByText(wrapper, '清空记录')?.trigger('click')
    await flushPromises()

    expect(state.resetCalls).toBe(1)
    const rows = wrapper.findAll('.el-table__row')
    // 模块表仍按加载器名渲染三行（快照分组缺省 → 版本空串 / 耗时破折号），错误 / 守卫 / Vitals 三表为空。
    expect(rows.map((row) => row.text()).filter((item) => item.includes('demo'))).toHaveLength(1)
    expect(wrapper.findAll('.el-table__empty-text').length).toBeGreaterThan(0)
  })
})
