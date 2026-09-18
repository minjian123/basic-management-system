/** 文件预览与审计差异查看用例（07_03）：类型分发 / 预签名重取 / 差异渲染与链校验。 */

import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { AuditDiff, FilePreview } from '../src'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('FilePreview 文件预览（真实数据通路）', () => {
  it('图片按直接地址渲染并支持缩放 / 旋转', async () => {
    const wrapper = mount(FilePreview, {
      props: { ready: true, files: [{ id: 'f1', name: 'a.png', mimeType: 'image/png', url: 'https://x/a.png' }] },
    })
    await flushPromises()
    const image = wrapper.find('[data-test="preview-image"]')
    expect(image.exists()).toBe(true)
    expect(image.attributes('src')).toBe('https://x/a.png')

    await wrapper.find('[data-test="zoom-in"]').trigger('click')
    expect(wrapper.find('[data-test="preview-image"]').attributes('style')).toContain('scale(1.2)')
    await wrapper.find('[data-test="rotate"]').trigger('click')
    expect(wrapper.find('[data-test="preview-image"]').attributes('style')).toContain('rotate(90deg)')
  })

  it('预签名地址获取失败重取一次，仍失败出错误态', async () => {
    const fetcher = vi.fn(async () => ({ url: 'https://signed/1', expiresAt: Date.now() + 60_000 }))
    const wrapper = mount(FilePreview, {
      props: { ready: true, files: [{ id: 'f1', name: 'a.png', mimeType: 'image/png' }], presignedFetcher: fetcher },
    })
    await flushPromises()
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-test="preview-image"]').attributes('src')).toBe('https://signed/1')

    await wrapper.find('[data-test="preview-image"]').trigger('error')
    await flushPromises()
    expect(fetcher).toHaveBeenCalledTimes(2)

    await wrapper.find('[data-test="preview-image"]').trigger('error')
    await flushPromises()
    expect(wrapper.find('[data-test="preview-error"]').text()).toContain('文件加载失败')
    expect(wrapper.emitted('error')?.at(-1)?.[0]).toMatchObject({ reason: 'load-failed' })
  })

  it('文本预览拉取内容，不支持类型降级下载', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ text: async () => 'hello world' })),
    )
    const text = mount(FilePreview, {
      props: {
        ready: true,
        files: [{ id: 't1', name: 'note.txt', mimeType: 'text/plain', url: 'https://x/note.txt' }],
      },
    })
    await flushPromises()
    expect(text.find('[data-test="preview-text"]').text()).toContain('hello world')

    const other = mount(FilePreview, {
      props: { ready: true, files: [{ id: 'z1', name: 'a.zip', mimeType: 'application/zip' }] },
    })
    await flushPromises()
    expect(other.attributes('data-kind')).toBe('other')
    expect(other.find('[data-test="preview-error"]').text()).toContain('不支持在线预览')
    expect(other.emitted('error')?.[0]?.[0]).toMatchObject({ reason: 'unsupported' })
  })
})

describe('AuditDiff 审计差异查看（真实渲染）', () => {
  it('字段级差异类型感知渲染、脱敏原样展示、变更高亮', () => {
    const wrapper = mount(AuditDiff, {
      props: {
        ready: true,
        records: [{ id: 'r1', tableName: 'sys_user', recordId: '1', fields: 4 }],
        diff: [
          { field: 'name', label: '姓名', oldValue: '张三', newValue: '李四' },
          { field: 'amount', label: '金额', oldValue: 1000, newValue: 2000, valueType: 'amount' },
          { field: 'enabled', label: '启用', oldValue: false, newValue: true, valueType: 'boolean' },
          { field: 'phone', label: '手机号', oldValue: '138****8000', newValue: '139****9000' },
          { field: 'extra', label: '新增', newValue: { a: 1 }, valueType: 'json' },
        ],
      },
    })
    expect(wrapper.find('[data-test="diff-name"]').attributes('data-change')).toBe('modified')
    expect(wrapper.find('[data-test="diff-name"]').find('[data-test="diff-old"]').text()).toBe('张三')
    expect(wrapper.find('[data-test="diff-amount"]').find('[data-test="diff-new"]').text()).toContain('2,000')
    expect(wrapper.find('[data-test="diff-enabled"]').find('[data-test="diff-new"]').text()).toBe('是')
    expect(wrapper.find('[data-test="diff-phone"]').find('[data-test="diff-old"]').text()).toBe('138****8000')
    expect(wrapper.find('[data-test="diff-extra"]').attributes('data-change')).toBe('added')
    expect(wrapper.find('[data-test="diff-extra"]').find('[data-test="diff-new"]').text()).toContain('"a": 1')
  })

  it('链字段缩写与校验结果，异常时可定位', async () => {
    const wrapper = mount(AuditDiff, {
      props: {
        ready: true,
        records: [],
        prevHash: 'abcdef0123456789',
        recordHash: 'fedcba9876543210',
        chainVerified: false,
      },
    })
    expect(wrapper.find('[data-test="prev-hash"]').text()).toContain('abcdef01…')
    expect(wrapper.find('[data-test="chain-status"]').text()).toBe('校验异常')

    await wrapper.find('[data-test="locate"]').trigger('click')
    expect(wrapper.emitted('verify')).toHaveLength(1)
  })
})
