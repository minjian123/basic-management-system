// kiwi_id: 2525
/** 页面帮助上下文派生（09_02）：模块锚点 / 表单业务码 / 父级回溯 / 锚点判定。 */

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'

import { resetAppCapabilities } from '@/capabilities'
import { usePageHelpContext, type UsePageHelpContextResult } from '@/composables/usePageHelpContext'
import { useMenuStore } from '@/stores/menu'

/**
 * 挂载探针并取组合式结果。
 *
 * @param path 当前路径。
 * @returns 组合式结果。
 */
async function mountProbe(path: string): Promise<UsePageHelpContextResult> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push(path)
  await router.isReady()
  let api: UsePageHelpContextResult | undefined
  const Probe = defineComponent({
    setup() {
      api = usePageHelpContext()
      return () => null
    },
  })
  mount(Probe, { global: { plugins: [pinia, router] } })
  expect(api).toBeDefined()
  return api as UsePageHelpContextResult
}

afterEach(() => {
  resetAppCapabilities()
})

describe('usePageHelpContext（09_02）', () => {
  it('当前路径直接命中：取模块段与表单业务码，锚点可用', async () => {
    const api = await mountProbe('/system/user')
    const menu = useMenuStore()
    menu.$patch({
      helpKeyByPath: { '/system/user': 'platform:system:user::' },
      formIdByPath: { '/system/user': 'f1' },
      forms: {
        f1: {
          id: 'f1',
          menuId: 'm1',
          businessCode: 'user',
          visibleButtonCodes: [],
          fieldPerms: {},
          helpKey: 'platform:system:user::',
          fieldHelpKeys: {},
          buttonHelpKeys: {},
        },
      },
    })

    expect(api.help.value.context).toMatchObject({ productKey: 'platform', moduleKey: 'system', formKey: 'user' })
    expect(api.help.value.anchorAvailable).toBe(true)
    expect(api.help.value.ready).toBe(false)
  })

  it('父级回溯：当前路径无锚点时向父路径取模块段', async () => {
    const api = await mountProbe('/system/dept/detail')
    const menu = useMenuStore()
    menu.$patch({
      helpKeyByPath: { '/system': 'platform:system:::' },
      formIdByPath: {},
      forms: {},
    })

    expect(api.help.value.context).toMatchObject({ moduleKey: 'system' })
    expect(api.help.value.context).not.toHaveProperty('formKey')
    expect(api.help.value.anchorAvailable).toBe(true)
  })

  it('无锚点：锚点不可用（页内入口不显示）；表单锚点亦算锚点', async () => {
    const empty = await mountProbe('/system/user')
    useMenuStore().$patch({ helpKeyByPath: {}, formIdByPath: {}, forms: {} })
    expect(empty.help.value.anchorAvailable).toBe(false)

    const withForm = await mountProbe('/system/user')
    useMenuStore().$patch({
      helpKeyByPath: {},
      formIdByPath: { '/system/user': 'f1' },
      forms: {
        f1: {
          id: 'f1',
          menuId: 'm1',
          businessCode: 'user',
          visibleButtonCodes: [],
          fieldPerms: {},
          helpKey: 'platform::user::',
          fieldHelpKeys: {},
          buttonHelpKeys: {},
        },
      },
    })
    expect(withForm.help.value.context).toMatchObject({ formKey: 'user' })
    expect(withForm.help.value.anchorAvailable).toBe(true)
  })

  it('字段 / 动作键默认空，setter 写入后进入上下文', async () => {
    const api = await mountProbe('/system/user')
    useMenuStore().$patch({
      helpKeyByPath: { '/system/user': 'platform:system:user::' },
      formIdByPath: { '/system/user': 'f1' },
      forms: {
        f1: {
          id: 'f1',
          menuId: 'm1',
          businessCode: 'user',
          visibleButtonCodes: [],
          fieldPerms: {},
          helpKey: null,
          fieldHelpKeys: {},
          buttonHelpKeys: {},
        },
      },
    })
    expect(api.help.value.context.fieldKey).toBeUndefined()

    api.setFieldKey('username')
    api.setActionCode('user:create')
    expect(api.help.value.context).toMatchObject({ fieldKey: 'username', actionCode: 'user:create' })
  })
})
