/**
 * 模块清单契约与严格解析（发布产物：宿主经 `modules.json` 下发）。
 *
 * 整份形态非法即抛错（宿主按「空清单 + 错误状态」处置）；单项缺字段 / 非法 / 重名逐项拒绝，
 * 不影响其余项——**缺字段即拒绝加载该项**，无缺省语义。
 */

import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

import { MODULE_NAME_PATTERN } from './define'

/** 模块清单项。 */
export interface ModuleManifestEntry {
  /** 模块名（`MODULE_NAME_PATTERN`）。 */
  name: string
  /** 入口标识（本阶段为模块源码标识；远端形态下为远端入口）。 */
  entry: string
  /** 版本（须与模块自报 `manifest.version` 严格相等）。 */
  version: string
}

/** 清单项被拒原因。 */
export interface ModuleManifestRejection {
  /** 模块名（缺名时为空串）。 */
  name: string
  /** 拒绝原因。 */
  reason: string
}

/** 清单解析结果。 */
export interface ModuleManifestParseResult {
  /** 可用清单项（保清单序）。 */
  entries: ModuleManifestEntry[]
  /** 被拒项与原因。 */
  rejected: ModuleManifestRejection[]
}

/** 读取字符串字段（去空白；非字符串返回空串）。 */
function readText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

/**
 * 解析模块清单（整份形态非法即抛错；单项非法逐项拒绝）。
 *
 * @param raw 清单原始数据（`JSON.parse` 产物）。
 * @returns 可用项与被拒项。
 * @throws BaseError 清单非数组（`CAPABILITY_VIOLATION`）。
 */
export function parseModuleManifest(raw: unknown): ModuleManifestParseResult {
  if (!Array.isArray(raw)) {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, '模块清单须为数组')
  }
  const entries: ModuleManifestEntry[] = []
  const rejected: ModuleManifestRejection[] = []
  const seen = new Set<string>()

  for (const item of raw) {
    const record = (typeof item === 'object' && item !== null ? item : {}) as Record<string, unknown>
    const name = readText(record.name)
    const entry = readText(record.entry)
    const version = readText(record.version)

    if (name === '' || !MODULE_NAME_PATTERN.test(name)) {
      rejected.push({ name, reason: `模块名缺失或非法：${name}` })
      continue
    }
    if (entry === '') {
      rejected.push({ name, reason: '入口缺失' })
      continue
    }
    if (version === '') {
      rejected.push({ name, reason: '版本缺失' })
      continue
    }
    if (seen.has(name)) {
      rejected.push({ name, reason: '清单内重名' })
      continue
    }
    seen.add(name)
    entries.push({ name, entry, version })
  }
  return { entries, rejected }
}
