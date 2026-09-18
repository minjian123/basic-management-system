/**
 * 表单元数据能力基类：加载 / 缓存 / 版本比对（加载器由宿主注入，占位不请求）。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 表单元数据能力基类（抽象）。 */
export abstract class BaseFormMeta extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'form-meta'
  /** 元数据。 */
  meta: unknown
  /** 元数据版本（加载后递增；命名避开根字段 `version`）。 */
  dataVersion = 0
  /** 元数据加载器（未注入则占位不请求）。 */
  loader: (() => Promise<unknown>) | undefined

  /** 加载元数据（未注入加载器则占位不动作）。 */
  async load(): Promise<void> {
    if (this.loader === undefined) {
      return
    }
    this.meta = await this.loader()
    this.dataVersion += 1
  }

  /**
   * 依据远端版本判断是否需要刷新。
   *
   * @param version 远端版本号。
   */
  needsRefresh(version: number): boolean {
    return version > this.dataVersion
  }
}
