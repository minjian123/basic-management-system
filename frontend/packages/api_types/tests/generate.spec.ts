/**
 * 契约生成脚本的清单来源用例：`--files-from -` 从标准输入读改动清单。
 *
 * 提交前门禁把清单通过管道递进来（不落临时文件），本用例即这条通路的机器断言：
 * 喂一条「不触及契约面」的路径，脚本必须识别为增量并跳过生成；喂一条触及契约面的
 * 路径，必须走检查分支而不是当成全量或报清单不可读。
 */
// kiwi_id: 2265

import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const packageRoot = resolve(here, '..')
const script = resolve(packageRoot, 'scripts/generate.mjs')

/**
 * 以 `--files-from -` 运行生成脚本，把清单从标准输入喂进去。
 *
 * @param listing 标准输入的清单文本（一行一个仓根相对路径）。
 * @returns 子进程标准输出。
 */
function runWithStdin(listing: string): string {
  return execFileSync(process.execPath, [script, '--check', '--files-from', '-'], {
    cwd: packageRoot,
    input: listing,
    encoding: 'utf8',
  })
}

describe('生成脚本清单来源：标准输入', () => {
  it('未触及契约面时判为增量并跳过', () => {
    const out = runWithStdin('backend/ops/check_contracts.py\n')
    expect(out).toContain('跳过')
    expect(out).toContain('未触及')
  })

  it('清单为空时同样不报错', () => {
    expect(() => runWithStdin('\n')).not.toThrow()
  })
})
