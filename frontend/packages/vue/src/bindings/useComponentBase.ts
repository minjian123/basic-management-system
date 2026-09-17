/**
 * 组件根投影（Vue 绑定插件）：核心 `BaseComponent` ↔ `<script setup>` 组件。
 *
 * 口径：能力实现在核心（`nsClass` / `rootAttrs` / `passthroughAttrs` / `setProps` / 生命周期），
 * 本投影只做「实例化 + props 优先同步 + 作用域释放」；接口面与旧组合式同构（迁移组件改 import 源即可）。
 */

import { getCurrentScope, onScopeDispose } from 'vue'

import { BaseComponent, type ComponentBaseOptions, type MechanismRegistry } from '@bms/core'

export interface UseComponentBaseReturn {
  ns: string
  identifier: string
  readonly size: ComponentBaseOptions['size']
  readonly density: ComponentBaseOptions['density']
  readonly loading: boolean
  readonly disabled: boolean
  readonly visible: boolean
  /** 命名空间 class：`nsClass('button')` → `bms-button`；`nsClass()` → `bms-` */
  nsClass: (name?: string) => string
  /** 根元素属性（令牌 / 可访问性 / 状态类），外部属性经 `extra` 合并 */
  rootAttrs: (extra?: Record<string, unknown>) => Record<string, unknown>
  /** 透传面（过滤组件根保留键） */
  passthroughAttrs: (attrs: Record<string, unknown>) => Record<string, unknown>
  readonly mechanisms: MechanismRegistry
  setProps: (patch: ComponentBaseOptions) => void
  notifyLifecycle: (phase: 'mounted' | 'unmounted') => void
  dispose: () => void
  /** 核心实例（单一来源） */
  readonly instance: BaseComponent
}

export function useComponentBase(props: ComponentBaseOptions = {}): UseComponentBaseReturn {
  const instance = new BaseComponent(props)

  /** 读前同步：props 已提供的键写回实例（props 优先） */
  const sync = (): void => {
    const patch: ComponentBaseOptions = {}
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
      return instance.size
    },
    get density() {
      return instance.density
    },
    get loading() {
      return instance.loading
    },
    get disabled() {
      return instance.disabled
    },
    get visible() {
      sync()
      return instance.visible
    },
    nsClass: (name) => instance.nsClass(name),
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
    instance,
  }
}
