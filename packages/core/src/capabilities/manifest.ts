/**
 * 核心能力清单（key / depends 登记源；导入即向能力机制登记）。
 *
 * 与《前端基类清单》「能力片段」节对齐（本文件为**核心侧权威表**，S2 分批扩充至 31 项）。
 */

import { registerKnownCapabilities } from '../mechanisms/capability'

export const capabilityManifest: Readonly<Record<string, readonly string[]>> = {
  value: [],
  'field-shell': [],
  'field-perm': [],
  field: ['value', 'field-shell', 'field-perm'],
}

registerKnownCapabilities(capabilityManifest)
