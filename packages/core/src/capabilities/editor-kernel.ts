/** 编辑器内核能力：懒加载 / 创建销毁 / 内容协议（内核实现由注入 loader 承担）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface EditorKernelInstance {
  setValue(value: string): void
  getValue(): string
  destroy(): void
}

export interface EditorKernelOptions extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 内核懒加载（CodeMirror / 富文本 / Markdown 由各自 loader 承接） */
  loader?: () => Promise<EditorKernelInstance>
}

export class BaseEditorKernel extends BaseCapability {
  readonly ready = observable(false)
  readonly content = observable('')
  private instance: EditorKernelInstance | undefined
  private readonly loader: EditorKernelOptions['loader']

  constructor(options: EditorKernelOptions = {}) {
    super({ ...options, key: options.key ?? 'editor-kernel' })
    this.loader = options.loader
  }

  async mount(): Promise<boolean> {
    if (this.instance || !this.loader) {
      return Boolean(this.instance)
    }
    try {
      this.instance = await this.loader()
      this.instance.setValue(this.content.get())
      this.ready.set(true)
      return true
    } catch (error) {
      this.reportError(error, { phase: 'editor-mount' })
      return false
    }
  }

  setContent(value: string): void {
    this.content.set(value)
    this.instance?.setValue(value)
  }

  dispose(): void {
    this.instance?.destroy()
    this.instance = undefined
    this.ready.set(false)
    super.dispose()
  }

  describe(): Record<string, unknown> {
    return { ...super.describe(), ready: this.ready.get() }
  }
}
