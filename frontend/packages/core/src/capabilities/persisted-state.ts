/**
 * 偏好持久化能力基类：本地即时状态 + 本地存储读写 + 快照回滚 + 远端偏好同步（占位）/ 版本比对。
 *
 * 统一承载「本地即时 + 远端同步」的偏好类状态（用户偏好、向导草稿、列配置、查询方案、页签、折叠等），
 * 具体件与投影不得再手写本地存储读写。
 */

import { BaseComponent } from '../base/BaseComponent'
import { stableStringify } from '../domain/serialize'

/** 本地存储后端（`localStorage` / `sessionStorage` 的最小接口）。 */
export interface PersistedStorage {
  /** 读取键值。 */
  getItem(key: string): string | null
  /** 写入键值。 */
  setItem(key: string, value: string): void
  /** 删除键值。 */
  removeItem(key: string): void
}

/** 远端保存注入点。 */
export type PersistedRemoteSaver = (value: unknown) => Promise<void>

/** 偏好持久化能力基类（抽象）。 */
export abstract class BasePersistedState extends BaseComponent {
  /** 能力键。 */
  readonly identifier: string = 'persisted-state'
  /** 状态键（本地 / 远端一致）。 */
  stateKey = ''
  /** 远端版本号（用于版本比对）。 */
  remoteVersion = 0
  /** 本地存储后端（未注入则不落盘）。 */
  storage: PersistedStorage | undefined
  /** 远端保存注入点（未注入则只写本地并置待同步标记）。 */
  remoteSaver: PersistedRemoteSaver | undefined
  /** 待同步标记（远端保存未注入或失败时置位）。 */
  pendingSync = false
  /** 本地即时状态。 */
  #local: unknown
  /** 打开前快照（取消回滚用）。 */
  #snapshot: unknown
  /** 是否已记录快照。 */
  #hasSnapshot = false
  /** 是否已有本地状态（用于区分「未设置」与 `undefined`）。 */
  #hasLocal = false

  /** 本地即时状态快照。 */
  get local(): unknown {
    return this.#local
  }

  /** 是否已有本地状态。 */
  get hasLocal(): boolean {
    return this.#hasLocal
  }

  /** 是否有未保存变更（与快照比较，稳定序列化）。 */
  get dirty(): boolean {
    return this.#hasSnapshot && stableStringify(this.#local) !== stableStringify(this.#snapshot)
  }

  /**
   * 写入本地即时状态（不触本地存储与远端）。
   *
   * @param value 状态值。
   */
  setLocal(value: unknown): void {
    this.#local = value
    this.#hasLocal = true
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 从本地存储读取到内存（解析失败或未注入存储时返回 `false`，不抛错）。
   *
   * @returns 是否读取到值。
   */
  restore(): boolean {
    if (this.storage === undefined || this.stateKey === '') {
      return false
    }
    try {
      const raw = this.storage.getItem(this.stateKey)
      if (raw === null) {
        return false
      }
      this.#local = JSON.parse(raw) as unknown
      this.#hasLocal = true
      if (!this.isDisposed) {
        this.notifyLifecycle('update')
      }
      return true
    } catch {
      return false
    }
  }

  /**
   * 把内存状态写入本地存储（未注入存储 / 无状态 / 写入受限时返回 `false`，不抛错）。
   *
   * @returns 是否写入成功。
   */
  persist(): boolean {
    if (this.storage === undefined || this.stateKey === '' || !this.#hasLocal) {
      return false
    }
    try {
      this.storage.setItem(this.stateKey, stableStringify(this.#local))
      return true
    } catch {
      return false
    }
  }

  /** 记录快照（打开面板 / 进入向导前调用）。 */
  snapshot(): void {
    this.#snapshot = this.#local
    this.#hasSnapshot = true
  }

  /**
   * 回滚到快照（未记录快照时返回 `false`）。
   *
   * @returns 是否回滚。
   */
  rollback(): boolean {
    if (!this.#hasSnapshot) {
      return false
    }
    this.#local = this.#snapshot
    this.#hasLocal = true
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
    return true
  }

  /** 清空状态（内存 + 本地存储 + 快照 + 待同步标记）。 */
  clear(): void {
    this.#local = undefined
    this.#hasLocal = false
    this.#snapshot = undefined
    this.#hasSnapshot = false
    this.pendingSync = false
    if (this.storage !== undefined && this.stateKey !== '') {
      try {
        this.storage.removeItem(this.stateKey)
      } catch {
        // 存储受限（隐私模式）时降级为仅清内存。
      }
    }
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }

  /**
   * 以默认值重置并保存。
   *
   * @param defaults 默认值。
   * @returns 保存是否全部成功。
   */
  async reset(defaults: unknown): Promise<boolean> {
    this.setLocal(defaults)
    return this.save()
  }

  /**
   * 保存：写本地存储 + 远端（远端注入点未注入时置待同步标记且不发请求）。
   *
   * @returns 是否全部成功（含远端）。
   */
  async save(): Promise<boolean> {
    const persisted = this.persist()
    if (this.remoteSaver === undefined) {
      this.pendingSync = true
      return false
    }
    try {
      await this.remoteSaver(this.#local)
      this.pendingSync = false
      return persisted
    } catch {
      this.pendingSync = true
      return false
    }
  }

  /**
   * 加载远端偏好（占位：未注入远端加载时从本地存储恢复并返回本地快照，不发请求）。
   *
   * @returns 本地快照。
   */
  async loadRemote(): Promise<unknown> {
    this.restore()
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
