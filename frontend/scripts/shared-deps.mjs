/**
 * 共享依赖声明读取（**单一来源**：`frontend/shared-dependencies.json`）。
 *
 * 宿主与模块两侧构建配置、CI 断言脚本、运行期用例**都从这里取共享面与版本要求**，
 * 不得各自手写一份（漂移即口径分叉；两侧声明一致性由 check-shared-deps.mjs 断言）。
 *
 * 角色差异（见详细设计 §3.2 / §3.3）：
 *   - `host`   提供方：不带 `import: false`（须打包并提供实例），不设 `strictVersion`（拒绝权在消费方）；
 *   - `remote` 消费方：每项追加 `import: false` + `suppressMissingImportWarning`（不打包本地回退副本），并设 `strictVersion: true`（版本不满足即拒绝）。
 */
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

/** 单一来源文件名。 */
const SOURCE_FILE = 'shared-dependencies.json'

/**
 * 解析单一来源文件路径。
 *
 * 优先按本文件位置解析（构建配置场景）；测试运行器转换后 `import.meta.url` 可能不是 `file:` URL，
 * 此时自当前工作目录**向上查找**（构建配置与测试的运行目录都在 `frontend/` 之下）。
 *
 * @param root 指定 `frontend/` 目录（演练 / 测试在临时工作区跑全流程时用；缺省按本文件位置推断）。
 * @returns 单一来源文件绝对路径。
 */
export function resolveSourcePath(root) {
  if (root !== undefined) {
    const candidate = join(root, SOURCE_FILE)
    if (!existsSync(candidate)) throw new Error(`未找到共享声明单一来源：${candidate}`)
    return candidate
  }
  try {
    const here = fileURLToPath(new URL(`../${SOURCE_FILE}`, import.meta.url))
    if (existsSync(here)) return here
  } catch {
    // 非 file: URL（测试运行器等）→ 走目录向上查找回退
  }
  let dir = process.cwd()
  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = join(dir, SOURCE_FILE)
    if (existsSync(candidate)) return candidate
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error(`未找到共享声明单一来源 ${SOURCE_FILE}（请确认运行目录在 frontend/ 之下）`)
}

/**
 * 读取共享声明单一来源（原始结构）。
 *
 * @param options 选项：`root` 指定 `frontend/` 目录（缺省按本文件位置推断）。
 * @returns 单一来源内容（共享面 / 消费方覆写 / 非共享项）。
 */
export function readSharedSource(options = {}) {
  return JSON.parse(readFileSync(resolveSourcePath(options.root), 'utf8'))
}

/**
 * 生成构建配置用的 `shared` 声明。
 *
 * @param options 选项（`role` 取 `host` / `remote`，缺省 `host`；`root` 指定 `frontend/` 目录，缺省按本文件位置推断）。
 * @returns `{ shareScope, shared }`——`shared` 可直接交给 Module Federation 插件的 `shared` 选项。
 */
export function loadSharedDependencies(options = {}) {
  const { role = 'host' } = options
  const source = readSharedSource({ root: options.root })
  const shared = Object.fromEntries(
    Object.entries(source.shared).map(([name, entry]) => {
      if (role === 'host') return [name, { ...entry }]
      return [name, { ...entry, ...source.remoteOverrides, strictVersion: true }]
    }),
  )
  return { shareScope: source.shareScope ?? 'default', shared }
}

/** 共享面白名单（包名数组，声明序）。 */
export function sharedNames() {
  return Object.keys(readSharedSource().shared)
}

/** 非共享项（包名数组）。 */
export function notSharedNames() {
  return Object.keys(readSharedSource().notShared ?? {})
}

export const SUPPORTED_ROLES = ['host', 'remote']
