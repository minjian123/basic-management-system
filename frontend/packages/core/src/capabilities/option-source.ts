/**
 * 选项源能力基类：加载 / 缓存与版本比对 / 搜索 / 回显（加载器由宿主注入，占位不请求）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 选项项。 */
export interface OptionItem<T = unknown> {
  /** 值。 */
  value: T
  /** 展示文案。 */
  label: string
}

/** 选项源能力基类（抽象）。 */
export abstract class BaseOptionSource<T = unknown> extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'option-source'
  /** 已加载选项。 */
  options: OptionItem<T>[] = []
  /** 数据版本（加载后递增，用于版本比对；命名避开根字段 `version`）。 */
  dataVersion = 0
  /** 选项加载器（未注入则占位不请求）。 */
  loader: (() => Promise<OptionItem<T>[]>) | undefined

  /** 加载选项（未注入加载器则占位不动作）。 */
  async load(): Promise<void> {
    if (this.loader === undefined) {
      return
    }
    this.options = await this.loader()
    this.dataVersion += 1
  }

  /**
   * 按值回显文案。
   *
   * @param value 值。
   */
  getLabel(value: T): string | undefined {
    return this.options.find((item) => Object.is(item.value, value))?.label
  }

  /**
   * 按关键字搜索（空串返回全部）。
   *
   * @param keyword 关键字。
   */
  search(keyword: string): OptionItem<T>[] {
    const text = keyword.trim()
    if (text === '') {
      return [...this.options]
    }
    return this.options.filter((item) => item.label.includes(text))
  }
}
