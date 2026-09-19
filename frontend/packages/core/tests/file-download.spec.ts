// kiwi_id: 769
/** 下载触发能力基类用例（08-5-1）：取址顺序 / 占位 / 阶段与重试 / 预签名回退 / blob 通路。 */

import { describe, expect, it } from 'vitest'

import { BaseFileDownload, BasePresignedUrl, DOWNLOAD_PLACEHOLDER_TEXT } from '../src'

/** 具体下载触发（可实例化）。 */
class DemoDownload extends BaseFileDownload {}

/** 具体预签名（可实例化）。 */
class DemoPresigned extends BasePresignedUrl {}

describe('BaseFileDownload 下载触发能力', () => {
  it('占位：未注入触发手段时不动作、写占位文案', async () => {
    const download = new DemoDownload()
    expect(download.ready).toBe(false)
    expect(download.degraded).toBe(true)
    await expect(download.download({ url: 'https://example.test/1.xlsx' })).resolves.toBeUndefined()
    expect(download.errorMessage).toBe(DOWNLOAD_PLACEHOLDER_TEXT)
    expect(download.phase).toBe('idle')
  })

  it('直连 URL 优先并经触发手段下载', async () => {
    const download = new DemoDownload()
    const seen: { url?: string; filename: string }[] = []
    download.trigger = (input) => {
      seen.push({ url: input.url, filename: input.filename })
    }
    download.fetcher = async () => ({ url: 'https://example.test/fetcher.xlsx' })

    await expect(download.download({ url: 'https://example.test/direct.xlsx', filename: 'a.xlsx' })).resolves.toEqual({
      url: 'https://example.test/direct.xlsx',
      filename: 'a.xlsx',
    })
    expect(seen).toEqual([{ url: 'https://example.test/direct.xlsx', filename: 'a.xlsx' }])
    expect(download.phase).toBe('done')
  })

  it('取址顺序：宿主取址先于预签名回退', async () => {
    const download = new DemoDownload()
    const presigned = new DemoPresigned()
    presigned.url = 'https://example.test/presigned.xlsx'
    presigned.expiresAt = Date.now() + 60_000
    download.presigned = presigned
    download.trigger = () => {}
    download.fetcher = async () => ({ url: 'https://example.test/fetcher.xlsx' })
    await expect(download.download({})).resolves.toMatchObject({ url: 'https://example.test/fetcher.xlsx' })

    download.fetcher = undefined
    await expect(download.download({})).resolves.toMatchObject({ url: 'https://example.test/presigned.xlsx' })
  })

  it('取址全失败：置失败并保留请求供重试', async () => {
    const download = new DemoDownload()
    download.trigger = () => {}
    await expect(download.download({ filename: 'a.xlsx' })).resolves.toBeUndefined()
    expect(download.phase).toBe('failed')
    expect(download.errorMessage).toBe('下载地址不可用')

    download.fetcher = async () => ({ url: 'https://example.test/1.xlsx' })
    await expect(download.retry()).resolves.toMatchObject({ url: 'https://example.test/1.xlsx' })
    expect(download.phase).toBe('done')
  })

  it('blob 通路：URL 为空但有二进制载荷时仍触发', async () => {
    const download = new DemoDownload()
    const seen: unknown[] = []
    download.trigger = (input) => {
      seen.push(input.blob)
    }
    download.fetcher = async () => ({ blob: { size: 1 } })
    await expect(download.download({})).resolves.toEqual({ url: '', filename: '' })
    expect(seen).toEqual([{ size: 1 }])
  })

  it('下载中重复调用不动作；复位清状态', async () => {
    const download = new DemoDownload()
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    download.trigger = () => {}
    download.fetcher = async () => {
      await gate
      return { url: 'https://example.test/1.xlsx' }
    }
    const pending = download.download({})
    expect(download.busy).toBe(true)
    await expect(download.download({})).resolves.toBeUndefined()
    release()
    await pending
    download.reset()
    expect(download.phase).toBe('idle')
    expect(download.url).toBe('')
    expect(download.filename).toBe('')
  })

  it('取址抛错置失败并保留文案', async () => {
    const download = new DemoDownload()
    download.trigger = () => {}
    download.fetcher = async () => {
      throw new Error('预签名过期')
    }
    await expect(download.download({})).resolves.toBeUndefined()
    expect(download.phase).toBe('failed')
    expect(download.errorMessage).toBe('预签名过期')
  })
})
