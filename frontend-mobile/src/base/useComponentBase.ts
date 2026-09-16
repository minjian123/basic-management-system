/**
 * 组件根组合式：为 `<script setup>` 组件提供与 `BaseComponent` 等价的能力。
 *
 * Vue 3 无类多继承，组合式是「继承」的等价形态（双轨：类继承 / 组合式）；
 * 两轨能力等价，口径见《前端开发规范》「继承与组合分工（强制）」节。
 *
 * **取值优先级**：props 提供的键 > `setProps` 运行期更新 > 构造默认值——传入响应式 props
 * （`reactive` / `defineProps` 结果）时读写保持响应，读前会把 props 已提供的键同步到实例，
 * 保证 `size` / `rootAttrs()` / `nsClass()` 等同源一致。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import {
  BaseComponent,
  type ComponentBaseOptions,
  type ComponentDensity,
  type ComponentSize,
  type MechanismRegistry,
} from './BaseComponent'

/** 组合式返回值：与 `BaseComponent` 的公开能力等价 */
export interface UseComponentBaseReturn {
  ns: string
  identifier: string
  readonly size: ComponentSize
  readonly density: ComponentDensity | undefined
  readonly loading: boolean
  readonly disabled: boolean
  readonly visible: boolean
  /** 命名空间 class：`nsClass('button')` → `bms-button`；`nsClass()` → `bms-` */
  nsClass: (name?: string) => string
  /** 根元素属性（令牌 / 可访问性 / 状态类），外部属性经 `extra` 合并 */
  rootAttrs: (extra?: Record<string, unknown>) => Record<string, unknown>
  /** 透传面（过滤组件根保留键） */
  passthroughAttrs: (attrs: Record<string, unknown>) => Record<string, unknown>
  /** 机制装配点（占位 / 异步资源 / 订阅经它挂接） */
  readonly mechanisms: MechanismRegistry
  /** 运行期更新（props 未提供的键生效；props 提供的键以 props 为准） */
  setProps: (patch: Partial<ComponentBaseOptions>) => void
  /** 挂载 / 卸载通知（组件包装调用） */
  notifyLifecycle: (phase: 'mounted' | 'unmounted') => void
  dispose: () => void
}

/** 作用域实例：承载与组件根类完全相同的能力（组合轨不另起炉灶） */
class ScopedComponentBase extends BaseComponent {}

/**
 * 获取组件根能力（组合轨）。
 *
 * 处于组件 / 副作用作用域内时，随作用域释放自动 `dispose()`（含已挂机制）。
 */
export function useComponentBase(props: Partial<ComponentBaseOptions> = {}): UseComponentBaseReturn {
  const instance = new ScopedComponentBase(props)

  /** 读前同步：props 已提供的键写回实例（props 优先） */
  const sync = (): void => {
    const patch: Partial<ComponentBaseOptions> = {}
    if (props.size !== undefined) {
      patch.size = props.size
    }
    if (props.density !== undefined) {
      patch.density = props.density
    }
    if (props.loading !== undefined) {
      patch.loading = props.loading
    }
    if (props.disabled !== undefined) {
      patch.disabled = props.disabled
    }
    if (props.visible !== undefined) {
      patch.visible = props.visible
    }
    if (props.dataTest !== undefined) {
      patch.dataTest = props.dataTest
    }
    instance.setProps(patch)
  }

  if (getCurrentScope()) {
    onScopeDispose(() => instance.dispose())
  }

  return {
    ns: instance.ns,
    identifier: instance.identifier,
    get size() {
      sync()
      return instance.size
    },
    get density() {
      sync()
      return instance.density
    },
    get loading() {
      sync()
      return instance.loading
    },
    get disabled() {
      sync()
      return instance.disabled
    },
    get visible() {
      sync()
      return instance.visible
    },
    nsClass: (name) => {
      sync()
      return instance.nsClass(name)
    },
    rootAttrs: (extra) => {
      sync()
      return instance.rootAttrs(extra)
    },
    passthroughAttrs: (attrs) => {
      sync()
      return instance.passthroughAttrs(attrs)
    },
    mechanisms: instance.mechanisms,
    setProps: (patch) => instance.setProps(patch),
    notifyLifecycle: (phase) => instance.notifyLifecycle(phase),
    dispose: () => instance.dispose(),
  }
}
