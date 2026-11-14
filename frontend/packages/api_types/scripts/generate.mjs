/**
 * 契约类型生成器薄壳（需求 01-9）：**实现已下沉** `frontend/scripts/api-types/generate.mjs`，
 * 本文件只负责把「本包目录」传给基座实现；产品差异全部在 `api-types.config.json`。
 *
 * 用法（不变）：
 *   node scripts/generate.mjs           # 生成（覆盖写入）
 *   node scripts/generate.mjs --check   # 零漂移校验（不写盘）
 */

import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { run } from '../../../scripts/api-types/generate.mjs'

const packageDir = resolve(fileURLToPath(new URL('.', import.meta.url)), '..')

process.exitCode = await run({ packageDir })
