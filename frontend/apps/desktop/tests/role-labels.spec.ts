/** 角色类型文案映射用例（02_03 / Kiwi 2248）：契约四类命中、空值占位、未知取值原样回显。 */
// kiwi_id: 2248

import { describe, expect, it } from 'vitest'

import { ROLE_TYPE_LABELS, roleTypeLabel } from '@/views/system/role/labels'

describe('角色类型文案（02_03）', () => {
  it('契约四类命中映射表', () => {
    expect(ROLE_TYPE_LABELS).toEqual({
      custom: '自定义',
      system: '系统管理员',
      security: '安全管理员',
      audit: '审计管理员',
    })
    expect(roleTypeLabel('custom')).toBe('自定义')
    expect(roleTypeLabel('system')).toBe('系统管理员')
    expect(roleTypeLabel('security')).toBe('安全管理员')
    expect(roleTypeLabel('audit')).toBe('审计管理员')
  })

  it('空值回退 `—`，未知取值原样回显', () => {
    expect(roleTypeLabel(undefined)).toBe('—')
    expect(roleTypeLabel('')).toBe('—')
    expect(roleTypeLabel('other')).toBe('other')
  })
})
