// kiwi_id: 2524
/** 上传引擎（09_01）：分片模式必算整文件 + 每片摘要、续传只补缺失、进度按片聚合。 */

import { describe, expect, it } from 'vitest'

import { BaseUploadEngine, type UploadCheckQuery, type UploadInitQuery, type UploadPartQuery } from '@bms/core'

/** 可实例化引擎。 */
class EngineUnderTest extends BaseUploadEngine<unknown> {}

/** 呼叫记录。 */
interface Calls {
  /** 秒传入参。 */
  checks: UploadCheckQuery[]
  /** 初始化入参。 */
  inits: UploadInitQuery[]
  /** 分片入参（含每片摘要）。 */
  parts: UploadPartQuery[]
}

/**
 * 造通路桩（分片 8 字节 / 4 字节一片 / 第 1 片已传）。
 *
 * @returns 通路桩与呼叫记录。
 */
function makeTransport(): { transport: Record<string, unknown>; calls: Calls } {
  const calls: Calls = { checks: [], inits: [], parts: [] }
  const transport = {
    hash: async () => ({ sha256: 'f'.repeat(64), partHashes: ['1'.repeat(64), '2'.repeat(64)] }),
    check: async (query: UploadCheckQuery) => {
      calls.checks.push(query)
      return null
    },
    initiate: async (query: UploadInitQuery) => {
      calls.inits.push(query)
      return { upload_id: 'u1', part_size: 4, total_parts: 2 }
    },
    listParts: async () => ({ uploaded: [1], missing: [2] }),
    uploadPart: async (query: UploadPartQuery) => {
      calls.parts.push(query)
      return { part_no: query.partNo, etag: 'e', size: query.end - query.start }
    },
    complete: async () => ({ id: 'file-1', name: 'a.bin', size: 8, mime: 'application/octet-stream' }),
  }
  return { transport, calls }
}

describe('上传引擎 · 分片契约（09_01）', () => {
  it('分片模式算整文件与每片摘要；秒传带文件名与类型；续传只补缺失片', async () => {
    const engine = new EngineUnderTest()
    const { transport, calls } = makeTransport()
    engine.setReady(true)
    engine.setTransport(transport as never)
    engine.setConfig({ wholeMaxSize: 4, autoDedup: true, partSize: 4 })

    const taskId = engine.enqueue({
      file: { name: 'a.bin' },
      meta: { name: 'a.bin', size: 8, mime: 'application/octet-stream' },
    })
    expect(taskId).toBe('upload-1')
    await engine.start(taskId)

    const task = engine.taskOf('upload-1')
    expect(task?.phase).toBe('done')
    expect(task?.percent).toBe(100)
    expect(task?.fileId).toBe('file-1')

    expect(calls.checks).toHaveLength(1)
    expect(calls.checks[0]).toMatchObject({
      name: 'a.bin',
      size: 8,
      sha256: 'f'.repeat(64),
      mime: 'application/octet-stream',
    })

    expect(calls.inits).toHaveLength(1)
    expect(calls.inits[0]).toMatchObject({ name: 'a.bin', size: 8, sha256: 'f'.repeat(64) })

    expect(calls.parts.map((part) => part.partNo)).toEqual([2])
    expect(calls.parts[0]?.sha256).toBe('2'.repeat(64))
  })

  it('关闭秒传时整包路径不发哈希请求', async () => {
    const engine = new EngineUnderTest()
    let hashCalls = 0
    engine.setReady(true)
    engine.setTransport({
      hash: async () => {
        hashCalls += 1
        return { sha256: 'f'.repeat(64), partHashes: [] }
      },
      check: async () => null,
      uploadWhole: async () => ({ id: 'file-2', name: 'b.bin', size: 4 }),
    } as never)
    engine.setConfig({ wholeMaxSize: 1024, autoDedup: false })

    const taskId = engine.enqueue({ file: { name: 'b.bin' }, meta: { name: 'b.bin', size: 4, mime: 'text/plain' } })
    await engine.start(taskId)

    expect(engine.taskOf(taskId as string)?.phase).toBe('done')
    expect(hashCalls).toBe(0)
  })
})
