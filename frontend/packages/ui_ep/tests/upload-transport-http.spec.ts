// kiwi_id: 2524
/** 上传通路 HTTP 内建实现（09_01）：对齐 03_01 契约的路径 / 请求体 / 每片摘要头 / 批量 ids。 */

import { describe, expect, it, vi, afterEach } from 'vitest'

import { createHttpUploadTransport } from '../src'

/** 统一响应包装（成功）。 */
function wrap(data: unknown): unknown {
  return { code: 0, message: '', data }
}

/**
 * 造 fetch 桩（依路径返回不同 data）。
 *
 * @returns fetch 桩。
 */
function makeFetch(): ReturnType<typeof vi.fn> {
  return vi.fn(async (url: string) => {
    if (url.includes('/files/dedup')) {
      return { ok: true, json: async () => wrap(null) }
    }
    if (url.includes('/multipart') && url.includes('/parts/')) {
      return { ok: true, json: async () => wrap({ part_no: 1, etag: 'e', size: 4 }) }
    }
    if (url.includes('/complete')) {
      return { ok: true, json: async () => wrap({ file_id: 'file-1', size: 8, sha256: 'f'.repeat(64), status: 'completed' }) }
    }
    if (url.includes('/multipart')) {
      return { ok: true, json: async () => wrap({ upload_id: 'u1', part_size: 4, total_parts: 2 }) }
    }
    if (url.includes('/files?ids=')) {
      return { ok: true, json: async () => wrap({ list: [], total: 0, page: 1, size: 10 }) }
    }
    return { ok: true, json: async () => wrap(null) }
  })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('上传通路 HTTP · 契约对齐（09_01）', () => {
  it('秒传 POST 体 / 分片路径 / 每片摘要头 / 合并与取消', async () => {
    const fetchMock = makeFetch()
    vi.stubGlobal('fetch', fetchMock)
    const transport = createHttpUploadTransport({ endpoint: '/api/v1', headers: { Authorization: 'Bearer t' } })

    await transport.check({ name: 'a.bin', size: 8, sha256: 'f'.repeat(64), mime: 'application/octet-stream' })
    const checkCall = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(checkCall[0]).toBe('/api/v1/files/dedup')
    expect(checkCall[1].method).toBe('POST')
    expect(JSON.parse(String(checkCall[1].body))).toEqual({
      name: 'a.bin',
      size: 8,
      sha256: 'f'.repeat(64),
      mime: 'application/octet-stream',
    })

    await transport.initiate({ name: 'a.bin', size: 8, mime: 'application/octet-stream', sha256: 'f'.repeat(64) })
    const initCall = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(initCall[0]).toBe('/api/v1/files/multipart')
    expect(JSON.parse(String(initCall[1].body))).toEqual({
      name: 'a.bin',
      size: 8,
      sha256: 'f'.repeat(64),
      mime: 'application/octet-stream',
    })

    await transport.uploadPart({
      uploadId: 'u1',
      partNo: 2,
      file: new Blob(['abcd']),
      start: 0,
      end: 4,
      sha256: '2'.repeat(64),
    })
    const partCall = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(partCall[0]).toBe('/api/v1/files/multipart/u1/parts/2')
    expect(partCall[1].method).toBe('PUT')
    expect((partCall[1].headers as Record<string, string>)['X-Part-Sha256']).toBe('2'.repeat(64))
    expect((partCall[1].headers as Record<string, string>).Authorization).toBe('Bearer t')

    await transport.listParts({ uploadId: 'u1' })
    expect(String((fetchMock.mock.calls[3] as [string])[0])).toBe('/api/v1/files/multipart/u1')

    await transport.complete({ uploadId: 'u1' })
    expect(String((fetchMock.mock.calls[4] as [string])[0])).toBe('/api/v1/files/multipart/u1/complete')

    await transport.abort({ uploadId: 'u1' })
    expect(String((fetchMock.mock.calls[5] as [string])[0])).toBe('/api/v1/files/multipart/u1')
    expect((fetchMock.mock.calls[5] as [string, RequestInit])[1].method).toBe('DELETE')
  })

  it('批量回显走 GET /files?ids=；无摘要时不下发 X-Part-Sha256', async () => {
    const fetchMock = makeFetch()
    vi.stubGlobal('fetch', fetchMock)
    const transport = createHttpUploadTransport({ endpoint: '/api/v1' })

    await transport.resolveFiles({ ids: ['1', '2'] })
    expect(String((fetchMock.mock.calls[0] as [string])[0])).toBe('/api/v1/files?ids=1%2C2')

    await transport.uploadPart({ uploadId: 'u1', partNo: 1, file: new Blob(['abcd']), start: 0, end: 4 })
    const headers = (fetchMock.mock.calls[1] as [string, RequestInit])[1].headers as Record<string, string>
    expect(headers['X-Part-Sha256']).toBeUndefined()
  })

  it('文件对象不可用时抛 50104（不发起请求）', async () => {
    const fetchMock = makeFetch()
    vi.stubGlobal('fetch', fetchMock)
    const transport = createHttpUploadTransport()
    await expect(transport.uploadPart({ uploadId: 'u1', partNo: 1, file: undefined, start: 0, end: 4 })).rejects.toThrow(
      '文件对象不可用',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
