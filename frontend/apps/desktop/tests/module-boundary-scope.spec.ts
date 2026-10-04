/**
 * 模块错误态作用域用例（需求 01-7）：模块**加载 / 清单失败**只阻断「归属该失败模块」的路由；
 * 免登录 / 基础路由（`/login` / `/403` / `/404` / `/500`）与平台自身路由不受影响。
 */
// kiwi_id: 2243

import { DEFAULT_PUBLIC_PATHS } from '@bms/core'
import { describe, expect, it } from 'vitest'

import { blocksModuleFailure, type ModuleErrorState } from '@/module/boundary'

/** 失败模块（演示：槽位样例模块）。 */
const FAILED: ModuleErrorState = { module: 'slot-sample', version: '0.1.0', reason: '加载失败' }

/** 清单失败（宿主兜底记录：`modules.json`）。 */
const MANIFEST_FAILED: ModuleErrorState = { module: 'modules.json', version: '', reason: '清单不可读' }

/**
 * 判定辅助。
 *
 * @param path 目标路径。
 * @param routeModule 目标路由归属模块（平台路由为 undefined）。
 * @param failure 失败态。
 */
function blocked(path: string, routeModule: string | undefined, failure: ModuleErrorState | null = FAILED): boolean {
  return blocksModuleFailure({ failure, path, routeModule, publicPaths: DEFAULT_PUBLIC_PATHS })
}

describe('blocksModuleFailure（Kiwi 2243）', () => {
  it('无失败态：不阻断任何路由', () => {
    expect(blocked('/demo', 'demo', null)).toBe(false)
  })

  it('失败模块自身路由：阻断', () => {
    expect(blocked('/slot-sample', 'slot-sample')).toBe(true)
  })

  it('免登录 / 基础路由：不阻断（含子路径）', () => {
    for (const path of ['/login', '/login/qr', '/403', '/404', '/500']) {
      expect(blocked(path, 'slot-sample')).toBe(false)
    }
  })

  it('其他模块路由与平台自身路由：不阻断', () => {
    expect(blocked('/demo', 'demo')).toBe(false)
    expect(blocked('/', undefined)).toBe(false)
    expect(blocked('/org/users', undefined)).toBe(false)
  })

  it('模块清单失败（modules.json）：不阻断宿主页面（保住登录与错误页可达）', () => {
    expect(blocked('/login', undefined, MANIFEST_FAILED)).toBe(false)
    expect(blocked('/demo', 'demo', MANIFEST_FAILED)).toBe(false)
  })
})
