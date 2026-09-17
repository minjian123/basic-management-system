/**
 * 权限上下文投影（Vue 绑定插件）：核心 `BaseAccess` ↔ Vue。
 *
 * 最小 API 面：`codes`（响应式）/ `has` / `hasAny` / `hasAll`；判定与集合语义单份在核心。
 */

import { getCurrentScope, onScopeDispose, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { createCapability, type BaseAccess } from '@bms/core'

export interface UseAccessOptions {
  /** 权限码集合（响应式；缺省空集） */
  codes?: MaybeRefOrGetter<readonly string[]>
}

export interface UseAccessReturn {
  readonly codes: readonly string[]
  has(code: string): boolean
  hasAny(codes: readonly string[]): boolean
  hasAll(codes: readonly string[]): boolean
}

export function useAccess(options: UseAccessOptions = {}): UseAccessReturn {
  const instance = createCapability<BaseAccess>('access', {
    codes: toValue(options.codes) ?? [],
  })

  const codes = shallowRef<readonly string[]>(instance.codes.get())
  const unsubscribe = instance.codes.subscribe((next) => {
    codes.value = next
  })

  if (options.codes) {
    watch(
      () => toValue(options.codes) ?? [],
      (next) => {
        instance.codes.set(next)
      },
      // 同步刷写：集合变更当拍即可判定（与旧片段「读即最新」语义一致）
      { flush: 'sync' },
    )
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      unsubscribe()
      instance.dispose()
    })
  }

  /** 读一次响应式集合（判定仍走核心实例；本读建立 Vue 依赖追踪） */
  const track = (): void => {
    void codes.value
  }

  return {
    get codes() {
      return codes.value
    },
    has: (code) => {
      track()
      return instance.has(code)
    },
    hasAny: (target) => {
      track()
      return instance.hasAny(target)
    },
    hasAll: (target) => {
      track()
      return instance.hasAll(target)
    },
  }
}
