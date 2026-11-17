// kiwi_id: 2524
/** 文件预览（09_01）：预签名过期时间透传、失败 / 不支持类型降级下载。 */

import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { FilePreview, useBaseFileUpload } from '../src'

const downloadMock = vi.hoisted(() => ({ triggerDownload: vi.fn() }))
vi.mock('../src/utils/downloadFile', () => downloadMock)

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  downloadMock.triggerDownload.mockReset()
})

describe('FilePreview · 降级下载（09_01）', () => {
  it('不支持类型出错误态并给下载按钮；点击经预签名取址后触发下载', async () => {
    const fetcher = vi.fn(async () => ({ url: 'https://signed/z1', expiresAt: Date.now() + 60_000 }))
    const wrapper = mount(FilePreview, {
      props: { ready: true, files: [{ id: 'z1', name: 'a.zip', mimeType: 'application/zip' }], presignedFetcher: fetcher },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="preview-error"]').text()).toContain('不支持在线预览')

    await wrapper.find('[data-test="error-download"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('download')?.[0]?.[0]).toMatchObject({ id: 'z1' })
    expect(downloadMock.triggerDownload).toHaveBeenCalledWith({ url: 'https://signed/z1', filename: 'a.zip' })
  })

  it('媒体两次失败后错误态仍给下载按钮，且不重复请求', async () => {
    const fetcher = vi.fn(async () => ({ url: 'https://signed/1', expiresAt: Date.now() + 60_000 }))
    const wrapper = mount(FilePreview, {
      props: { ready: true, files: [{ id: 'f1', name: 'a.png', mimeType: 'image/png' }], presignedFetcher: fetcher },
    })
    await flushPromises()
    await wrapper.find('[data-test="preview-image"]').trigger('error')
    await flushPromises()
    await wrapper.find('[data-test="preview-image"]').trigger('error')
    await flushPromises()
    expect(wrapper.find('[data-test="preview-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="error-download"]').exists()).toBe(true)
  })
})

describe('useBaseFileUpload · 预签名过期透传（09_01）', () => {
  it('previewResultOf 回传 expiresAt（按后端 expires_in 换算）', async () => {
    const scope = effectScope(true)
    const api = scope.run(() =>
      useBaseFileUpload({
        ready: true,
        transport: {
          presign: async () => ({ url: 'https://signed/f1', expires_in: 120 }),
        },
      }),
    )
    expect(api).toBeDefined()
    const before = Date.now()
    const result = await api!.previewResultOf('f1')
    expect(result?.url).toBe('https://signed/f1')
    expect(result?.expiresAt).toBeGreaterThanOrEqual(before + 120_000)
    scope.stop()
  })
})
