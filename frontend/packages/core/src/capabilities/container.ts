/** 容器形态能力：区域语义（折叠状态机 / 区域名称），渲染与视觉由插件承担。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface ContainerOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  collapsible?: boolean
  collapsed?: boolean
}

export class BaseContainer extends BaseCapability {
  readonly collapsible: boolean
  readonly collapsed = observable(false)

  constructor(options: ContainerOptions = {}) {
    super({ ...options, key: options.key ?? 'container' })
    this.collapsible = options.collapsible ?? false
    this.collapsed.set(options.collapsed ?? false)
  }

  toggle(): void {
    if (!this.collapsible) {
      return
    }
    this.collapsed.set(!this.collapsed.get())
  }

  collapse(): void {
    if (this.collapsible) {
      this.collapsed.set(true)
    }
  }

  expand(): void {
    this.collapsed.set(false)
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), collapsible: this.collapsible }
  }
}
