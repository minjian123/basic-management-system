// kiwi_id: 965
/** 文件上传字段用例（06_07）：契约套件（核心 + 投影）+ 四件 + 工具（HTTP 通路 / 哈希 / 图片处理 / 裁剪）+ 占位契约复用。 */

import { FILE_PART_SIZE } from '@bms/core'
import {
  createUploadTransportStub,
  describeFileUploadContract,
  describePlaceholderFieldContract,
  describeUploadEngineContract,
  type FileUploadContractTarget,
  type PlaceholderFieldContractTarget,
  type UploadEngineContractTarget,
} from '@bms/core/testing'
import { flushPromises, mount } from '@vue/test-utils'
import { effectScope } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  FileListField,
  FileUploadField,
  ImageCropDialog,
  ImageUploadField,
  createHttpUploadTransport,
  createObjectUrl,
  hashFile,
  planImageCompress,
  registerUploadTransport,
  revokeObjectUrl,
  uploadTransportRegistry,
  useBaseFileUpload,
  useBaseUploadEngine,
} from '../src'

const cropperMock = vi.hoisted(() => ({ mount: vi.fn() }))
vi.mock('../src/utils/imageCrop', () => ({ mountImageCropper: cropperMock.mount }))

/** 契约目标：上传引擎投影。 */
function makeEngineTarget(): UploadEngineContractTarget {
  const scope = effectScope(true)
  const result = scope.run(() => useBaseUploadEngine()) as ReturnType<typeof useBaseUploadEngine>
  return {
    get ready() {
      return result.ready.value
    },
    get degraded() {
      return result.degraded.value
    },
    get requestCount() {
      return result.requestCount.value
    },
    get tasks() {
      return result.tasks.value
    },
    get busy() {
      return result.busy.value
    },
    get totalPercent() {
      return result.totalPercent.value
    },
    get doneCount() {
      return result.tasks.value.filter((task) => task.phase === 'done').length
    },
    get failedCount() {
      return result.tasks.value.filter((task) => task.phase === 'failed').length
    },
    get canUpload() {
      return result.canUpload.value
    },
    setReady: (value) => result.setReady(value),
    setTransport: (transport) => result.setTransport(transport),
    setConfig: (input) => result.setConfig(input),
    enqueue: (input) => result.enqueue(input),
    start: (taskId) => result.start(taskId),
    retry: (taskId) => result.retry(taskId),
    cancel: (taskId) => result.cancelTask(taskId),
    remove: (taskId) => result.remove(taskId),
    taskOf: (taskId) => result.taskOf(taskId),
    reset: () => {
      result.engine.reset()
    },
  }
}

/** 契约目标：文件上传族投影。 */
function makeFileTarget(): FileUploadContractTarget {
  const scope = effectScope(true)
  const result = scope.run(() => useBaseFileUpload()) as ReturnType<typeof useBaseFileUpload>
  return {
    get ready() {
      return result.ready.value
    },
    get degraded() {
      return result.degraded.value
    },
    get requestCount() {
      return result.requestCount.value
    },
    get refs() {
      return result.refs.value
    },
    get tasks() {
      return result.tasks.value
    },
    get empty() {
      return result.empty.value
    },
    get limitExceeded() {
      return result.limitExceeded.value
    },
    get fileError() {
      return result.fileError.value
    },
    get errorCode() {
      return result.errorCode.value
    },
    get value() {
      return result.value.value
    },
    setReady: (value) => result.setReady(value),
    setTransport: (transport) => result.setTransport(transport),
    setOptions: (options) => result.setOptions(options),
    setValue: (value) => result.setValue(value),
    acceptFiles: (inputs) => result.acceptFiles(inputs),
    remove: (id) => result.remove(id),
    clearFiles: () => result.clearFiles(),
    moveFile: (from, to) => result.moveFile(from, to),
    resolveFiles: (ids) => result.resolveFiles(ids),
    retryTask: (taskId) => result.retryTask(taskId),
    cancelTask: (taskId) => result.cancelTask(taskId),
    labelOf: (id) => result.labelOf(id),
    summary: () => result.summary(),
    previewUrlOf: (id) => result.previewUrlOf(id),
    downloadFile: (id) => result.downloadFile(id),
  }
}

/** 契约目标：占位字段投影（06_01 冻结套件复用）。 */
function makePlaceholderTarget(): PlaceholderFieldContractTarget {
  const scope = effectScope(true)
  const result = scope.run(() => useBaseFileUpload()) as ReturnType<typeof useBaseFileUpload>
  return {
    get ready() {
      return result.ready.value
    },
    get degraded() {
      return result.degraded.value
    },
    get disabled() {
      return result.disabled.value
    },
    get requestCount() {
      return result.requestCount.value
    },
    setReady: (value) => result.setReady(value),
    load: () => {
      result.acceptFiles([{ file: 'f', meta: { name: 'a.pdf', size: 10, mime: 'application/pdf' } }])
    },
  }
}

describeUploadEngineContract('上传引擎契约（投影）', makeEngineTarget)
describeFileUploadContract('文件上传族契约（投影）', makeFileTarget)
describePlaceholderFieldContract('占位字段契约（文件上传投影）', makePlaceholderTarget)

afterEach(() => {
  vi.unstubAllGlobals()
  cropperMock.mount.mockReset()
})

describe('FileUploadField 件', () => {
  it('选择文件经校验入队并上抛受控值（秒传命中）', async () => {
    const stub = createUploadTransportStub({ dedup: { key: 'f-1' } })
    const wrapper = mount(FileUploadField, {
      props: { modelValue: [], ready: true, transport: stub.transport, multiple: false },
      global: { stubs: { FilePreview: true } },
    })
    const input = wrapper.find('[data-test="file-input"]')
    const file = new File(['hello'], 'a.pdf', { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await vi.waitFor(() => {
      expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual([{ id: 'f-1', name: 'a.pdf' }])
    })
    expect(stub.calls).toContain('check')
  })

  it('类型不符时上抛 invalid 且不发请求', async () => {
    const stub = createUploadTransportStub()
    const wrapper = mount(FileUploadField, {
      props: { modelValue: [], ready: true, accept: '.pdf', transport: stub.transport },
      global: { stubs: { FilePreview: true } },
    })
    const input = wrapper.find('[data-test="file-input"]')
    const file = new File(['x'], 'a.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    expect(wrapper.emitted('invalid')?.length).toBe(1)
    expect(stub.calls).toEqual([])
  })

  it('只读态渲染列表且不渲染拖拽区', () => {
    const wrapper = mount(FileUploadField, {
      props: { modelValue: [{ id: 'f1', name: 'a.pdf' }], ready: true, readonly: true },
      global: { stubs: { FilePreview: true } },
    })
    expect(wrapper.find('[data-test="file-dropzone"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="file-f1"]').text()).toContain('a.pdf')
  })

  it('未就绪占位降级（06_01 冻结口径）', () => {
    const wrapper = mount(FileUploadField, { props: { modelValue: [] } })
    expect(wrapper.attributes('data-degraded')).toBe('true')
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('文件上传未就绪')
  })
})

describe('ImageUploadField 件', () => {
  it('选择图片入队（无尺寸能力时直传）并展示缩略位', async () => {
    const stub = createUploadTransportStub({ dedup: { key: 'img-1' } })
    const wrapper = mount(ImageUploadField, {
      props: { modelValue: [], ready: true, transport: stub.transport, multiple: false, compress: false },
      global: { stubs: { FilePreview: true } },
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['img'], 'a.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await vi.waitFor(() => {
      expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBe('img-1')
    })
  })

  it('多图排序与移除同步受控值', async () => {
    const wrapper = mount(ImageUploadField, {
      props: { modelValue: ['a', 'b'], ready: true, draggable: true },
      global: { stubs: { FilePreview: true } },
    })
    const thumbs = wrapper.findAll('[data-test^="image-thumb-"]')
    expect(thumbs).toHaveLength(2)
    await thumbs[0]?.trigger('dragstart')
    await thumbs[1]?.trigger('drop')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toEqual(['b', 'a'])
    await wrapper.find('[data-test="image-remove-a"]').trigger('click')
    expect(wrapper.emitted('remove')?.[0]).toEqual(['a'])
  })

  it('裁剪开启时选择进入裁剪弹窗并上抛 crop', async () => {
    cropperMock.mount.mockResolvedValue({ reset: vi.fn(), zoom: vi.fn(), toBlob: vi.fn(async () => new Blob(['x'], { type: 'image/png' })), destroy: vi.fn() })
    const wrapper = mount(ImageUploadField, {
      props: { modelValue: [], ready: true, crop: true, multiple: false },
      global: { stubs: { FilePreview: true } },
    })
    const input = wrapper.find('input[type="file"]')
    const file = new File(['img'], 'a.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.emitted('crop')?.[0]?.[0]).toEqual({ name: 'a.png' })
    expect(wrapper.find('[data-test="image-crop-dialog"]').exists()).toBe(true)
  })

  it('头像形态（单图 + 圆形）标记', () => {
    const wrapper = mount(ImageUploadField, {
      props: { modelValue: [], ready: true, multiple: false, cropShape: 'circle' },
      global: { stubs: { FilePreview: true } },
    })
    expect(wrapper.attributes('data-avatar')).toBe('true')
  })
})

describe('FileListField 件', () => {
  it('回显列表 / 失效标记 / 下载与预览事件', async () => {
    const stub = createUploadTransportStub()
    const wrapper = mount(FileListField, {
      props: { modelValue: ['f1', 'f9'], ready: true, transport: stub.transport },
      global: { stubs: { FilePreview: true } },
    })
    await vi.waitFor(() => {
      expect(wrapper.find('[data-test="file-list-item-f1"]').text()).toContain('已回显.pdf')
    })
    expect(wrapper.find('[data-test="file-mark-invalid-f9"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="file-download-f9"]').exists()).toBe(false)
    await wrapper.find('[data-test="file-download-f1"]').trigger('click')
    expect(wrapper.emitted('download')?.[0]?.[0]).toMatchObject({ id: 'f1' })
    await wrapper.find('[data-test="file-preview-f1"]').trigger('click')
    expect(wrapper.emitted('preview')?.[0]?.[0]).toMatchObject({ id: 'f1' })
  })
})

describe('ImageCropDialog 件', () => {
  it('装配成功：缩放 / 复位 / 确认上抛产物', async () => {
    const reset = vi.fn()
    const zoom = vi.fn()
    const destroy = vi.fn()
    const blob = new Blob(['crop'], { type: 'image/png' })
    cropperMock.mount.mockResolvedValue({ reset, zoom, toBlob: vi.fn(async () => blob), destroy })
    const wrapper = mount(ImageCropDialog, { props: { visible: true, source: new Blob(['src'], { type: 'image/png' }) } })
    await flushPromises()
    await wrapper.find('[data-test="image-crop-reset"]').trigger('click')
    await wrapper.find('[data-test="image-crop-zoom-in"]').trigger('click')
    expect(reset).toHaveBeenCalledTimes(1)
    expect(zoom).toHaveBeenCalledWith(1)
    await wrapper.find('[data-test="image-crop-confirm"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('confirm')?.[0]?.[0]).toEqual({ blob })
    expect(destroy).toHaveBeenCalled()
  })

  it('装配失败：降级提示并上抛 fail', async () => {
    cropperMock.mount.mockResolvedValue(undefined)
    const wrapper = mount(ImageCropDialog, { props: { visible: true, source: new Blob(['src']) } })
    await flushPromises()
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('裁剪器不可用')
    expect(wrapper.emitted('fail')?.length).toBe(1)
  })

  it('取消关闭且不隐式提交', async () => {
    cropperMock.mount.mockResolvedValue({ reset: vi.fn(), zoom: vi.fn(), toBlob: vi.fn(), destroy: vi.fn() })
    const wrapper = mount(ImageCropDialog, { props: { visible: true, source: new Blob(['src']) } })
    await flushPromises()
    await wrapper.find('[data-test="image-crop-cancel"]').trigger('click')
    expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
    expect(wrapper.emitted('cancel')?.length).toBe(1)
    expect(wrapper.emitted('confirm')).toBeUndefined()
  })
})

describe('上传工具', () => {
  it('HTTP 通路端点与解包；无 fetch 能力降级', async () => {
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      void init
      return {
        ok: true,
        json: async () => ({ code: 0, message: '', data: url.includes('/dedup') ? null : { upload_id: 'u1' } }),
      }
    })
    vi.stubGlobal('fetch', fetchMock)
    const transport = createHttpUploadTransport({ endpoint: '/api/v1' })
    await transport.check({ sha256: 'a'.repeat(64), size: 10 })
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v1/files/dedup')
    await transport.initiate({ name: 'a.pdf', size: 10, mime: 'application/pdf', partSize: FILE_PART_SIZE })
    const initCall = fetchMock.mock.calls[1]
    expect(String(initCall?.[0])).toContain('/api/v1/files/uploads')
    expect(String((initCall?.[1] as RequestInit).body)).toContain('"part_size"')
    await transport.listParts({ uploadId: 'u1' })
    expect(String(fetchMock.mock.calls[2]?.[0])).toContain('/files/uploads/u1/parts')
    await transport.resolveFiles({ ids: ['f1', 'f2'] })
    expect(String(fetchMock.mock.calls[3]?.[0])).toContain('ids=f1%2Cf2')
    await transport.presign({ fileId: 'f1', purpose: 'preview' })
    expect(String(fetchMock.mock.calls[4]?.[0])).toContain('/files/f1/preview-url')

    vi.stubGlobal('fetch', undefined)
    const degraded = createHttpUploadTransport()
    expect(await degraded.check({ sha256: 'a'.repeat(64), size: 10 })).toBeUndefined()
  })

  it('注册表默认键与自定义登记', () => {
    expect(uploadTransportRegistry.get('http')).toBeDefined()
    registerUploadTransport('spec-upload', () => createHttpUploadTransport())
    expect(uploadTransportRegistry.get('spec-upload')).toBeDefined()
  })

  it('哈希主线程降级（无 Worker 环境）产出标准摘要', async () => {
    const result = await hashFile(new Blob(['abc']))
    expect(result.sha256).toBe('ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    expect(result.partHashes).toHaveLength(1)
    expect(await hashFile(undefined)).toEqual({ sha256: '', partHashes: [] })
  })

  it('图片处理决策与对象 URL 降级', () => {
    expect(planImageCompress({ name: 'a.png', size: 10, mime: 'image/png' }).compress).toBe(false)
    expect(planImageCompress({ name: 'a.png', size: 2 * 1024 * 1024, mime: 'image/png' }).compress).toBe(true)
    expect(createObjectUrl(undefined)).toBeUndefined()
    revokeObjectUrl(undefined)
  })
})
