/** 偏好持久化能力：本地即时 + 可注入存储适配器（远端偏好同步随后续任务）。 */

import { BaseCapability, type CapabilityOptions } from '../mechanisms/capability'
import { observable } from '../base/observable'

export interface KeyValueStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export function createMemoryStorage(): KeyValueStorage {
  const map = new Map<string, string>()
  return {
    getItem: (key) => (map.has(key) ? (map.get(key) as string) : null),
    setItem: (key, value) => {
      map.set(key, value)
    },
    removeItem: (key) => {
      map.delete(key)
    },
  }
}

export interface PersistedStateOptions<T> extends Omit<CapabilityOptions, 'key'> {
  key?: string
  /** 偏好键（存储键 = `bms:pref:{key}`） */
  prefKey: string
  defaultValue: T
  storage?: KeyValueStorage
}

export class BasePersistedState<T> extends BaseCapability {
  readonly state = observable<T>(undefined as T)
  private readonly prefKey: string
  private readonly storage: KeyValueStorage

  constructor(options: PersistedStateOptions<T>) {
    super({ ...options, key: options.key ?? 'persisted-state' })
    this.prefKey = `bms:pref:${options.prefKey}`
    this.storage = options.storage ?? createMemoryStorage()
    this.state.set(this.read() ?? options.defaultValue)
  }

  private read(): T | undefined {
    try {
      const raw = this.storage.getItem(this.prefKey)
      return raw === null ? undefined : (JSON.parse(raw) as T)
    } catch {
      return undefined
    }
  }

  get(): T {
    return this.state.get()
  }

  set(value: T): void {
    this.state.set(value)
    try {
      this.storage.setItem(this.prefKey, JSON.stringify(value))
    } catch (error) {
      this.reportError(error, { phase: 'persist-write', key: this.prefKey })
    }
  }

  reset(defaultValue?: T): void {
    this.storage.removeItem(this.prefKey)
    this.state.set(defaultValue as T)
  }
}
