<script setup lang="ts">
// 开发态核对页（06_07）：文件上传字段族（通用文件 / 图片 / 只读列表 / 裁剪弹窗）实例 + 12 项自检上屏（本页不进构建产物）。
import {
  BaseUploadTransport,
  FILE_PART_SIZE,
  type FileMeta,
  type UploadTransportAdapter,
} from '@bms/core'
import {
  FileListField,
  FileUploadField,
  ImageCropDialog,
  ImageUploadField,
  planImageCompress,
  registerUploadTransport,
  uploadTransportRegistry,
  useBaseFileUpload,
} from '@bms/ui-ep'
import { nextTick, ref } from 'vue'

/** 桩通路调用轨迹。 */
const calls: string[] = []

/** 秒传命中键（可切换）。 */
let dedupKey: string | null = 'dedup-1'
/** 首次失败分片。 */
const failPartOnce = new Set<number>([2])
/** 已传分片（断点续传样例）。 */
const uploadedParts: number[] = [1]
/** 慢分片释放（对象持有，避免闭包内赋值被流分析收窄）。 */
const slowPart: { release: (() => void) | undefined } = { release: undefined }

/** 桩上传通路（记录调用轨迹；分片 1MB、秒传可控、失败一次、已传分片可控）。 */
const transport: UploadTransportAdapter = {
  hash: async () => {
    calls.push('hash')
    return { sha256: 'a'.repeat(64) }
  },
  check: async () => {
    calls.push('check')
    return dedupKey === null ? null : { key: dedupKey, size: 1024, content_type: 'application/pdf' }
  },
  uploadWhole: async () => {
    calls.push('uploadWhole')
    return { key: 'whole-1', size: 1024, content_type: 'application/pdf' }
  },
  initiate: async (query) => {
    calls.push('initiate')
    return { upload_id: 'u1', key: 'k1', part_size: FILE_PART_SIZE, total_parts: Math.ceil(query.size / FILE_PART_SIZE) }
  },
  uploadPart: async (query) => {
    calls.push('uploadPart')
    if (query.partNo === 3 && slowPart.release === undefined) {
      await new Promise<void>((resolve) => {
        slowPart.release = resolve
      })
    }
    if (failPartOnce.has(query.partNo)) {
      failPartOnce.delete(query.partNo)
      throw Object.assign(new Error('分片失败'), { code: 50104 })
    }
    uploadedParts.push(query.partNo)
    return { part_no: query.partNo, etag: `e${query.partNo}`, size: query.end - query.start }
  },
  complete: async () => {
    calls.push('complete')
    return { key: 'stored-1', size: 0, content_type: 'application/octet-stream' }
  },
  abort: async () => {
    calls.push('abort')
  },
  listParts: async () => {
    calls.push('listParts')
    return [...uploadedParts]
  },
  resolveFiles: async (query) => {
    calls.push('resolveFiles')
    return query.ids.map((id) => (id === 'f9' ? { id, name: '', exists: false } : { id, name: '已回显.pdf', size: 2048 }))
  },
  presign: async (query) => {
    calls.push('presign')
    return { url: `https://signed/${query.fileId}`, expires_in: 3600 }
  },
}

/** 自定义通路（注册表登记示例）。 */
class CheckUploadTransport extends BaseUploadTransport {
  /** 实现名。 */
  override readonly pluginName: string = 'check-upload'

  /**
   * 秒传判定（固定命中）。
   *
   * @returns 既有对象引用。
   */
  override async check(): Promise<unknown> {
    return { key: 'custom-1' }
  }
}
registerUploadTransport('check-upload', () => new CheckUploadTransport())

/** 页面受控值。 */
const fileValue = ref<{ id: string; name: string }[]>([])
const imageValue = ref<string[]>([])
const listValue = ref<string[]>(['f1', 'f9'])
const cropVisible = ref(true)

/** 1x1 PNG（裁剪弹窗装配样例）。 */
const pngBlob = (): Blob => {
  const binary = atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return new Blob([bytes], { type: 'image/png' })
}

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/**
 * 等待上传任务空闲（在途任务完成 / 失败 / 取消）。
 *
 * @param api 文件上传族投影。
 */
async function waitIdle(api: { engine: { busy: { value: boolean } } }): Promise<void> {
  for (let tick = 0; tick < 200 && api.engine.busy.value; tick += 1) {
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
}

/** 构造文件元信息。 */
const metaOf = (name: string, size: number, mime: string): FileMeta => ({ name, size, mime })

/**
 * 运行自检并上屏。
 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []
  const add = (label: string, pass: boolean): void => {
    result.push({ label, pass })
  }

  // 1. 占位降级与零请求（未就绪 / 未注入通路）
  const placeholder = useBaseFileUpload({ ready: false })
  placeholder.acceptFiles([{ file: 'f', meta: metaOf('a.pdf', 10, 'application/pdf') }])
  await placeholder.resolveFiles(['f1'])
  add('占位降级且零请求', placeholder.degraded.value && placeholder.requestCount.value === 0 && placeholder.refs.value.length === 0)

  // 2. 校验（空文件 / 类型 / 大小 / 数量）
  const validate = useBaseFileUpload({ ready: true, accept: '.pdf', maxSize: 1024, limit: 1, transport })
  const empty = validate.acceptFiles([{ file: 'f', meta: metaOf('a.pdf', 0, 'application/pdf') }])
  const type = validate.acceptFiles([{ file: 'f', meta: metaOf('a.png', 10, 'image/png') }])
  const size = validate.acceptFiles([{ file: 'f', meta: metaOf('b.pdf', 2048, 'application/pdf') }])
  const limit = validate.acceptFiles([
    { file: 'f1', meta: metaOf('c.pdf', 10, 'application/pdf') },
    { file: 'f2', meta: metaOf('d.pdf', 10, 'application/pdf') },
  ])
  add(
    '校验与数量上限（空 / 类型 / 大小 / 截断）',
    empty.rejected[0]?.code === 50102 &&
      type.rejected[0]?.code === 50101 &&
      size.rejected[0]?.code === 50102 &&
      limit.rejected.some((item) => item.code === 50103) &&
      validate.limitExceeded.value,
  )

  // 3. 秒传命中（零上传直接完成）
  calls.length = 0
  const dedup = useBaseFileUpload({ ready: true, transport, multiple: false })
  dedup.acceptFiles([{ file: 'f', meta: metaOf('a.pdf', 1024, 'application/pdf') }])
  await waitIdle(dedup)
  add('秒传命中零上传', dedup.value.value === 'dedup-1' && calls.includes('check') && !calls.includes('uploadPart'))

  // 4. 整包 / 分片决策
  calls.length = 0
  dedupKey = null
  const whole = useBaseFileUpload({ ready: true, transport, multiple: false, wholeMaxSize: 2048 })
  whole.acceptFiles([{ file: 'f', meta: metaOf('a.pdf', 1024, 'application/pdf') }])
  await waitIdle(whole)
  const wholePass = calls.includes('uploadWhole')
  calls.length = 0
  uploadedParts.length = 0
  failPartOnce.clear()
  const multipart = useBaseFileUpload({ ready: true, transport, multiple: false, wholeMaxSize: 1024 })
  multipart.acceptFiles([{ file: 'f', meta: metaOf('big.bin', FILE_PART_SIZE + 10, 'application/octet-stream') }])
  await waitIdle(multipart)
  add(
    '整包 / 分片决策与分片完成',
    wholePass &&
      calls.includes('initiate') &&
      calls.filter((call) => call === 'uploadPart').length === 2 &&
      calls.includes('complete') &&
      multipart.value.value === 'stored-1',
  )

  // 5. 分片并发与失败重试
  calls.length = 0
  uploadedParts.length = 0
  failPartOnce.add(1)
  const retry = useBaseFileUpload({ ready: true, transport, multiple: false, concurrency: 2, wholeMaxSize: 1024 })
  retry.acceptFiles([{ file: 'f', meta: metaOf('big.bin', FILE_PART_SIZE + 10, 'application/octet-stream') }])
  await waitIdle(retry)
  const retryTask = retry.tasks.value[0]
  add(
    '分片失败退避重试后完成',
    retry.value.value === 'stored-1' && (retryTask?.attempts ?? 0) >= 3 && uploadedParts.includes(1) && uploadedParts.includes(2),
  )

  // 6. 断点续传（listParts 覆写仅补缺失）
  calls.length = 0
  uploadedParts.length = 0
  uploadedParts.push(1)
  const resume = useBaseFileUpload({ ready: true, transport, multiple: false, wholeMaxSize: 1024 })
  resume.acceptFiles([{ file: 'f', meta: metaOf('big.bin', FILE_PART_SIZE + 10, 'application/octet-stream') }])
  await waitIdle(resume)
  add(
    '断点续传仅补缺失分片',
    calls.includes('listParts') && calls.filter((call) => call === 'uploadPart').length === 1 && resume.value.value === 'stored-1',
  )

  // 7. 取消在途（中断 + 进度复位 + 不视为失败）
  calls.length = 0
  uploadedParts.length = 0
  slowPart.release = undefined
  dedupKey = null
  const cancel = useBaseFileUpload({ ready: true, transport, multiple: false, concurrency: 1, wholeMaxSize: 1024 })
  cancel.acceptFiles([{ file: 'f', meta: metaOf('big.bin', FILE_PART_SIZE * 2 + 10, 'application/octet-stream') }])
  for (let tick = 0; tick < 50 && !calls.includes('uploadPart'); tick += 1) {
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
  const cancelTaskId = cancel.tasks.value[0]?.id ?? ''
  cancel.cancelTask(cancelTaskId)
  const releaseSlow = slowPart.release as (() => void) | undefined
  releaseSlow?.()
  await new Promise((resolve) => setTimeout(resolve, 30))
  add(
    '取消在途不视为失败',
    cancel.tasks.value[0]?.phase === 'canceled' &&
      calls.includes('abort') &&
      cancel.engine.tasks.value.filter((task) => task.phase === 'failed').length === 0,
  )

  // 8. 多文件队列与上限
  calls.length = 0
  uploadedParts.length = 0
  dedupKey = 'dedup-1'
  const queue = useBaseFileUpload({ ready: true, transport, limit: 2 })
  const queueResult = queue.acceptFiles([
    { file: 'f1', meta: metaOf('a.pdf', 10, 'application/pdf') },
    { file: 'f2', meta: metaOf('b.pdf', 10, 'application/pdf') },
    { file: 'f3', meta: metaOf('c.pdf', 10, 'application/pdf') },
  ])
  await queue.engine.start()
  add('多文件队列与上限截断', queueResult.added.length === 2 && queueResult.rejected.some((item) => item.code === 50103))

  // 9. 只读文件列表（回显 / 失效 / 预览下载入口）
  await nextTick()
  const listPass =
    document.querySelector('[data-test="file-list-item-f1"]') !== null &&
    document.querySelector('[data-test="file-mark-invalid-f9"]') !== null &&
    document.querySelector('[data-test="file-download-f1"]') !== null
  add('只读文件列表与失效占位', listPass)

  // 10. 批量回显（一次批量、二次零请求）
  calls.length = 0
  const resolve = useBaseFileUpload({ ready: true, transport })
  resolve.setValue(['f1', 'f9'])
  await resolve.resolveFiles()
  const firstCount = calls.filter((call) => call === 'resolveFiles').length
  await resolve.resolveFiles()
  const secondCount = calls.filter((call) => call === 'resolveFiles').length
  add(
    '批量回显一次请求且已解析不重复',
    firstCount === 1 && secondCount === 1 && resolve.labelOf('f9').includes('文件已失效') && resolve.refs.value.some((ref) => ref.name === '已回显.pdf'),
  )

  // 11. 图片（尺寸校验 / 压缩决策 / 排序 / 头像形态 / 裁剪弹窗）
  const image = useBaseFileUpload({ ready: true, kind: 'image', multiple: true, imageOptions: { aspect: 1 }, transport })
  const badAspect = image.acceptFiles([{ file: 'f', meta: { ...metaOf('a.png', 10, 'image/png'), dimension: { width: 2, height: 1 } } }])
  const compressDecision = planImageCompress(metaOf('big.png', 2 * 1024 * 1024, 'image/png')).compress
  image.setValue(['i1', 'i2'])
  image.moveFile(0, 1)
  await nextTick()
  const avatar = document.querySelector('[data-avatar="true"]') !== null
  const cropStage = document.querySelector('[data-test="image-crop-stage"]') !== null
  add(
    '图片校验 / 压缩决策 / 排序 / 头像 / 裁剪弹窗',
    badAspect.rejected[0]?.code === 50102 &&
      compressDecision &&
      image.value.value?.toString() === 'i2,i1' &&
      avatar &&
      cropStage,
  )

  // 12. 数据源可替换（注册表默认键 + 自定义登记）
  add(
    '上传通路可替换（默认键 http + 自定义登记）',
    uploadTransportRegistry.get('http') !== undefined && uploadTransportRegistry.get('check-upload') !== undefined,
  )

  checks.value = result
}

void runChecks()
</script>

<template>
  <main style="padding: 16px; font-family: sans-serif">
    <h1>文件上传字段核对页（06-7）</h1>
    <section data-check-scope="file" style="margin-bottom: 16px; max-width: 560px">
      <file-upload-field v-model="fileValue" :ready="true" :transport="transport" :multiple="true" :limit="3" accept=".pdf,.png" />
    </section>
    <section data-check-scope="image" style="margin-bottom: 16px; max-width: 560px">
      <image-upload-field v-model="imageValue" :ready="true" :transport="transport" :multiple="true" :limit="9" />
    </section>
    <section data-check-scope="avatar" style="margin-bottom: 16px; max-width: 320px">
      <image-upload-field :model-value="undefined" :ready="true" :transport="transport" :multiple="false" crop-shape="circle" :crop="true" />
    </section>
    <section data-check-scope="list" style="margin-bottom: 16px; max-width: 560px">
      <file-list-field v-model="listValue" :ready="true" :transport="transport" />
    </section>
    <section style="margin-bottom: 16px">
      <image-crop-dialog v-model:visible="cropVisible" :source="pngBlob()" shape="circle" :aspect="1" />
    </section>
    <section style="margin-bottom: 16px">
      <p data-test="placeholder">文件上传未就绪（占位）</p>
      <button type="button" @click="cropVisible = !cropVisible">切换裁剪弹窗</button>
    </section>
    <section style="margin-top: 16px">
      <h2>自检结果</h2>
      <ol>
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass">
          {{ item.pass ? '通过' : '失败' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>
