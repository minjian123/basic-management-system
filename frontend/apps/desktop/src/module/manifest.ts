/**
 * 模块清单获取（宿主）：清单外置为 `public/modules.json`（改清单不必重构建）。
 *
 * 获取失败（网络 / 404 / JSON 非法 / 非数组）**不阻塞启动**——返回空清单与原因，由调用方记错误状态。
 */

import { parseModuleManifest, type ModuleManifestEntry, type ModuleManifestRejection } from '@bms/core'

/** 模块清单地址（随部署替换清单文件）。 */
export const MODULE_MANIFEST_URL = '/modules.json'

/** 清单获取结果。 */
export interface ModuleManifestLoadResult {
  /** 可用清单项。 */
  entries: ModuleManifestEntry[]
  /** 被拒项与原因。 */
  rejected: ModuleManifestRejection[]
  /** 获取失败原因（成功时缺省）。 */
  reason?: string
}

/**
 * 获取并解析模块清单（失败按空清单处理）。
 *
 * @param url 清单地址。
 * @returns 清单获取结果。
 */
export async function loadModuleManifest(url: string = MODULE_MANIFEST_URL): Promise<ModuleManifestLoadResult> {
  try {
    const response = await fetch(url, { headers: { accept: 'application/json' } })
    if (!response.ok) {
      return { entries: [], rejected: [], reason: `清单获取失败：HTTP ${response.status}` }
    }
    const parsed = parseModuleManifest(await response.json())
    return { entries: parsed.entries, rejected: parsed.rejected }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return { entries: [], rejected: [], reason: `清单获取失败：${message}` }
  }
}
