/**
 * 表单页组合能力基类：三态（新增 / 编辑 / 详情）/ 提交 / 脏数据 / 返回。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 表单页模式。 */
export type FormMode = 'create' | 'edit' | 'detail'

/** 表单页组合能力基类（抽象）。 */
export abstract class BaseFormPage extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'form-page'
  /** 依赖能力键（表单元数据）。 */
  override readonly depends = ['form-meta']
  /** 当前模式。 */
  mode: FormMode = 'create'
  /** 是否脏数据。 */
  dirty = false
  /** 提交器（未注入则占位不请求）。 */
  submitter: (() => Promise<void>) | undefined

  /**
   * 设置模式。
   *
   * @param mode 模式。
   */
  setMode(mode: FormMode): void {
    this.mode = mode
  }

  /**
   * 标记脏数据。
   *
   * @param dirty 是否脏。
   */
  markDirty(dirty = true): void {
    this.dirty = dirty
  }

  /** 提交（未注入提交器则占位不动作；成功后清脏）。 */
  async submit(): Promise<void> {
    if (this.submitter === undefined) {
      return
    }
    await this.submitter()
    this.dirty = false
  }

  /** 返回：脏数据时需拦截（返回 `true` 表示需确认）。 */
  back(): boolean {
    return this.dirty
  }
}
