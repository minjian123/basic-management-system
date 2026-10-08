// kiwi_id: 768（旧口径；新口径用例编号于测试步登记后回填）
/** 授权编排能力基类用例（08-4-3，新口径）：占位语义 / 四类授权写入 / 三类提交与用户差量 / 幂等与上下文刷新。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseNotice,
  BasePermissionConfig,
  PERMISSION_PLACEHOLDER_TEXT,
  type AssignedUser,
  type PermissionMetadata,
  type PermissionSnapshot,
} from '../src'

/** 具体授权编排件（可实例化）。 */
class SamplePermissionConfig extends BasePermissionConfig {}

/** 权限上下文样例。 */
class SampleAccess extends BaseAccess {}

/** 提示通知样例。 */
class SampleNotice extends BaseNotice {}

/** 样例元数据。 */
const METADATA: PermissionMetadata = {
  menus: [
    { id: 'menu:user', name: '用户管理', children: [{ id: 'menu:user:list', name: '用户列表' }] },
    { id: 'menu:orphan', name: '未挂接菜单' },
  ],
  forms: [
    { id: 'form:user', name: '用户表单', menuIds: ['menu:user', 'menu:user:list'] },
    { id: 'form:free', name: '无入口表单', menuIds: [] },
  ],
  actions: [{ id: 'act:user:create', name: '新增用户' }],
  fields: [
    { id: 'field:name', name: '姓名' },
    { id: 'field:salary', name: '薪资' },
  ],
  formActions: { 'form:user': ['act:user:create'] },
  formFields: { 'form:user': ['field:name', 'field:salary'] },
  dictTypes: [{ id: 'dict:user', code: 'user', name: '用户字典' }],
  extensions: [],
}

/** 样例授权快照。 */
function snapshot(): PermissionSnapshot {
  return { roleId: 'r1', entries: [], fieldEntries: [], dataScopeEntries: [], users: [] }
}

/** 样例用户。 */
function user(id: string): AssignedUser {
  return { id, username: id, name: id, status: 'enabled' }
}

/** 构造就绪且已装载的实例。 */
async function ready(config: SamplePermissionConfig, grants: PermissionSnapshot = snapshot()): Promise<void> {
  config.setJobs({ loadMetadata: async () => METADATA, loadGrants: async () => grants })
  config.setReady(true)
  await config.load()
}

/** 注入三类提交处理函数（返回给定版本）。 */
function injectSubmits(
  config: SamplePermissionConfig,
  calls: string[],
  version = 1,
): void {
  config.setJobs({
    submitPermissions: async (input) => {
      calls.push(`perm:${input.idempotencyKey}`)
      return { version }
    },
    submitFields: async () => {
      calls.push('field')
      return {}
    },
    submitDataScopes: async () => {
      calls.push('scope')
      return {}
    },
  })
}

describe('capabilities/permission-config（新口径）', () => {
  it('占位语义：未就绪不发请求、降级且禁用', async () => {
    const config = new SamplePermissionConfig()
    config.setJobs({ loadMetadata: async () => METADATA, loadGrants: async () => snapshot() })
    expect(config.ready).toBe(false)
    expect(config.degraded).toBe(true)
    expect(config.disabled).toBe(true)
    await config.load()
    expect(config.requestCount).toBe(0)
  })

  it('就绪未注入处理函数：不发请求、不再降级', async () => {
    const config = new SamplePermissionConfig()
    config.setReady(true)
    expect(config.degraded).toBe(false)
    expect(config.disabled).toBe(false)
    await config.load()
    expect(config.requestCount).toBe(0)
  })

  it('装载：元数据 + 授权并行取数，初始不脏', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    expect(config.requestCount).toBe(2)
    expect(config.dirty).toBe(false)
    expect(config.metadata.forms).toHaveLength(2)
    expect(config.checkMenuState('menu:user')).toBe('unchecked')
  })

  it('菜单勾选：级联与连带；挂接缺失拒绝；三态', () => {
    const config = new SamplePermissionConfig()
    return ready(config).then(() => {
      expect(config.toggleMenu('menu:orphan')).toBe(false)
      expect(config.toggleMenu('menu:user')).toBe(true)
      expect(config.checkMenuState('menu:user')).toBe('checked')
      expect(config.checkMenuState('menu:user:list')).toBe('checked')
      expect(config.formSources('form:user')).toEqual(['menu:user', 'menu:user:list'])
      expect(config.dirty).toBe(true)
    })
  })

  it('操作 / 字段 / 数据权限写入与来源判定', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    expect(config.toggleAction('act:user:create', '0')).toBe(true)
    expect(config.actionSources('act:user:create')).toEqual(['0'])
    expect(config.setFieldPerm('form:user', 'field:name', { visible: false })).toBe(true)
    expect(config.setFieldPerm('form:user', 'field:absent', { visible: false })).toBe(false)
    expect(config.fieldPayload.entries).toHaveLength(1)
    expect(config.setDataScope('dict:user', 'select', [{ itemCode: 'enabled' }])).toBe(true)
    expect(config.dataScopePayload.entries).toHaveLength(1)
    config.setDataScope('dict:user', 'select', [])
    expect(config.dataScopePayload.entries).toEqual([])
  })

  it('用户分配去重与解绑；撤销回滚', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    expect(config.bindUsers([user('u1'), user('u1')])).toBe(true)
    expect(config.users.map((item) => item.id)).toEqual(['u1'])
    expect(config.bindUsers([user('u1')])).toBe(false)
    expect(config.unbindUser('u1')).toBe(true)
    expect(config.users).toHaveLength(0)
    config.bindUsers([user('u2')])
    expect(config.dirty).toBe(true)
    config.discard()
    expect(config.dirty).toBe(false)
    expect(config.users).toHaveLength(0)
  })

  it('保存：三类顺序提交 + 用户差量 + 上下文刷新', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    const access = new SampleAccess()
    access.setCodes(['role:grant'])
    config.setAccess(access)
    const calls: string[] = []
    config.setJobs({
      submitPermissions: async () => {
        calls.push('perm')
        return { version: 7 }
      },
      submitFields: async () => {
        calls.push('field')
        return {}
      },
      submitDataScopes: async () => {
        calls.push('scope')
        return {}
      },
      saveUsers: async (input) => {
        calls.push(`users:${input.added.join(',')}:${input.removed.join(',')}`)
        return {}
      },
      loadPermissionCodes: async () => ['role:grant', 'user:create'],
    })
    config.toggleMenu('menu:user')
    config.bindUsers([user('u1')])
    expect(config.canSave).toBe(true)
    const result = await config.save()
    expect(result).toEqual({ version: 7 })
    expect(calls).toEqual(['perm', 'field', 'scope', 'users:u1:'])
    expect(config.phase).toBe('done')
    expect(config.pendingAccessRefresh).toBe(false)
    expect([...access.codes]).toContain('user:create')
    expect(config.dirty).toBe(false)
  })

  it('未注入取码：不发刷新请求，仅置待刷新标记', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    const access = new SampleAccess()
    access.setCodes(['role:grant'])
    config.setAccess(access)
    injectSubmits(config, [])
    const before = config.requestCount
    config.toggleMenu('menu:user')
    await config.save()
    expect(config.phase).toBe('done')
    expect(config.pendingAccessRefresh).toBe(true)
    expect(config.requestCount).toBe(before + 3)
  })

  it('未注入提交：占位不请求、写占位文案、保留本地', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    const before = config.requestCount
    config.toggleMenu('menu:user')
    await expect(config.save()).resolves.toBeUndefined()
    expect(config.requestCount).toBe(before)
    expect(config.errorMessage).toBe(PERMISSION_PLACEHOLDER_TEXT)
    expect(config.dirty).toBe(true)
  })

  it('提交失败：按错误码定位页签、保留本地、重试恢复', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    let fail = true
    config.setJobs({
      submitPermissions: async () => ({}),
      submitFields: async () => {
        if (fail) {
          throw Object.assign(new Error('字段不匹配'), { code: 30049 })
        }
        return {}
      },
      submitDataScopes: async () => ({}),
    })
    config.toggleMenu('menu:user')
    await expect(config.save()).resolves.toBeUndefined()
    expect(config.phase).toBe('failed')
    expect(config.errorTarget?.tab).toBe('form')
    expect(config.dirty).toBe(true)
    fail = false
    await config.retry()
    expect(config.phase).toBe('done')
    expect(config.dirty).toBe(false)
  })

  it('无权（缺写权限码）不可保存与编辑', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    const access = new SampleAccess()
    access.setCodes([])
    config.setAccess(access)
    injectSubmits(config, [])
    expect(config.canSave).toBe(false)
    expect(config.toggleMenu('menu:user')).toBe(false)
    access.setCodes(['role:grant'])
    expect(config.toggleMenu('menu:user')).toBe(true)
  })

  it('提示通知：保存成功入队', async () => {
    const config = new SamplePermissionConfig()
    await ready(config)
    const notice = new SampleNotice()
    config.notice = notice
    injectSubmits(config, [])
    config.toggleMenu('menu:user')
    await config.save()
    expect(notice.queue.length).toBeGreaterThan(0)
  })
})
