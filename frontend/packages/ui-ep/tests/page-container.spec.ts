/** 页面容器用例（03_05）。 */

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { PageContainer } from '../src'

const stubs = {
  ElButton: { template: '<button><slot /></button>' },
  ElBreadcrumb: { template: '<nav class="el-breadcrumb"><slot /></nav>' },
  ElBreadcrumbItem: { props: ['to'], template: '<span class="el-breadcrumb-item"><slot /></span>' },
}

describe('PageContainer', () => {
  it('渲染标题 / 描述 / 面包屑 / 工具栏 / 底部', () => {
    const wrapper = mount(PageContainer, {
      props: {
        title: '用户详情',
        description: '查看与编辑用户',
        breadcrumb: [{ title: '系统管理' }, { title: '用户管理', path: '/system/user' }],
        showFooter: true,
      },
      slots: { extra: '<button data-test="extra">保存</button>', footer: '<div data-test="footer">底部</div>', default: '<div data-test="content">内容</div>' },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('用户详情')
    expect(wrapper.text()).toContain('查看与编辑用户')
    expect(wrapper.findAll('.el-breadcrumb-item')).toHaveLength(2)
    expect(wrapper.find('[data-test="extra"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="footer"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
    expect(wrapper.classes()).toContain('is-sticky')
  })

  it('返回与刷新事件', async () => {
    const wrapper = mount(PageContainer, {
      props: { title: 'T', showBack: true },
      slots: { extra: '<button data-test="refresh" @click="$emit(\'x\')">R</button>' },
      global: { stubs },
    })
    await wrapper.find('[data-test="page-back"]').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })

  it('无头信息与底部时仅渲染内容区', () => {
    const wrapper = mount(PageContainer, { slots: { default: '<div data-test="content">内容</div>' }, global: { stubs } })
    expect(wrapper.find('.bms-page-container__header').exists()).toBe(false)
    expect(wrapper.find('.bms-page-container__footer').exists()).toBe(false)
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
  })
})
