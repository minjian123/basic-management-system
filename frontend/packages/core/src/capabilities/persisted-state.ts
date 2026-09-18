/**
 * 偏好持久化能力基类：本地即时状态 + 远端偏好同步（占位）/ 版本比对。
 */

import { BaseComponent } from '../base/BaseComponent'

/** 偏好持久化能力基类（抽象）。 */
export abstract class BasePersistedState extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'persisted-state'
  /** 状态键（本地 / 远端一致）。 */
  stateKey = ''
  /** 远端版本号（用于版本比对）。 */
  remoteVersion = 0
  /** 本地即时状态。 */
  #local: unknown

  /** 本地即时状态快照。 */
  get local(): unknown {
    return this.#local
  }

  /**
   * 写入本地即时状态（不触远端）。
   *
   * @param value 状态值。
   */
  setLocal(value: unknown): void {
    this.#local = value
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 加载远端偏好（占位：不请求，返回本地快照）。
   *
   * @returns 本地快照。
   */
  async loadRemote(): Promise<unknown> {
    return this.#local
  }

  /**
   * 依据远端版本判断是否需要刷新。
   *
   * @param version 远端版本号。
   */
  needsRemoteRefresh(version: number): boolean {
    return version > this.remoteVersion
  }
}
