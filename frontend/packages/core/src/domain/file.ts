/**
 * 文件领域纯函数与数据模型：归一 / 校验 / 上限 / 模式决策 / 分片计划 / 进度聚合 /
 * 元数据归一 / 增量 SHA-256（整文件与每片同源）/ 错误码文案。
 *
 * 纯数据、框架无关：不触 DOM、不请求、不依赖渲染框架与第三方库；同输入同输出。
 * 浏览器侧的文件读取、Worker 调度、图片处理与裁剪归各端插件 `utils/`（单一落点）。
 */

import { formatFileSize } from './format'

/** 整包上传阈值（字节，20MB；超限转分片；与后端 `file.upload.max_size` 同源）。 */
export const FILE_WHOLE_MAX_SIZE = 20 * 1024 * 1024
/** 缺省分片大小（字节，5MB；与后端 `DEFAULT_PART_SIZE` 同源，会话返回 `part_size` 覆盖）。 */
export const FILE_PART_SIZE = 5 * 1024 * 1024
/** 单文件大小上限（字节，2GB；与后端 `file.upload.max_file_size` 同源）。 */
export const FILE_MAX_SIZE = 2 * 1024 * 1024 * 1024
/** 分片并发数（缺省 3）。 */
export const FILE_PART_CONCURRENCY = 3
/** 多文件并发数（缺省 3）。 */
export const FILE_TASK_CONCURRENCY = 3
/** 分片失败重试上限（缺省 3）。 */
export const FILE_RETRY_MAX = 3
/** 重试指数退避基数（毫秒）。 */
export const FILE_RETRY_BASE_MS = 1000
/** 重试指数退避上限（毫秒）。 */
export const FILE_RETRY_MAX_MS = 8000
/** 搜索 / 输入防抖（毫秒，与组织 / 字典同口径）。 */
export const FILE_DEBOUNCE = 300
/** 数量上限缺省值（0 = 不限）。 */
export const FILE_LIMIT_DEFAULT = 0
/** 图片压缩最大边长（像素，超出即压缩）。 */
export const IMAGE_COMPRESS_MAX_EDGE = 1920
/** 图片压缩质量（JPEG / WebP 编码质量）。 */
export const IMAGE_COMPRESS_QUALITY = 0.85
/** 图片压缩触发体积（字节，超出即压缩）。 */
export const IMAGE_COMPRESS_MIN_SIZE = 1024 * 1024
/** 超大图跳过压缩阈值（字节；超出即跳过压缩直接上传，防卡顿）。 */
export const IMAGE_COMPRESS_SKIP_SIZE = 20 * 1024 * 1024
/** 裁剪缺省比例（头像 1:1）。 */
export const IMAGE_CROP_ASPECT = 1
/** 裁剪输出最大边长（像素）。 */
export const IMAGE_CROP_OUTPUT_MAX_EDGE = 1024
/** 宽高比校验容差（相对偏差）。 */
export const IMAGE_ASPECT_TOLERANCE = 0.01
/** 空值占位。 */
export const FILE_EMPTY_VALUE = '—'
/** 多值连接符。 */
export const FILE_JOIN = '、'
/** 失效标记。 */
export const FILE_INVALID_MARK = '文件已失效'
/** 已压缩标记。 */
export const FILE_COMPRESSED_MARK = '已压缩'
/** 数量上限提示前缀。 */
export const FILE_LIMIT_TEXT_PREFIX = '最多上传'
/** 本地占位文件标识前缀（在途上传；不进入受控值）。 */
export const FILE_LOCAL_ID_PREFIX = 'local:'
/** 占位文案。 */
export const FILE_PLACEHOLDER_TEXT = '文件上传未就绪（占位）'
/** 空态文案。 */
export const FILE_EMPTY_TEXT = '暂无文件'
/** 文件错误码文案（50101 ~ 50105，与架构 09 错误码分段 / 组件设计第 4 节同源）。 */
export const FILE_ERROR_TEXTS: Readonly<Record<number, string>> = {
  50101: '文件类型不允许',
  50102: '文件超出大小限制',
  50103: '文件数量超出限制',
  50104: '文件上传失败',
  50105: '文件已失效',
}
/** 上传任务阶段全量。 */
export const UPLOAD_TASK_PHASES = ['pending', 'hashing', 'uploading', 'merging', 'done', 'failed', 'canceled'] as const
/** 上传模式全量。 */
export const UPLOAD_MODES = ['whole', 'multipart'] as const

/** 文件形态（通用文件 / 图片）。 */
export type FileKind = 'file' | 'image'
/** 上传模式（整包 / 分片）。 */
export type UploadMode = (typeof UPLOAD_MODES)[number]
/** 上传任务阶段。 */
export type UploadTaskPhase = (typeof UPLOAD_TASK_PHASES)[number]
/** 裁剪形态（矩形 / 圆形）。 */
export type ImageCropShape = 'rect' | 'circle'

/** 中断信号（最小结构；与浏览器 `AbortSignal` 结构兼容，核心不依赖 DOM 类型）。 */
export interface UploadAbortSignal {
  /** 是否已请求中断。 */
  readonly aborted: boolean
}

/** 文件元信息（件层从文件对象裁剪，核心不触文件对象）。 */
export interface FileMeta {
  /** 文件名。 */
  name: string
  /** 字节数。 */
  size: number
  /** 内容类型。 */
  mime: string
  /** 最后修改时间戳（毫秒，可选）。 */
  lastModified?: number
  /** 原图尺寸（图片，可选）。 */
  dimension?: { width: number; height: number }
}

/** 文件引用（受控值载体；`id` 为文件标识，非文件对象）。 */
export interface FileRef {
  /** 文件标识。 */
  id: string
  /** 文件名。 */
  name: string
  /** 字节数。 */
  size?: number
  /** 内容类型。 */
  mime?: string
  /** 直连地址（后端下发或已解析签名 URL）。 */
  url?: string
  /** 是否存在（批量回显未命中为 `false`）。 */
  exists?: boolean
  /** 原图尺寸（图片）。 */
  dimension?: { width: number; height: number }
  /** 压缩前原始体积（已压缩时记录，供展示）。 */
  originSize?: number
}

/** 分片计划项（`partNo` 从 1 起，与后端同源）。 */
export interface UploadPartPlan {
  /** 分片序号（从 1 起）。 */
  partNo: number
  /** 起始字节（含）。 */
  start: number
  /** 结束字节（不含）。 */
  end: number
  /** 分片字节数。 */
  size: number
}

/** 上传会话（归一结果；`partSize` / `totalParts` 以会话返回为准）。 */
export interface UploadSessionInfo {
  /** 会话标识。 */
  uploadId: string
  /** 目标对象键。 */
  key: string
  /** 分片大小（字节）。 */
  partSize: number
  /** 分片总数。 */
  totalParts: number
  /** 已传分片序号（断点续传；未返回为空数组）。 */
  uploadedParts: number[]
}

/** 上传任务快照（投影与件层消费）。 */
export interface UploadTaskSnapshot {
  /** 任务标识。 */
  id: string
  /** 文件名。 */
  name: string
  /** 字节数。 */
  size: number
  /** 任务阶段。 */
  phase: UploadTaskPhase
  /** 任务进度（0 ~ 100）。 */
  percent: number
  /** 上传模式（决策后写入）。 */
  mode?: UploadMode
  /** 完成后的文件标识。 */
  fileId?: string
  /** 错误码。 */
  errorCode?: number
  /** 错误文案。 */
  errorMessage: string
  /** 已尝试次数（含重试）。 */
  attempts: number
}

/** 校验结果。 */
export interface FileCheckResult {
  /** 是否通过。 */
  valid: boolean
  /** 错误码（不通过时）。 */
  code?: number
  /** 提示文案（通过为空串）。 */
  message: string
}

/** 文件校验选项。 */
export interface FileCheckOptions {
  /** 接受类型（扩展名 / MIME，逗号分隔；空 = 不限制）。 */
  accept?: string
  /** 单文件大小上限（字节；0 = 不限）。 */
  maxSize?: number
  /** 文件形态。 */
  kind?: FileKind
}

/** 图片尺寸与比例校验选项。 */
export interface ImageCheckOptions {
  /** 最小宽度（像素）。 */
  minWidth?: number
  /** 最大宽度（像素）。 */
  maxWidth?: number
  /** 最小高度（像素）。 */
  minHeight?: number
  /** 最大高度（像素）。 */
  maxHeight?: number
  /** 目标宽高比（如 1 表示 1:1）。 */
  aspect?: number
}

/** 图片压缩决策选项。 */
export interface ImageCompressOptions {
  /** 最大边长（像素）。 */
  maxEdge?: number
  /** 触发体积（字节）。 */
  minSize?: number
  /** 跳过阈值（字节）。 */
  skipSize?: number
}

/** 图片压缩决策结果。 */
export interface ImageCompressDecision {
  /** 是否需要压缩。 */
  compress: boolean
  /** 是否超大图跳过（原文件上传）。 */
  skip: boolean
  /** 决策原因（调试与展示）。 */
  reason: string
}

/** 增量 SHA-256 哈希器（纯 TS；整文件与每片同源）。 */
export interface Sha256Hasher {
  /**
   * 追加数据。
   *
   * @param data 字节块。
   */
  update(data: Uint8Array): void
  /**
   * 取摘要（64 位小写十六进制；非破坏性，可重复调用）。
   *
   * @returns 摘要十六进制串。
   */
  digestToHex(): string
  /** 复位（重新开始）。 */
  reset(): void
}

/** 哈希结果（整文件 + 每片）。 */
export interface FileHashResult {
  /** 整文件 SHA-256（64 位小写十六进制）。 */
  sha256: string
  /** 每片 SHA-256（与分片计划同序）。 */
  partHashes: readonly string[]
}

/** 秒传判定入参。 */
export interface DedupQuery {
  /** 整文件 SHA-256。 */
  sha256: string
  /** 文件字节数。 */
  size: number
}

/** 分片初始化入参（线参数构造用）。 */
export interface MultipartInitInput {
  /** 目标对象键（缺省由通路实现生成）。 */
  key?: string
  /** 文件字节数。 */
  size: number
  /** 整文件 SHA-256（可选）。 */
  sha256?: string
  /** 内容类型（可选）。 */
  mime?: string
  /** 分片大小（字节，可选；缺省由后端取基座缺省）。 */
  partSize?: number
}

/** 分片结果（归一结果）。 */
export interface UploadPartResult {
  /** 分片序号。 */
  partNo: number
  /** 分片 etag。 */
  etag: string
  /** 分片字节数。 */
  size: number
}

/** SHA-256 轮常量（FIPS 180-4）。 */
const SHA256_K: readonly number[] = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

/**
 * 创建增量 SHA-256 哈希器（纯 TS，框架无关；整文件与每片可同一遍读取产出）。
 *
 * @returns 哈希器实例。
 */
export function createSha256(): Sha256Hasher {
  const state = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ])
  const buffer = new Uint8Array(64)
  let bufferLength = 0
  let totalBytes = 0

  return {
    update(data: Uint8Array): void {
      totalBytes += data.length
      let offset = 0
      if (bufferLength > 0) {
        const take = Math.min(64 - bufferLength, data.length)
        buffer.set(data.subarray(0, take), bufferLength)
        bufferLength += take
        offset = take
        if (bufferLength === 64) {
          processBlock(state, buffer, 0)
          bufferLength = 0
        }
      }
      while (offset + 64 <= data.length) {
        processBlock(state, data, offset)
        offset += 64
      }
      if (offset < data.length) {
        buffer.set(data.subarray(offset), 0)
        bufferLength = data.length - offset
      }
    },
    digestToHex(): string {
      const copy = new Uint32Array(state)
      const tail = new Uint8Array(64)
      tail.set(buffer.subarray(0, bufferLength), 0)
      tail[bufferLength] = 0x80
      if (bufferLength >= 56) {
        processBlock(copy, tail, 0)
        tail.fill(0, 0, 64)
      }
      const bits = totalBytes * 8
      const high = Math.floor(bits / 4294967296)
      const low = bits % 4294967296
      writeUint32(tail, 56, high)
      writeUint32(tail, 60, low)
      processBlock(copy, tail, 0)
      let hex = ''
      for (const word of copy) {
        hex += word.toString(16).padStart(8, '0')
      }
      return hex
    },
    reset(): void {
      state.set([
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
      ])
      bufferLength = 0
      totalBytes = 0
    },
  }
}

/**
 * 处理一个 512 位分组。
 *
 * @param state 状态字（原地更新）。
 * @param block 字节缓冲。
 * @param offset 分组起始偏移。
 */
function processBlock(state: Uint32Array, block: Uint8Array, offset: number): void {
  const w = new Uint32Array(64)
  for (let i = 0; i < 16; i += 1) {
    w[i] = readUint32(block, offset + i * 4)
  }
  for (let i = 16; i < 64; i += 1) {
    const s0 = rotr(w[i - 15] as number, 7) ^ rotr(w[i - 15] as number, 18) ^ ((w[i - 15] as number) >>> 3)
    const s1 = rotr(w[i - 2] as number, 17) ^ rotr(w[i - 2] as number, 19) ^ ((w[i - 2] as number) >>> 10)
    w[i] = ((w[i - 16] as number) + s0 + (w[i - 7] as number) + s1) >>> 0
  }
  let [a, b, c, d, e, f, g, h] = [state[0] as number, state[1] as number, state[2] as number, state[3] as number, state[4] as number, state[5] as number, state[6] as number, state[7] as number]
  for (let i = 0; i < 64; i += 1) {
    const s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
    const ch = (e & f) ^ (~e & g)
    const temp1 = (h + s1 + ch + (SHA256_K[i] as number) + (w[i] as number)) >>> 0
    const s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
    const maj = (a & b) ^ (a & c) ^ (b & c)
    const temp2 = (s0 + maj) >>> 0
    h = g
    g = f
    f = e
    e = (d + temp1) >>> 0
    d = c
    c = b
    b = a
    a = (temp1 + temp2) >>> 0
  }
  state[0] = ((state[0] as number) + a) >>> 0
  state[1] = ((state[1] as number) + b) >>> 0
  state[2] = ((state[2] as number) + c) >>> 0
  state[3] = ((state[3] as number) + d) >>> 0
  state[4] = ((state[4] as number) + e) >>> 0
  state[5] = ((state[5] as number) + f) >>> 0
  state[6] = ((state[6] as number) + g) >>> 0
  state[7] = ((state[7] as number) + h) >>> 0
}

/**
 * 循环右移（32 位）。
 *
 * @param value 值。
 * @param bits 位数。
 * @returns 移位结果。
 */
function rotr(value: number, bits: number): number {
  return ((value >>> bits) | (value << (32 - bits))) >>> 0
}

/**
 * 读大端 32 位整数。
 *
 * @param bytes 字节缓冲。
 * @param offset 起始偏移。
 * @returns 整数值。
 */
function readUint32(bytes: Uint8Array, offset: number): number {
  return (
    (((bytes[offset] as number) << 24) |
      ((bytes[offset + 1] as number) << 16) |
      ((bytes[offset + 2] as number) << 8) |
      (bytes[offset + 3] as number)) >>>
    0
  )
}

/**
 * 写大端 32 位整数。
 *
 * @param bytes 字节缓冲（原地写入）。
 * @param offset 起始偏移。
 * @param value 整数值。
 */
function writeUint32(bytes: Uint8Array, offset: number, value: number): void {
  bytes[offset] = (value >>> 24) & 0xff
  bytes[offset + 1] = (value >>> 16) & 0xff
  bytes[offset + 2] = (value >>> 8) & 0xff
  bytes[offset + 3] = value & 0xff
}

/**
 * 解析接受类型清单（扩展名 / MIME；逗号 / 分号分隔、小写、去重）。
 *
 * @param accept 接受类型串。
 * @returns 类型清单。
 */
export function parseAcceptList(accept: string): string[] {
  const tokens = accept
    .split(/[,;]/)
    .map((token) => token.trim().toLowerCase())
    .filter((token) => token !== '')
  return [...new Set(tokens)]
}

/**
 * 取文件扩展名（不含点，小写；无扩展名返回空串）。
 *
 * @param name 文件名。
 * @returns 扩展名。
 */
export function fileExtOf(name: string): string {
  const index = name.lastIndexOf('.')
  if (index <= 0 || index === name.length - 1) {
    return ''
  }
  return name.slice(index + 1).toLowerCase()
}

/**
 * 是否图片文件（MIME 或扩展名判定）。
 *
 * @param name 文件名。
 * @param mime 内容类型。
 * @returns 是否图片。
 */
export function isImageFile(name: string, mime: string): boolean {
  if (mime.toLowerCase().startsWith('image/')) {
    return true
  }
  return ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'svg', 'avif', 'heic'].includes(fileExtOf(name))
}

/**
 * 类型白名单匹配（扩展名 + MIME 双重；`accept` 为空视为通过）。
 *
 * @param name 文件名。
 * @param mime 内容类型。
 * @param accept 接受类型串。
 * @returns 是否匹配。
 */
export function matchAccept(name: string, mime: string, accept: string): boolean {
  const list = parseAcceptList(accept)
  if (list.length === 0) {
    return true
  }
  const ext = fileExtOf(name)
  const type = mime.toLowerCase()
  return list.some((token) => {
    if (token.startsWith('.')) {
      return `.${ext}` === token
    }
    if (token.endsWith('/*')) {
      return type.startsWith(token.slice(0, -1))
    }
    if (token.includes('/')) {
      return type === token
    }
    return ext === token
  })
}

/**
 * 文件元信息校验（空文件 / 类型 / 大小；数量由选择归一判定）。
 *
 * @param meta 文件元信息。
 * @param options 校验选项。
 * @returns 校验结果。
 */
export function checkFileMeta(meta: FileMeta, options: FileCheckOptions = {}): FileCheckResult {
  const kind = options.kind ?? 'file'
  if (!Number.isFinite(meta.size) || meta.size <= 0) {
    return { valid: false, code: 50102, message: '文件内容为空' }
  }
  if (kind === 'image' && !isImageFile(meta.name, meta.mime)) {
    return { valid: false, code: 50101, message: resolveFileErrorText(50101) }
  }
  if (!matchAccept(meta.name, meta.mime, options.accept ?? '')) {
    return { valid: false, code: 50101, message: `${resolveFileErrorText(50101)}：${meta.name}` }
  }
  const maxSize = options.maxSize ?? 0
  if (maxSize > 0 && meta.size > maxSize) {
    return {
      valid: false,
      code: 50102,
      message: `${resolveFileErrorText(50102)}（${formatFileSize(maxSize)}）`,
    }
  }
  return { valid: true, message: '' }
}

/**
 * 图片尺寸与比例校验（尺寸缺失视为通过）。
 *
 * @param dimension 图片尺寸。
 * @param options 校验选项。
 * @returns 校验结果。
 */
export function checkImageDimension(
  dimension: { width: number; height: number } | undefined,
  options: ImageCheckOptions = {},
): FileCheckResult {
  if (dimension === undefined) {
    return { valid: true, message: '' }
  }
  const { width, height } = dimension
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    return { valid: true, message: '' }
  }
  if (options.minWidth !== undefined && width < options.minWidth) {
    return { valid: false, code: 50102, message: `图片宽度不得小于 ${options.minWidth}px` }
  }
  if (options.maxWidth !== undefined && width > options.maxWidth) {
    return { valid: false, code: 50102, message: `图片宽度不得大于 ${options.maxWidth}px` }
  }
  if (options.minHeight !== undefined && height < options.minHeight) {
    return { valid: false, code: 50102, message: `图片高度不得小于 ${options.minHeight}px` }
  }
  if (options.maxHeight !== undefined && height > options.maxHeight) {
    return { valid: false, code: 50102, message: `图片高度不得大于 ${options.maxHeight}px` }
  }
  const aspect = options.aspect
  if (aspect !== undefined && aspect > 0) {
    const ratio = width / height
    if (Math.abs(ratio - aspect) / aspect > IMAGE_ASPECT_TOLERANCE) {
      return { valid: false, code: 50102, message: `图片宽高比须为 ${aspect}:1` }
    }
  }
  return { valid: true, message: '' }
}

/**
 * 图片尺寸展示文本（「宽 × 高」；缺失返回空串）。
 *
 * @param dimension 图片尺寸。
 * @returns 展示文本。
 */
export function imageDimensionText(dimension: { width: number; height: number } | undefined): string {
  if (dimension === undefined) {
    return ''
  }
  return `${dimension.width} × ${dimension.height}`
}

/**
 * 归一文件引用（兼容 snake_case；`id` 缺失剔除）。
 *
 * @param raw 原始数据。
 * @returns 文件引用；不可用返回 `undefined`。
 */
export function normalizeFileRef(raw: unknown): FileRef | undefined {
  if (raw === null || typeof raw !== 'object') {
    return undefined
  }
  const source = raw as Record<string, unknown>
  const id = readString(source.id) ?? readString(source.file_id) ?? readString(source.key)
  if (id === undefined) {
    return undefined
  }
  const name = readString(source.name) ?? readString(source.file_name) ?? readString(source.filename) ?? id
  const ref: FileRef = { id, name }
  const size = readNumber(source.size)
  if (size !== undefined) {
    ref.size = size
  }
  const mime = readString(source.mime) ?? readString(source.mime_type) ?? readString(source.content_type)
  if (mime !== undefined) {
    ref.mime = mime
  }
  const url = readString(source.url)
  if (url !== undefined) {
    ref.url = url
  }
  if (source.exists === false || source.deleted === true) {
    ref.exists = false
  }
  const dimension = readDimension(source)
  if (dimension !== undefined) {
    ref.dimension = dimension
  }
  const originSize = readNumber(source.origin_size) ?? readNumber(source.originSize)
  if (originSize !== undefined) {
    ref.originSize = originSize
  }
  return ref
}

/**
 * 归一文件引用列表（兼容数组 / `{ list }` / `{ items }` / `{ data }` 包装）。
 *
 * @param raw 原始数据。
 * @returns 文件引用列表。
 */
export function normalizeFileRefs(raw: unknown): FileRef[] {
  const list = readList(raw)
  const refs: FileRef[] = []
  for (const entry of list) {
    const ref = normalizeFileRef(entry)
    if (ref !== undefined) {
      refs.push(ref)
    }
  }
  return refs
}

/**
 * 受控值归一（单值 / 数组；去重、空值剔除、统一转字符串）。
 *
 * @param value 受控值。
 * @param multiple 是否多选。
 * @returns 标识列表。
 */
export function normalizeFileValue(value: unknown, multiple: boolean): string[] {
  const list = Array.isArray(value) ? value : [value]
  const ids: string[] = []
  for (const entry of list) {
    if (entry === null || entry === undefined || entry === '') {
      continue
    }
    const id = String(entry)
    if (!ids.includes(id)) {
      ids.push(id)
    }
  }
  return multiple ? ids : ids.slice(0, 1)
}

/**
 * 选择归一（多选追加去重；`limit > 0` 超出截断并置 `exceeded`；单选整体替换）。
 *
 * @param current 当前引用。
 * @param incoming 新增引用。
 * @param limit 数量上限（0 不限）。
 * @returns 归一结果。
 */
export function applyFileSelection(
  current: readonly FileRef[],
  incoming: readonly FileRef[],
  limit: number,
): { refs: FileRef[]; exceeded: boolean } {
  const refs = mergeFileRefs(current, incoming)
  const cap = Number.isFinite(limit) && limit > 0 ? Math.floor(limit) : 0
  if (cap === 0 || refs.length <= cap) {
    return { refs, exceeded: false }
  }
  return { refs: refs.slice(0, cap), exceeded: true }
}

/**
 * 移除引用（按 id）。
 *
 * @param refs 引用列表。
 * @param id 文件标识。
 * @returns 新列表。
 */
export function removeFileRef(refs: readonly FileRef[], id: string): FileRef[] {
  return refs.filter((ref) => ref.id !== id)
}

/**
 * 移动引用（多图排序；索引夹取，越界不动作）。
 *
 * @param refs 引用列表。
 * @param from 原索引。
 * @param to 目标索引。
 * @returns 新列表。
 */
export function moveFileRef(refs: readonly FileRef[], from: number, to: number): FileRef[] {
  const next = [...refs]
  if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || from >= next.length || to < 0 || to >= next.length || from === to) {
    return next
  }
  const [moved] = next.splice(from, 1)
  if (moved !== undefined) {
    next.splice(to, 0, moved)
  }
  return next
}

/**
 * 合并引用（按 id 合并，入参覆盖同项；入参缺失的可选字段保留原值）。
 *
 * @param base 基础引用。
 * @param incoming 增量引用。
 * @returns 合并结果。
 */
export function mergeFileRefs(base: readonly FileRef[], incoming: readonly FileRef[]): FileRef[] {
  const result = [...base]
  for (const ref of incoming) {
    const index = result.findIndex((entry) => entry.id === ref.id)
    if (index < 0) {
      result.push({ ...ref })
      continue
    }
    const previous = result[index] as FileRef
    result[index] = {
      ...previous,
      ...ref,
      url: ref.url ?? previous.url,
      size: ref.size ?? previous.size,
      mime: ref.mime ?? previous.mime,
      dimension: ref.dimension ?? previous.dimension,
      originSize: ref.originSize ?? previous.originSize,
      exists: ref.exists ?? previous.exists,
    }
  }
  return result
}

/**
 * 按 id 取引用。
 *
 * @param refs 引用列表。
 * @param id 文件标识。
 * @returns 引用；未命中 `undefined`。
 */
export function findFileRef(refs: readonly FileRef[], id: string): FileRef | undefined {
  return refs.find((ref) => ref.id === id)
}

/**
 * 是否失效引用（批量回显未命中）。
 *
 * @param ref 引用。
 * @returns 是否失效。
 */
export function isFileRefInvalid(ref: FileRef): boolean {
  return ref.exists === false
}

/**
 * 生成本地占位文件标识（在途上传展示用；不进入受控值）。
 *
 * @param seq 序号。
 * @returns 本地标识。
 */
export function localFileRefId(seq: number): string {
  return `${FILE_LOCAL_ID_PREFIX}${seq}`
}

/**
 * 是否本地占位引用（在途上传）。
 *
 * @param ref 引用。
 * @returns 是否本地占位。
 */
export function isLocalFileRef(ref: FileRef): boolean {
  return ref.id.startsWith(FILE_LOCAL_ID_PREFIX)
}

/**
 * 引用展示文案（失效 → 「名称（文件已失效）」；名称缺失回退 id）。
 *
 * @param ref 引用。
 * @returns 展示文案。
 */
export function fileRefLabel(ref: FileRef): string {
  if (isFileRefInvalid(ref)) {
    return `${ref.name || ref.id}（${FILE_INVALID_MARK}）`
  }
  return ref.name || ref.id
}

/**
 * 引用列表摘要（「、」连接；空列表返回空值占位）。
 *
 * @param refs 引用列表。
 * @returns 摘要文本。
 */
export function fileListSummary(refs: readonly FileRef[]): string {
  if (refs.length === 0) {
    return FILE_EMPTY_VALUE
  }
  return refs.map((ref) => fileRefLabel(ref)).join(FILE_JOIN)
}

/**
 * 上传模式决策（`size ≤ wholeMax` 整包，否则分片）。
 *
 * @param size 文件字节数。
 * @param wholeMax 整包阈值（缺省 20MB）。
 * @returns 上传模式。
 */
export function decideUploadMode(size: number, wholeMax: number = FILE_WHOLE_MAX_SIZE): UploadMode {
  const threshold = Number.isFinite(wholeMax) && wholeMax > 0 ? wholeMax : FILE_WHOLE_MAX_SIZE
  return size <= threshold ? 'whole' : 'multipart'
}

/**
 * 分片计划（末片余量；`part_no` 从 1 起）。
 *
 * @param size 文件字节数。
 * @param partSize 分片大小（字节）。
 * @returns 分片计划。
 */
export function planParts(size: number, partSize: number): UploadPartPlan[] {
  const chunk = Number.isFinite(partSize) && partSize > 0 ? Math.floor(partSize) : FILE_PART_SIZE
  const total = Math.ceil(size / chunk)
  const parts: UploadPartPlan[] = []
  for (let index = 0; index < total; index += 1) {
    const start = index * chunk
    const end = Math.min(start + chunk, size)
    parts.push({ partNo: index + 1, start, end, size: end - start })
  }
  return parts
}

/**
 * 分片进度聚合（已传占比 + 在途分片按剩余占比加权；0 ~ 100 整数）。
 *
 * @param doneBytes 已传字节数。
 * @param totalBytes 总字节数。
 * @param inflightPercent 在途分片进度（0 ~ 100，可选）。
 * @returns 聚合进度。
 */
export function mergePartProgress(doneBytes: number, totalBytes: number, inflightPercent?: number): number {
  if (!Number.isFinite(totalBytes) || totalBytes <= 0) {
    return 0
  }
  const doneRatio = Math.min(1, Math.max(0, (Number.isFinite(doneBytes) ? doneBytes : 0) / totalBytes))
  const inflight = Number.isFinite(inflightPercent) ? Math.min(100, Math.max(0, inflightPercent as number)) : 0
  const percent = (doneRatio + (1 - doneRatio) * (inflight / 100)) * 100
  return Math.min(100, Math.max(0, Math.round(percent)))
}

/**
 * 缺失分片（断点续传仅补缺失）。
 *
 * @param uploaded 已传分片序号。
 * @param total 分片总数。
 * @returns 缺失分片序号（升序）。
 */
export function missingParts(uploaded: readonly number[], total: number): number[] {
  const done = new Set(uploaded)
  const missing: number[] = []
  for (let partNo = 1; partNo <= total; partNo += 1) {
    if (!done.has(partNo)) {
      missing.push(partNo)
    }
  }
  return missing
}

/**
 * 图片压缩决策（超最大边长或超触发体积才压；超大图跳过）。
 *
 * @param meta 文件元信息（含尺寸时参与判定）。
 * @param options 决策选项。
 * @returns 决策结果。
 */
export function decideImageCompress(meta: FileMeta, options: ImageCompressOptions = {}): ImageCompressDecision {
  const skipSize = options.skipSize ?? IMAGE_COMPRESS_SKIP_SIZE
  if (meta.size > skipSize) {
    return { compress: false, skip: true, reason: '超大图跳过压缩' }
  }
  const maxEdge = options.maxEdge ?? IMAGE_COMPRESS_MAX_EDGE
  const minSize = options.minSize ?? IMAGE_COMPRESS_MIN_SIZE
  const oversize = meta.dimension !== undefined && (meta.dimension.width > maxEdge || meta.dimension.height > maxEdge)
  if (oversize) {
    return { compress: true, skip: false, reason: '超出最大边长' }
  }
  if (meta.size > minSize) {
    return { compress: true, skip: false, reason: '超出触发体积' }
  }
  return { compress: false, skip: false, reason: '未达压缩阈值' }
}

/**
 * 是否超大图跳过压缩。
 *
 * @param size 字节数。
 * @param skipSize 跳过阈值。
 * @returns 是否跳过。
 */
export function shouldSkipCompress(size: number, skipSize: number = IMAGE_COMPRESS_SKIP_SIZE): boolean {
  return size > skipSize
}

/**
 * 构造秒传判定线参数。
 *
 * @param sha256 整文件 SHA-256。
 * @param size 字节数。
 * @returns 线参数。
 */
export function buildDedupQuery(sha256: string, size: number): Record<string, unknown> {
  return { sha256, size }
}

/**
 * 构造分片初始化线参数（非空才传）。
 *
 * @param input 初始化入参。
 * @returns 线参数。
 */
export function buildMultipartInit(input: MultipartInitInput): Record<string, unknown> {
  const query: Record<string, unknown> = { size: input.size }
  if (input.key !== undefined && input.key !== '') {
    query.key = input.key
  }
  if (input.sha256 !== undefined && input.sha256 !== '') {
    query.sha256 = input.sha256
  }
  if (input.mime !== undefined && input.mime !== '') {
    query.mime = input.mime
  }
  if (input.partSize !== undefined && input.partSize > 0) {
    query.part_size = input.partSize
  }
  return query
}

/**
 * 构造批量元数据线参数。
 *
 * @param ids 文件标识列表。
 * @returns 线参数。
 */
export function buildResolveQuery(ids: readonly string[]): Record<string, unknown> {
  return { ids: ids.join(',') }
}

/**
 * 归一上传会话（兼容 snake_case；`part_size` / `total_parts` 缺失回落缺省）。
 *
 * @param raw 原始会话。
 * @returns 会话信息。
 */
export function normalizeUploadSession(raw: unknown): UploadSessionInfo {
  const source = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const partSize = readNumber(source.part_size) ?? readNumber(source.partSize) ?? FILE_PART_SIZE
  const totalParts = readNumber(source.total_parts) ?? readNumber(source.totalParts) ?? 0
  const uploaded = source.uploaded_parts ?? source.uploadedParts
  const uploadedParts = Array.isArray(uploaded)
    ? uploaded.map((entry) => Number(entry)).filter((entry) => Number.isFinite(entry) && entry >= 1)
    : []
  return {
    uploadId: readString(source.upload_id) ?? readString(source.uploadId) ?? '',
    key: readString(source.key) ?? '',
    partSize: partSize > 0 ? partSize : FILE_PART_SIZE,
    totalParts: totalParts > 0 ? Math.floor(totalParts) : 0,
    uploadedParts,
  }
}

/**
 * 归一分片结果。
 *
 * @param raw 原始分片结果。
 * @returns 分片结果。
 */
export function normalizePartResult(raw: unknown): UploadPartResult {
  const source = raw !== null && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  return {
    partNo: readNumber(source.part_no) ?? readNumber(source.partNo) ?? 0,
    etag: readString(source.etag) ?? '',
    size: readNumber(source.size) ?? 0,
  }
}

/**
 * 归一合并产物为文件引用。
 *
 * @param raw 原始产物。
 * @returns 文件引用；不可用返回 `undefined`。
 */
export function normalizeStoredFile(raw: unknown): FileRef | undefined {
  return normalizeFileRef(raw)
}

/**
 * 归一批量元数据结果。
 *
 * @param raw 原始结果。
 * @returns 文件引用列表。
 */
export function normalizeResolvedFiles(raw: unknown): FileRef[] {
  return normalizeFileRefs(raw)
}

/**
 * 归一秒传命中引用（未命中返回 `undefined`）。
 *
 * @param raw 原始引用。
 * @returns 文件引用；未命中 `undefined`。
 */
export function normalizeDedupRef(raw: unknown): FileRef | undefined {
  if (raw === null || raw === undefined) {
    return undefined
  }
  return normalizeFileRef(raw)
}

/**
 * 重试指数退避（1s 基数、8s 上限）。
 *
 * @param attempt 已尝试次数（从 1 起）。
 * @returns 等待毫秒数。
 */
export function retryDelayMs(attempt: number): number {
  const index = Number.isFinite(attempt) && attempt >= 1 ? Math.floor(attempt) : 1
  const delay = FILE_RETRY_BASE_MS * 2 ** (index - 1)
  return Math.min(FILE_RETRY_MAX_MS, delay)
}

/**
 * 是否文件错误码（50101 ~ 50105）。
 *
 * @param code 错误码。
 * @returns 是否文件错误码。
 */
export function isFileErrorCode(code: number | undefined): boolean {
  return code !== undefined && code >= 50101 && code <= 50105
}

/**
 * 错误码文案（未命中回落「文件上传失败」）。
 *
 * @param code 错误码。
 * @returns 文案。
 */
export function resolveFileErrorText(code: number | undefined): string {
  if (code !== undefined && FILE_ERROR_TEXTS[code] !== undefined) {
    return FILE_ERROR_TEXTS[code] as string
  }
  return FILE_ERROR_TEXTS[50104] as string
}

/**
 * 读字符串（非字符串 / 空串返回 `undefined`）。
 *
 * @param value 原始值。
 * @returns 字符串或 `undefined`。
 */
function readString(value: unknown): string | undefined {
  return typeof value === 'string' && value !== '' ? value : undefined
}

/**
 * 读有限数值。
 *
 * @param value 原始值。
 * @returns 数值或 `undefined`。
 */
function readNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string' && value !== '' && Number.isFinite(Number(value))) {
    return Number(value)
  }
  return undefined
}

/**
 * 读图片尺寸（兼容 `dimension` / 平铺 `width` + `height`）。
 *
 * @param source 原始对象。
 * @returns 尺寸或 `undefined`。
 */
function readDimension(source: Record<string, unknown>): { width: number; height: number } | undefined {
  const nested = source.dimension
  if (nested !== null && typeof nested === 'object') {
    const inner = nested as Record<string, unknown>
    const width = readNumber(inner.width)
    const height = readNumber(inner.height)
    if (width !== undefined && height !== undefined) {
      return { width, height }
    }
  }
  const width = readNumber(source.width)
  const height = readNumber(source.height)
  if (width !== undefined && height !== undefined) {
    return { width, height }
  }
  return undefined
}

/**
 * 读列表（兼容数组 / `{ list }` / `{ items }` / `{ data }` 包装）。
 *
 * @param raw 原始数据。
 * @returns 列表。
 */
function readList(raw: unknown): unknown[] {
  if (Array.isArray(raw)) {
    return raw
  }
  if (raw !== null && typeof raw === 'object') {
    const source = raw as Record<string, unknown>
    for (const key of ['list', 'items', 'data']) {
      const value = source[key]
      if (Array.isArray(value)) {
        return value
      }
    }
  }
  return []
}
