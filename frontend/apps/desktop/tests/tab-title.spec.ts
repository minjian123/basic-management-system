/** 页签标题解析用例（07-06_01 补修）：菜单名优先 / `meta.title` 回退 / 路径兜底 / 不取路由 name。 */

import type { MenuNode } from '@bms/core'
import { describe, expect, it } from 'vitest'

import { resolveTabTitle } from '@/utils/tab-title'

/** 典型菜单树（含嵌套叶子）。 */
const MENU: MenuNode[] = [
  { path: '/', title: '工作台' },
  { path: '/sys', title: '系统管理', children: [{ path: '/sys/users', title: '用户管理' }] },
]

describe('resolveTabTitle（《布局设计 · 主框架》§3.8）', () => {
  it('菜单名优先（顶级与嵌套叶子）', () => {
    expect(resolveTabTitle(MENU, '忽略的标题', '/')).toBe('工作台')
    expect(resolveTabTitle(MENU, '忽略的标题', '/sys/users')).toBe('用户管理')
  })

  it('未命中菜单时回退 meta.title；`meta.title` 缺失 / 非字符串回退路径（不取路由 name）', () => {
    expect(resolveTabTitle(MENU, '用户详情', '/sys/users/1')).toBe('用户详情')
    expect(resolveTabTitle(MENU, undefined, '/unknown')).toBe('/unknown')
    expect(resolveTabTitle(MENU, '', '/unknown')).toBe('/unknown')
    expect(resolveTabTitle(MENU, 42, '/unknown')).toBe('/unknown')
  })
})
