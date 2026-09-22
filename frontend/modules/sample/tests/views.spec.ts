// kiwi_id: 983
/** 样例页面渲染与交互用例：列表加载行、表单必填校验（jsdom + @vue/test-utils）。 */

import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { describe, expect, it } from 'vitest'

import SampleForm from '../src/views/SampleForm.vue'
import SampleList from '../src/views/SampleList.vue'

/** 空渲染桩（路由占位组件）。 */
const Blank = { render: () => null }

/**
 * 构造预览路由（与模块声明同构）。
 *
 * @returns 路由实例。
 */
function createTestRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: Blank },
      { path: '/sample', name: 'SampleList', component: Blank },
      { path: '/sample/form/:id?', name: 'SampleForm', component: Blank },
      { path: '/sample/detail/:id', name: 'SampleDetail', component: Blank },
    ],
  })
}

/**
 * 等待占位服务的模拟延迟结束。
 *
 * @param ms 等待毫秒数。
 */
async function wait(ms: number): Promise<void> {
  await new Promise<void>((resolve) => {
    setTimeout(resolve, ms)
  })
  await flushPromises()
}

describe('样例页面（Kiwi 982）', () => {
  it('列表页加载占位数据并渲染行', async () => {
    const router = createTestRouter()
    await router.push('/')
    const wrapper = mount(SampleList, { global: { plugins: [router] } })
    await wait(260)

    expect(wrapper.findAll('[data-test^="row-"]').length).toBeGreaterThan(0)
    expect(wrapper.text()).toContain('示例数据管理')
  })

  it('表单页必填校验：空名称 / 负责人提交时给出错误提示', async () => {
    const router = createTestRouter()
    await router.push('/sample/form')
    const wrapper = mount(SampleForm, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[data-test="sample-form-name-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="sample-form-owner-error"]').exists()).toBe(true)
  })
})
