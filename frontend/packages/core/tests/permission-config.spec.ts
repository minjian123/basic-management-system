// kiwi_id: 767
/** 授权编排能力基类用例（08-4-1）：阶段机 / 占位语义 / 四类授权写入 / 幂等提交与上下文刷新 / 失败与撤销。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseNotice,
  BasePermissionConfig,
  PERMISSION_PLACEHOLDER_TEXT,
  type PermissionSnapshot,
} from '../src'

/** 具体授权编排件（可实例化）。 */
class SamplePermissionConfig extends BasePermissionConfig {}

/** 权限上下文样例。 */
class SampleAccess extends BaseAccess {}

/** 提示通知样例。 */
class SampleNotice extends BaseNotice {}

/** 样例授权快照。 */
function snapshot(): PermissionSnapshot {
  return {
    roleId: 'r1',
    nodes: [
      {
        key: 'menu:user',
        label: '用户管理',
        type: 'menu',
        children: [
          {
            key: 'form:user',
            label: '用户表单',
            type: 'form',
            children: [
              { key: 'biz:user', label: '用户业务', type: 'business' },
              { key: 'act:user:create', label: '新增用户', type: 'action' },
            ],
          },
        ],
      },
      { key: 'menu:orphan', label: '未挂接菜单', type: 'menu', detached: true },
    ],
    fieldPerms: [{ formKey: 'form:user', formLabel: '用户表单', fields: [{ key: 'name', label: '姓名' }] }],
    dataScopes: [{ actionKey: 'act:user:list', actionLabel: '查询', expression: '' }],
    subjects: [],
  }
}

/**
 * 构造已就绪且已装载的编排件。
 *
 * @param load 取数处理函数（缺省返回样例快照）。
 */
async function ready(
  load: () => Promise<PermissionSnapshot> = async () => snapshot(),
): Promise<SamplePermissionConfig> {
  const config = new SamplePermissionConfig()
  config.setJobs({ load })
  config.setReady(true)
  await config.load()
  return config
}

describe('BasePermissionConfig 占位语义与取数', () => {
  it('初始为占位态且未装载（不脏、不可保存）', () => {
    const config = new SamplePermissionConfig()
    expect(config.ready).toBe(false)
    expect(config.degraded).toBe(true)
    expect(config.disabled).toBe(true)
    expect(config.phase).toBe('idle')
    expect(config.dirty).toBe(false)
    expect(config.canSave).toBe(false)
    expect(config.loadReady).toBe(false)
    expect(config.submitReady).toBe(false)
    expect(config.refreshReady).toBe(false)
  })

  it('未就绪时不发请求（取数与提交均占位）', async () => {
    const config = new SamplePermissionConfig()
    config.setJobs({
      load: async () => snapshot(),
      submit: async () => ({ recordVersion: 1 }),
    })
    await config.load()
    expect(config.requestCount).toBe(0)

    await expect(config.save()).resolves.toBeUndefined()
    expect(config.requestCount).toBe(0)
    expect(config.errorMessage).toBe(PERMISSION_PLACEHOLDER_TEXT)
  })

  it('就绪但未注入处理函数时不发请求、不再降级', async () => {
    const config = new SamplePermissionConfig()
    config.setReady(true)
    expect(config.degraded).toBe(false)
    expect(config.disabled).toBe(false)
    await expect(config.load()).resolves.toBeUndefined()
    expect(config.requestCount).toBe(0)
  })

  it('取数装载四类授权、同步权限树并记基线', async () => {
    const config = await ready()
    expect(config.requestCount).toBe(1)
    expect(config.phase).toBe('done')
    expect(config.roleId).toBe('r1')
    expect(config.dirty).toBe(false)
    expect(config.tree.nodes.map((node) => node.key)).toEqual(['menu:user', 'menu:orphan'])
    expect(config.fieldPerms[0]?.fields[0]).toMatchObject({ key: 'name', visible: true, editable: true })
    expect(config.dataScopes[0]?.expression).toBe('')
    expect(config.subjects).toEqual([])
  })

  it('取数失败置 failed 并按错误码定位页签（含提示）', async () => {
    const notice = new SampleNotice()
    const config = new SamplePermissionConfig()
    config.notice = notice
    config.setJobs({
      load: async () => {
        throw Object.assign(new Error('菜单未挂接表单'), { code: 30046 })
      },
    })
    config.setReady(true)
    await expect(config.load()).resolves.toBeUndefined()
    expect(config.phase).toBe('failed')
    expect(config.errorMessage).toBe('菜单未挂接表单')
    expect(config.errorTarget?.tab).toBe('tree')
    expect(notice.queue[0]?.type).toBe('error')
  })
})

describe('BasePermissionConfig 四类授权写入', () => {
  it('勾选 / 三态 / 业务只读 / 挂接缺失与树机制同步', async () => {
    const config = await ready()
    expect(config.checkState('menu:user')).toBe('unchecked')
    expect(config.toggleNode('biz:user')).toBe(false)

    expect(config.toggleNode('form:user')).toBe(true)
    expect(config.checkState('form:user')).toBe('checked')
    expect(config.checkState('menu:user')).toBe('indeterminate')
    expect([...config.tree.checked].sort()).toEqual(['biz:user', 'form:user'])

    expect(config.toggleNode('menu:user')).toBe(true)
    expect(config.granted).toEqual({
      menus: ['menu:user'],
      forms: ['form:user'],
      actions: [],
      implied: ['biz:user'],
    })
    expect(config.checkState('absent')).toBeUndefined()
  })

  it('字段权限、数据范围与主体绑定的写入与拒绝', async () => {
    const notice = new SampleNotice()
    const config = await ready()
    config.notice = notice

    expect(config.setFieldPerm('form:user', 'name', { editable: false })).toBe(true)
    expect(config.setFieldPerm('form:user', 'absent', { editable: false })).toBe(false)
    expect(config.setDataScope('act:user:list', 'dept_id = @current_dept')).toBe(true)
    expect(config.setDataScope('act:absent', 'x = 1')).toBe(false)

    expect(config.bindSubject({ id: 'u1', type: 'user', name: '张三' })).toBe(true)
    expect(config.bindSubject({ id: 'u1', type: 'user', name: '张三' })).toBe(false)
    expect(config.unbindSubject('u1')).toBe(true)
    expect(config.unbindSubject('u1')).toBe(false)

    config.subjectLimit = 1
    expect(config.bindSubject({ id: 'u2', type: 'user', name: '李四' })).toBe(true)
    expect(config.bindSubject({ id: 'u3', type: 'user', name: '王五' })).toBe(false)
    expect(notice.queue[0]?.type).toBe('warning')
    expect(notice.queue[0]?.content).toContain('上限')
  })

  it('未就绪或无权时四类授权均不写入', async () => {
    const access = new SampleAccess()
    access.setCodes([])
    const config = await ready()
    config.access = access
    expect(config.canGrant).toBe(false)
    expect(config.toggleNode('menu:user')).toBe(false)
    expect(config.setFieldPerm('form:user', 'name', { visible: false })).toBe(false)
    expect(config.setDataScope('act:user:list', 'x = 1')).toBe(false)
    expect(config.bindSubject({ id: 'u1', type: 'user', name: '张三' })).toBe(false)

    access.setCodes(['role:grant'])
    expect(config.canGrant).toBe(true)
    expect(config.toggleNode('menu:user')).toBe(true)
  })
})

describe('BasePermissionConfig 全量覆盖提交与上下文刷新', () => {
  it('提交成功：基线下移、幂等键随内容、刷新权限上下文', async () => {
    const access = new SampleAccess()
    access.setCodes(['role:grant'])
    const notice = new SampleNotice()
    const keys: string[] = []
    const config = await ready()
    config.access = access
    config.notice = notice
    config.setJobs({
      submit: async (input) => {
        keys.push(input.idempotencyKey)
        return { recordVersion: 3 }
      },
      loadPermissionCodes: async () => ['role:grant', 'user:create'],
    })
    config.toggleNode('menu:user')
    expect(config.dirty).toBe(true)
    expect(config.canSave).toBe(true)

    await expect(config.save()).resolves.toEqual({ recordVersion: 3 })
    expect(config.phase).toBe('done')
    expect(config.dirty).toBe(false)
    expect(config.pendingAccessRefresh).toBe(false)
    expect(config.refreshError).toBe('')
    expect(access.codes).toContain('user:create')
    expect(config.requestCount).toBe(3)
    expect(notice.queue[0]?.type).toBe('success')

    await config.save()
    expect(keys).toHaveLength(2)
    expect(keys[0]).toBe(keys[1])
  })

  it('未注入取码处理函数时不发请求、置待刷新标记（不否定保存成功）', async () => {
    const notice = new SampleNotice()
    const config = await ready()
    config.notice = notice
    config.setJobs({ submit: async () => ({ recordVersion: 1 }) })
    config.toggleNode('menu:user')

    const before = config.requestCount
    await config.save()
    expect(config.phase).toBe('done')
    expect(config.pendingAccessRefresh).toBe(true)
    expect(config.requestCount).toBe(before + 1)
    expect(notice.queue[0]?.type).toBe('warning')

    await expect(config.refreshAccess()).resolves.toBe(false)
    expect(config.requestCount).toBe(before + 1)
  })

  it('取码失败：阶段仍为 done、写刷新错误与待刷新标记', async () => {
    const config = await ready()
    config.setJobs({
      submit: async () => ({ recordVersion: 1 }),
      loadPermissionCodes: async () => {
        throw new Error('权限概要不可用')
      },
    })
    config.toggleNode('menu:user')

    await config.save()
    expect(config.phase).toBe('done')
    expect(config.pendingAccessRefresh).toBe(true)
    expect(config.refreshError).toBe('权限概要不可用')
  })

  it('提交失败保留本地、按错误码定位并可重试', async () => {
    const config = await ready()
    let fail = true
    config.setJobs({
      submit: async () => {
        if (fail) {
          throw Object.assign(new Error('规则表达式非法'), { code: 30047 })
        }
        return { recordVersion: 2 }
      },
    })
    config.toggleNode('menu:user')

    await expect(config.save()).resolves.toBeUndefined()
    expect(config.phase).toBe('failed')
    expect(config.errorTarget?.tab).toBe('scope')
    expect(config.dirty).toBe(true)
    expect(config.granted.menus).toEqual(['menu:user'])

    fail = false
    await expect(config.retry()).resolves.toEqual({ recordVersion: 2 })
    expect(config.phase).toBe('done')
    expect(config.dirty).toBe(false)
  })

  it('进行中重复提交不动作（防重复提交）', async () => {
    const config = await ready()
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    let calls = 0
    config.setJobs({
      submit: async () => {
        calls += 1
        await gate
        return { recordVersion: 1 }
      },
    })
    config.toggleNode('menu:user')

    const pending = config.save()
    expect(config.phase).toBe('saving')
    expect(config.busy).toBe(true)
    await expect(config.save()).resolves.toBeUndefined()
    release()
    await expect(pending).resolves.toEqual({ recordVersion: 1 })
    expect(calls).toBe(1)
  })

  it('未注入提交处理函数时不请求并保留本地变更', async () => {
    const config = await ready()
    const before = config.requestCount
    config.toggleNode('menu:user')

    await expect(config.save()).resolves.toBeUndefined()
    expect(config.requestCount).toBe(before)
    expect(config.dirty).toBe(true)
    expect(config.errorMessage).toBe(PERMISSION_PLACEHOLDER_TEXT)
  })
})

describe('BasePermissionConfig 角色切换 / 撤销 / 复位', () => {
  it('切换角色清空四类授权与基线', async () => {
    const config = await ready()
    config.toggleNode('menu:user')
    config.setRole('r2')
    expect(config.roleId).toBe('r2')
    expect(config.nodes).toEqual([])
    expect(config.fieldPerms).toEqual([])
    expect(config.dataScopes).toEqual([])
    expect(config.subjects).toEqual([])
    expect(config.tree.nodes).toEqual([])
    expect(config.phase).toBe('idle')
    expect(config.dirty).toBe(false)
  })

  it('撤销回滚到基线；复位清错误但保留数据', async () => {
    const config = await ready()
    config.toggleNode('menu:user')
    expect(config.dirty).toBe(true)
    config.discard()
    expect(config.dirty).toBe(false)
    expect(config.granted.menus).toEqual([])

    config.setJobs({
      submit: async () => {
        throw Object.assign(new Error('失败'), { code: 30049 })
      },
    })
    config.toggleNode('menu:user')
    await config.save()
    expect(config.phase).toBe('failed')

    config.reset()
    expect(config.phase).toBe('idle')
    expect(config.errorMessage).toBe('')
    expect(config.errorTarget).toBeUndefined()
    expect(config.granted.menus).toEqual(['menu:user'])
  })

  it('变更经生命周期 update 通知（释放后不再通知）', async () => {
    const config = await ready()
    let updates = 0
    const off = config.onLifecycle((event) => {
      if (event === 'update') {
        updates += 1
      }
    })
    config.setTab('field')
    expect(config.tab).toBe('field')
    expect(updates).toBeGreaterThan(0)

    off()
    config.dispose()
    config.setTab('tree')
    expect(config.tab).toBe('tree')
  })

  it('载荷含内容派生的幂等键与排序后的四类授权', async () => {
    const config = await ready()
    config.toggleNode('menu:user')
    config.setFieldPerm('form:user', 'name', { visible: false })
    config.bindSubject({ id: 'u1', type: 'user', name: '张三' })

    expect(config.payload).toMatchObject({
      roleId: 'r1',
      menus: ['menu:user'],
      forms: ['form:user'],
      actions: [],
      fields: [{ formKey: 'form:user', fieldKey: 'name', visible: false, editable: true }],
      subjects: [{ id: 'u1', type: 'user', name: '张三' }],
    })
    expect(config.idempotencyKey).toMatch(/^perm:r1:[0-9a-f]{8}$/)
  })
})
