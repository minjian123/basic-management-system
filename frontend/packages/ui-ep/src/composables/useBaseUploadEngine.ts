/** 上传引擎投影：把核心上传引擎能力基类 `BaseUploadEngine` 投影为组合式（进度 / 上传 / 取消）。 */

import { BaseUploadEngine } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体上传引擎（可实例化）。 */
class UploadEngine<TFile> extends BaseUploadEngine<TFile> {}

/** 选项。 */
export interface UseBaseUploadEngineOptions {
  /** 分片大小（字节）。 */
  chunkSize?: number
  /** 单文件大小上限（字节；0 表示不限）。 */
  maxSize?: number
}

/** `useBaseUploadEngine` 返回面。 */
export interface UseBaseUploadEngineResult<TFile = unknown> {
  /** 上传引擎基类实例。 */
  engine: BaseUploadEngine<TFile>
  /** 上传进度（0 ~ 100，响应式）。 */
  progress: Ref<number>
  /** 上传文件（未注入上传器则占位返回 `undefined`）。 */
  upload: (file: TFile) => Promise<string | undefined>
  /** 取消上传（复位进度）。 */
  cancel: () => void
}

/**
 * 使用上传引擎投影。
 *
 * @param options 选项。
 * @returns 上传引擎基类实例与响应式面。
 */
export function useBaseUploadEngine<TFile = unknown>(
  options: UseBaseUploadEngineOptions = {},
): UseBaseUploadEngineResult<TFile> {
  const engine = new UploadEngine<TFile>()
  if (options.chunkSize !== undefined) {
    engine.chunkSize = options.chunkSize
  }
  if (options.maxSize !== undefined) {
    engine.maxSize = options.maxSize
  }

  const progress = ref(engine.progress)
  const off = engine.onLifecycle((event) => {
    if (event === 'update') {
      progress.value = engine.progress
    }
  })
  onScopeDispose(off)

  return {
    engine,
    progress,
    upload: async (file) => {
      const key = await engine.upload(file)
      progress.value = engine.progress
      return key
    },
    cancel: () => {
      engine.cancel()
      progress.value = engine.progress
    },
  }
}
