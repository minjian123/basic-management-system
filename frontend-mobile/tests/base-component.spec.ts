/** 组件根用例（Kiwi 700）：props / attrs 透传 / 令牌属性 / 可访问性 / 机制装配点（双端同款）。 */

import { beforeEach, describe, expect, it } from 'vitest'
import { effectScope, h, nextTick, reactive } from 'vue'

import {
  BaseComponent,
  resetMechanismWarnings,
  type ComponentBaseOptions,
  type MechanismLike,
  type MechanismRegistry,
} from '@/base/BaseComponent'
import { configureFrontendBase, resetFrontendBaseConfig, setFrontendSinks, type LogRecord } from '@/base/BaseFrontend'
import { BasePlaceholder } from '@/base/placeholder'
import { useComponentBase } from '@/base/useComponentBase'
import BaseComponentWrapper from '@/base/BaseComponent.vue'

import { mountWithPlugins } from './helpers/mount'

/** 探针组件：以组件根为身份轨的最小实现 */
class ProbeComponent extends BaseComponent {
  mountedCount = 0
  unmountedCount = 0

  protected override onComponentMounted(): void {
    this.mountedCount += 1
  }

  protected override onComponentUnmounted(): void {
    this.unmountedCount += 1
  }
}

/** 探针机制：验证装配点的挂接与释放联动 */
class ProbeMechanism implements MechanismLike {
  readonly mechanismKey = 'probe'
  attached = 0
  detached = 0

  attachToComponent(): void {
    this.attached += 1
  }

  detachFromComponent(): void {
    this.detached += 1
  }
}

const logRecords: LogRecord[] = []

/** 警告记录（用于断言机制未挂接告警） */
function warnings(): LogRecord[] {
  return logRecords.filter((record) => record.level === 'warn')
}

beforeEach(() => {
  resetFrontendBaseConfig()
  resetMechanismWarnings()
  logRecords.length = 0
  setFrontendSinks({
    log: (record) => logRecords.push(record),
    error: () => {},
  })
})

describe('组件根（Kiwi 700）', () => {
  it('① 类与组合式的 props 等价', () => {
    const options: ComponentBaseOptions = {
      ns: 'demo',
      identifier: 'probe',
      size: 'large',
      density: 'compact',
      loading: true,
      disabled: true,
      visible: false,
      dataTest: 'probe-root',
    }
    const instance = new ProbeComponent(options)
    expect(instance.size).toBe('large')
    expect(instance.density).toBe('compact')
    expect(instance.loading).toBe(true)
    expect(instance.disabled).toBe(true)
    expect(instance.visible).toBe(false)
    expect(instance.dataTest).toBe('probe-root')

    const base = useComponentBase(options)
    expect(base.size).toBe('large')
    expect(base.density).toBe('compact')
    expect(base.loading).toBe(true)
    expect(base.disabled).toBe(true)
    expect(base.visible).toBe(false)
    expect(base.ns).toBe('demo')
    expect(base.rootAttrs()['data-test']).toBe('probe-root')
  })

  it('② 命名空间回落与 class 前缀', () => {
    const blank = new ProbeComponent({ ns: '   ' })
    expect(blank.ns).toBe('bms')
    expect(blank.identifier).toBe('bms')
    expect(blank.nsClass('button')).toBe('bms-button')
    expect(blank.nsClass()).toBe('bms-')

    const custom = new ProbeComponent({ ns: 'demo' })
    expect(custom.nsClass('field')).toBe('demo-field')
  })

  it('③ rootAttrs 产出令牌属性、可访问性与状态类（未设 density 不产出）', () => {
    const instance = new ProbeComponent({ size: 'small', loading: true, disabled: true, dataTest: 'x' })
    const attrs = instance.rootAttrs()
    expect(attrs['data-size']).toBe('small')
    expect(attrs['data-test']).toBe('x')
    expect(attrs['aria-busy']).toBe('true')
    expect(attrs['aria-disabled']).toBe('true')
    expect(attrs.class).toEqual(['is-disabled', 'is-loading'])
    expect('data-density' in attrs).toBe(false)

    const withDensity = new ProbeComponent({ density: 'loose' })
    expect(withDensity.rootAttrs()['data-density']).toBe('loose')
    expect('class' in withDensity.rootAttrs()).toBe(false)
  })

  it('④ rootAttrs 合并外部 class、passthroughAttrs 过滤保留键', () => {
    const instance = new ProbeComponent({ size: 'large', loading: true })
    expect(instance.rootAttrs({ class: 'external' }).class).toEqual(['is-loading', 'external'])

    const passthrough = instance.passthroughAttrs({
      'data-size': 'small',
      'data-density': 'compact',
      'data-test': 'x',
      'aria-disabled': 'true',
      'aria-busy': 'true',
      id: 'field-1',
      class: 'external',
      style: 'color: red',
    })
    expect(passthrough).toEqual({ id: 'field-1', class: 'external', style: 'color: red' })
  })

  it('⑤ 组合式 props 与运行期更新', () => {
    const props = { size: 'small' as const, loading: true }
    const base = useComponentBase(props)
    expect(base.size).toBe('small')
    expect(base.loading).toBe(true)
    expect(base.rootAttrs()['aria-busy']).toBe('true')

    // 取值优先级：props 提供的键 > setProps 运行期更新 > 构造默认值
    const reactiveProps = reactive<ComponentBaseOptions>({ size: 'small' })
    const scoped = useComponentBase(reactiveProps)
    expect(scoped.size).toBe('small')

    scoped.setProps({ size: 'large', loading: true })
    expect(scoped.size).toBe('small')
    expect(scoped.loading).toBe(true)
    expect(scoped.rootAttrs()['data-size']).toBe('small')

    reactiveProps.size = 'large'
    expect(scoped.size).toBe('large')
    expect(scoped.rootAttrs()['data-size']).toBe('large')
  })

  it('⑥ 机制装配点：attach / detach / get / list / size 与 dispose 逆序释放', () => {
    const instance = new ProbeComponent()
    const registry: MechanismRegistry = instance.mechanisms
    const first = new ProbeMechanism()
    const second = new ProbeMechanism()
    const detachFirst = registry.attach(first)
    registry.attach(second)

    expect(registry.size).toBe(2)
    expect(registry.get('probe')).toBe(first)
    expect(registry.list()).toHaveLength(2)
    expect(registry.get<ProbeMechanism>('probe')?.attached).toBe(1)

    // 重复挂接幂等（不重复 attach）
    registry.attach(first)
    expect(first.attached).toBe(1)
    expect(registry.size).toBe(2)

    detachFirst()
    expect(registry.size).toBe(1)
    expect(first.detached).toBe(1)

    instance.dispose()
    expect(second.detached).toBe(1)
    expect(registry.size).toBe(0)

    // dispose 幂等：再次释放不重复调用 detach
    instance.dispose()
    expect(second.detached).toBe(1)
  })

  it('⑦ 未挂接机制开发态告警一次；挂接后与生产态静默', () => {
    const orphan = new BasePlaceholder({ label: '未挂接探针' })
    orphan.describe()
    expect(warnings()).toHaveLength(1)
    expect(warnings()[0]?.message).toContain('未被组件根挂接')

    orphan.describe()
    expect(warnings()).toHaveLength(1)

    // 挂接后不再告警
    resetFrontendBaseConfig()
    resetMechanismWarnings()
    logRecords.length = 0
    const instance = new ProbeComponent()
    const attached = new BasePlaceholder({ label: '已挂接', owner: instance })
    attached.describe()
    expect(warnings()).toHaveLength(0)

    // 生产态静默（含占位标记与日志输出）
    resetFrontendBaseConfig()
    configureFrontendBase({ env: 'prod' })
    resetMechanismWarnings()
    logRecords.length = 0
    const inProd = new BasePlaceholder({ label: '生产态' })
    inProd.describe()
    expect(logRecords).toHaveLength(0)
    expect(inProd.placeholderAttrs()).toEqual({})
  })

  it('⑧ 组件包装：透传合并、插槽下发、挂载事件与卸载释放', () => {
    const wrapper = mountWithPlugins(BaseComponentWrapper, {
      props: { size: 'small', disabled: true, dataTest: 'wrapper-root', visible: true },
      attrs: { class: 'external', id: 'wrapper-1' },
      slots: {
        default: (params: { base: { size: string } }) => h('span', { class: 'inner' }, params.base.size),
      },
    })

    const root = wrapper.find('div')
    expect(root.attributes('data-size')).toBe('small')
    expect(root.attributes('data-test')).toBe('wrapper-root')
    expect(root.attributes('aria-disabled')).toBe('true')
    expect(root.attributes('id')).toBe('wrapper-1')
    expect(root.classes()).toContain('is-disabled')
    expect(root.classes()).toContain('external')
    expect(wrapper.find('.inner').text()).toBe('small')
    expect(wrapper.emitted('base-mounted')).toHaveLength(1)

    const exposed = wrapper.vm as unknown as { mechanisms: MechanismRegistry }
    const mechanism = new ProbeMechanism()
    exposed.mechanisms.attach(mechanism)
    wrapper.unmount()
    expect(mechanism.detached).toBe(1)
    expect(wrapper.emitted('base-unmounted')).toHaveLength(1)
  })

  it('⑨ visible=false 不渲染；生命周期钩子与作用域释放', async () => {
    const hidden = mountWithPlugins(BaseComponentWrapper, { props: { visible: false } })
    expect(hidden.find('div').exists()).toBe(false)
    hidden.unmount()

    const instance = new ProbeComponent()
    instance.notifyLifecycle('mounted')
    instance.notifyLifecycle('unmounted')
    expect(instance.mountedCount).toBe(1)
    expect(instance.unmountedCount).toBe(1)

    const scope = effectScope()
    const mechanism = new ProbeMechanism()
    scope.run(() => {
      const base = useComponentBase()
      base.mechanisms.attach(mechanism)
    })
    scope.stop()
    await nextTick()
    expect(mechanism.detached).toBe(1)
  })
})
