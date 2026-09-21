// kiwi_id: 965
/** 文件领域纯函数用例（06_07）：归一 / 校验 / 模式决策 / 分片计划 / 进度聚合 / 元数据 / 增量 SHA-256 / 错误码。 */

import { describe, expect, it } from 'vitest'

import {
  FILE_WHOLE_MAX_SIZE,
  applyFileSelection,
  checkFileMeta,
  checkImageDimension,
  createSha256,
  decideImageCompress,
  decideUploadMode,
  fileExtOf,
  fileListSummary,
  fileRefLabel,
  isFileErrorCode,
  isImageFile,
  isLocalFileRef,
  localFileRefId,
  matchAccept,
  mergeFileRefs,
  mergePartProgress,
  missingParts,
  moveFileRef,
  normalizeDedupRef,
  normalizeFileRef,
  normalizeFileRefs,
  normalizeFileValue,
  normalizePartResult,
  normalizeStoredFile,
  normalizeUploadSession,
  parseAcceptList,
  planParts,
  removeFileRef,
  resolveFileErrorText,
  retryDelayMs,
  shouldSkipCompress,
  type FileMeta,
  type FileRef,
} from '@bms/core'

/** 文本编码为字节。 */
function bytesOf(text: string): Uint8Array {
  return new TextEncoder().encode(text)
}

describe('createSha256 增量哈希', () => {
  it('标准向量：空串 / abc / 多块长输入', () => {
    expect(createSha256().digestToHex()).toBe('e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
    const abc = createSha256()
    abc.update(bytesOf('abc'))
    expect(abc.digestToHex()).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    const long = createSha256()
    long.update(bytesOf('abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq'))
    expect(long.digestToHex()).toBe('248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1')
  })

  it('分块追加与一次追加一致（跨块边界）', () => {
    const oneShot = createSha256()
    const chunked = createSha256()
    const data = new Uint8Array(200).map((_, index) => index % 251)
    oneShot.update(data)
    for (let offset = 0; offset < data.length; offset += 7) {
      chunked.update(data.subarray(offset, Math.min(offset + 7, data.length)))
    }
    expect(chunked.digestToHex()).toBe(oneShot.digestToHex())
  })

  it('digestToHex 非破坏性且可复位', () => {
    const hasher = createSha256()
    hasher.update(bytesOf('abc'))
    const first = hasher.digestToHex()
    expect(hasher.digestToHex()).toBe(first)
    hasher.reset()
    hasher.update(bytesOf('abc'))
    expect(hasher.digestToHex()).toBe(first)
  })
})

describe('类型与校验', () => {
  it('解析接受类型并做扩展名 + MIME 双重匹配', () => {
    expect(parseAcceptList('.pdf, image/* ; .PDF')).toEqual(['.pdf', 'image/*'])
    expect(fileExtOf('a.PDF')).toBe('pdf')
    expect(fileExtOf('noext')).toBe('')
    expect(isImageFile('a.png', '')).toBe(true)
    expect(isImageFile('a.bin', 'image/webp')).toBe(true)
    expect(matchAccept('a.pdf', 'application/pdf', '.pdf')).toBe(true)
    expect(matchAccept('a.png', 'image/png', 'image/*')).toBe(true)
    expect(matchAccept('a.png', 'image/png', '.pdf')).toBe(false)
    expect(matchAccept('a.png', 'image/png', '')).toBe(true)
  })

  it('校验空文件 / 类型 / 大小', () => {
    expect(checkFileMeta({ name: 'a.pdf', size: 0, mime: 'application/pdf' }).code).toBe(50102)
    expect(checkFileMeta({ name: 'a.png', size: 10, mime: 'image/png' }, { kind: 'image' }).valid).toBe(true)
    expect(checkFileMeta({ name: 'a.txt', size: 10, mime: 'text/plain' }, { kind: 'image' }).code).toBe(50101)
    expect(checkFileMeta({ name: 'a.pdf', size: 2048, mime: 'application/pdf' }, { accept: '.pdf', maxSize: 1024 }).code).toBe(50102)
    expect(checkFileMeta({ name: 'a.pdf', size: 1024, mime: 'application/pdf' }, { accept: '.pdf' }).valid).toBe(true)
  })

  it('校验图片尺寸与比例', () => {
    expect(checkImageDimension(undefined, { aspect: 1 }).valid).toBe(true)
    expect(checkImageDimension({ width: 100, height: 100 }, { aspect: 1 }).valid).toBe(true)
    expect(checkImageDimension({ width: 200, height: 100 }, { aspect: 1 }).valid).toBe(false)
    expect(checkImageDimension({ width: 100, height: 100 }, { minWidth: 200 }).valid).toBe(false)
  })

  it('压缩决策：超边长 / 超体积 / 超大图跳过', () => {
    const meta: FileMeta = { name: 'a.png', size: 512, mime: 'image/png', dimension: { width: 3000, height: 1000 } }
    expect(decideImageCompress(meta).compress).toBe(true)
    expect(decideImageCompress({ ...meta, dimension: { width: 100, height: 100 }, size: 2 * 1024 * 1024 }).compress).toBe(true)
    expect(decideImageCompress({ ...meta, dimension: { width: 100, height: 100 }, size: 512 }).compress).toBe(false)
    const huge = decideImageCompress({ ...meta, size: 30 * 1024 * 1024 })
    expect(huge.compress).toBe(false)
    expect(huge.skip).toBe(true)
    expect(shouldSkipCompress(30 * 1024 * 1024)).toBe(true)
  })
})

describe('元数据归一', () => {
  it('归一文件引用（兼容 snake_case 与失效标记）', () => {
    const ref = normalizeFileRef({ file_id: 'f1', file_name: 'a.pdf', size: '10', mime_type: 'application/pdf', exists: false })
    expect(ref).toEqual({ id: 'f1', name: 'a.pdf', size: 10, mime: 'application/pdf', exists: false })
    expect(normalizeFileRef({ name: 'x' })).toBeUndefined()
    expect(normalizeFileRefs({ list: [{ id: 'f1', name: 'a' }, { bad: true }] })).toHaveLength(1)
    expect(normalizeFileRefs([{ key: 'k1', width: 10, height: 20 }])[0]?.dimension).toEqual({ width: 10, height: 20 })
    expect(normalizeDedupRef(null)).toBeUndefined()
    expect(normalizeDedupRef({ key: 'dedup-1' })?.id).toBe('dedup-1')
    expect(normalizeStoredFile({ key: 'stored-1' })?.id).toBe('stored-1')
  })

  it('受控值归一与本地占位标识', () => {
    expect(normalizeFileValue('f1', false)).toEqual(['f1'])
    expect(normalizeFileValue(['f1', 'f1', '', undefined, 'f2'], true)).toEqual(['f1', 'f2'])
    expect(normalizeFileValue(['f1', 'f2'], false)).toEqual(['f1'])
    const local = localFileRefId(3)
    expect(local).toBe('local:3')
    expect(isLocalFileRef({ id: local, name: 'x' })).toBe(true)
    expect(isLocalFileRef({ id: 'f1', name: 'x' })).toBe(false)
  })

  it('会话与分片结果归一（兼容 snake_case 与缺省）', () => {
    const session = normalizeUploadSession({ upload_id: 'u1', key: 'k1', part_size: 1024, total_parts: 3, uploaded_parts: [1, '2', 0] })
    expect(session).toEqual({ uploadId: 'u1', key: 'k1', partSize: 1024, totalParts: 3, uploadedParts: [1, 2] })
    const fallback = normalizeUploadSession({ uploadId: 'u2' })
    expect(fallback.partSize).toBe(5 * 1024 * 1024)
    expect(fallback.totalParts).toBe(0)
    expect(normalizePartResult({ part_no: 2, etag: 'e', size: 10 })).toEqual({ partNo: 2, etag: 'e', size: 10 })
  })
})

describe('选择 / 排序 / 合并', () => {
  const refs: FileRef[] = [
    { id: 'f1', name: 'a' },
    { id: 'f2', name: 'b' },
  ]

  it('选择归一与上限截断', () => {
    const selection = applyFileSelection(refs, [{ id: 'f3', name: 'c' }], 2)
    expect(selection.refs.map((ref) => ref.id)).toEqual(['f1', 'f2'])
    expect(selection.exceeded).toBe(true)
    const unlimited = applyFileSelection(refs, [{ id: 'f3', name: 'c' }], 0)
    expect(unlimited.refs).toHaveLength(3)
    expect(unlimited.exceeded).toBe(false)
  })

  it('移除 / 移动 / 合并（入参覆盖且保留原字段）', () => {
    expect(removeFileRef(refs, 'f1').map((ref) => ref.id)).toEqual(['f2'])
    expect(moveFileRef(refs, 0, 1).map((ref) => ref.id)).toEqual(['f2', 'f1'])
    expect(moveFileRef(refs, 5, 0).map((ref) => ref.id)).toEqual(['f1', 'f2'])
    const merged = mergeFileRefs([{ id: 'f1', name: 'a', url: 'u1', size: 10 }], [{ id: 'f1', name: 'a2' }])
    expect(merged[0]).toEqual({ id: 'f1', name: 'a2', url: 'u1', size: 10 })
  })

  it('失效标记与摘要', () => {
    expect(fileRefLabel({ id: 'f9', name: 'x', exists: false })).toBe('x（文件已失效）')
    expect(fileRefLabel({ id: 'f9', name: '', exists: false })).toBe('f9（文件已失效）')
    expect(fileListSummary([])).toBe('—')
    expect(fileListSummary([{ id: 'f1', name: 'a' }, { id: 'f2', name: 'b' }])).toBe('a、b')
  })
})

describe('上传编排纯函数', () => {
  it('模式决策与分片计划', () => {
    expect(decideUploadMode(FILE_WHOLE_MAX_SIZE)).toBe('whole')
    expect(decideUploadMode(FILE_WHOLE_MAX_SIZE + 1)).toBe('multipart')
    const parts = planParts(2 * 1024 * 1024 + 100, 1024 * 1024)
    expect(parts.map((part) => part.partNo)).toEqual([1, 2, 3])
    expect(parts[2]).toEqual({ partNo: 3, start: 2 * 1024 * 1024, end: 2 * 1024 * 1024 + 100, size: 100 })
  })

  it('进度聚合与缺失分片', () => {
    expect(mergePartProgress(0, 100)).toBe(0)
    expect(mergePartProgress(50, 100, 100)).toBe(100)
    expect(mergePartProgress(50, 100, 50)).toBe(75)
    expect(mergePartProgress(0, 0)).toBe(0)
    expect(missingParts([1, 3], 4)).toEqual([2, 4])
    expect(missingParts([], 2)).toEqual([1, 2])
  })

  it('重试退避与错误码', () => {
    expect(retryDelayMs(1)).toBe(1000)
    expect(retryDelayMs(2)).toBe(2000)
    expect(retryDelayMs(10)).toBe(8000)
    expect(isFileErrorCode(50101)).toBe(true)
    expect(isFileErrorCode(50105)).toBe(true)
    expect(isFileErrorCode(40101)).toBe(false)
    expect(resolveFileErrorText(50101)).toBe('文件类型不允许')
    expect(resolveFileErrorText(99999)).toBe('文件上传失败')
    expect(resolveFileErrorText(undefined)).toBe('文件上传失败')
  })
})
