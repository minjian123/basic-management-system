/**
 * 表单元数据片段（`form-meta`）：菜单下发表单元数据的加载、缓存与版本比对。
 *
 * 契约见《组件设计 · 表单元数据片段》：`load` / `refresh` / `get` / `invalidate` + 缓存与版本比对
 * （表单渲染器与表单设计器共用；字段权限属性由字段权限片段消费）。
 * **占位先行**：未注入 `loader`（后端表单元数据未接入）时 `load` 返回 `undefined` 并标记占位，
 * 消费方可回落本地默认元数据（`fallbackToDefault`）。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 字段元数据（渲染器消费的最小形状） */
export interface FieldMeta {
  key: string
  label: string
  /** 控件类型（字典 / 输入 / 选择…；渲染器按注册表解析） */
  type: string
  required?: boolean
  visible?: boolean
  editable?: boolean
  rules?: Array<Record<string, unknown>>
  [key: string]: unknown
}

/** 表单元数据 */
export interface FormMeta {
  menuKey: string
  /** 元数据版本（后端下发；变化即失效缓存） */
  version: string | number
  fields: FieldMeta[]
  [key: string]: unknown
}

/** 表单元数据片段参数 */
export interface UseFormMetaOptions {
  /** 菜单标识（表单元数据按菜单下发） */
  menuKey?: MaybeRefOrGetter<string | undefined>
  /** 是否缓存（默认 true） */
  cache?: MaybeRefOrGetter<boolean>
  /** 加载失败 / 占位时是否回落到默认元数据 */
  fallbackToDefault?: boolean
  /** 默认元数据（本地兜底） */
  defaultMeta?: MaybeRefOrGetter<FormMeta | undefined>
  /** 加载器（缺省即占位：不请求） */
  loader?: (menuKey: string) => Promise<FormMeta>
}

/** 表单元数据片段返回值 */
export interface UseFormMetaReturn {
  readonly meta: FormMeta | undefined
  readonly version: string | number | undefined
  readonly loading: boolean
  readonly error: string
  readonly isPlaceholder: boolean
  load: (menuKey?: string) => Promise<FormMeta | undefined>
  refresh: (payload?: unknown) => Promise<FormMeta | undefined>
  get: (menuKey?: string) => FormMeta | undefined
  invalidate: (menuKey?: string) => void
}

/**
 * 获取表单元数据能力。
 *
 * 用法：`const formMeta = useFormMeta({ menuKey, loader, fallbackToDefault: true, defaultMeta })`；
 * 后端未就绪时省略 `loader` 即得占位行为（返回默认元数据）。
 */
export function useFormMeta(options: UseFormMetaOptions = {}): UseFormMetaReturn {
  const capability = declareFragment('form-meta')

  const cache = ref<Record<string, FormMeta>>({})
  const loading = ref(false)
  const error = ref('')
  const isPlaceholder = computed(() => options.loader === undefined)

  const currentKey = computed(() => toValue(options.menuKey))
  const fallbackMeta = computed(() => toValue(options.defaultMeta))

  const get = (menuKey?: string): FormMeta | undefined => {
    const key = menuKey ?? currentKey.value
    if (key === undefined) {
      return fallbackMeta.value
    }
    return cache.value[key] ?? (options.fallbackToDefault ? fallbackMeta.value : undefined)
  }

  const load = async (menuKey?: string): Promise<FormMeta | undefined> => {
    const key = menuKey ?? currentKey.value
    if (key === undefined) {
      return fallbackMeta.value
    }
    const useCache = toValue(options.cache) ?? true
    if (useCache && cache.value[key] !== undefined) {
      return cache.value[key]
    }
    if (!options.loader) {
      capability.log('debug', 'form-meta 占位：表单元数据加载器未接入，回落默认元数据')
      return options.fallbackToDefault ? fallbackMeta.value : undefined
    }
    loading.value = true
    error.value = ''
    try {
      const meta = await options.loader(key)
      // 版本比对：同 key 且版本未变时保留旧引用（避免渲染器全量重建）
      const existing = cache.value[key]
      const next = existing && existing.version === meta.version ? existing : meta
      cache.value = { ...cache.value, [key]: next }
      return next
    } catch (caught) {
      error.value = '表单元数据加载失败'
      capability.reportError(caught, { scope: 'form-meta.load', menuKey: key })
      return options.fallbackToDefault ? fallbackMeta.value : undefined
    } finally {
      loading.value = false
    }
  }

  return {
    get meta() {
      return get()
    },
    get version() {
      return get()?.version
    },
    get loading() {
      return loading.value
    },
    get error() {
      return error.value
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    load,
    refresh: async (payload?: unknown) => {
      void payload
      const key = currentKey.value
      if (key !== undefined) {
        const next = { ...cache.value }
        delete next[key]
        cache.value = next
      }
      return load()
    },
    get,
    invalidate: (menuKey) => {
      if (menuKey === undefined) {
        cache.value = {}
        return
      }
      const next = { ...cache.value }
      delete next[menuKey]
      cache.value = next
    },
  }
}
