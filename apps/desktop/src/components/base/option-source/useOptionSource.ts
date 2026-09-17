/**
 * 选项源片段（`option-source`）：远端 / 静态选项的统一加载、缓存与回显。
 *
 * 契约见《组件设计 · 选项源片段》：`load` / `search` / 缓存与版本比对 / `resolveLabel(s)` 回显；
 * 静态选项与远端选项共用同一口径（字典、组织、枚举、树、级联均消费本片段）。
 * **组合依赖**：`value`（值的归一与回显判定）。**占位先行**：未注入 `loader`（后端字典 / 组织未就绪）
 * 时不发请求、返回静态选项或空结果，`isPlaceholder` 标记占位态供界面降级。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'
import { useValue } from '../value/useValue'

/** 选项项（级联 / 树形经 `children` 嵌套） */
export interface OptionItem {
  value: string | number
  label: string
  disabled?: boolean
  children?: OptionItem[]
}

/** 选项源模式 */
export type OptionSourceMode = 'static' | 'remote' | 'cascade'

/** 选项源片段参数 */
export interface UseOptionSourceOptions {
  /** 静态选项（占位与本地数据源） */
  options?: MaybeRefOrGetter<OptionItem[]>
  /** 远端加载器（缺省即占位：不请求、空结果） */
  loader?: (params: { keyword?: string }) => Promise<OptionItem[]>
  mode?: MaybeRefOrGetter<OptionSourceMode>
  searchable?: MaybeRefOrGetter<boolean>
  /** 原始数据字段映射（远端返回未归一为 `value` / `label` 时使用） */
  valueKey?: string
  labelKey?: string
  cascade?: MaybeRefOrGetter<boolean>
  /** 是否缓存（默认 true） */
  cache?: MaybeRefOrGetter<boolean>
  /** 数据版本（后端版本比对；变化即失效重取） */
  version?: MaybeRefOrGetter<string | number>
  placeholder?: MaybeRefOrGetter<string>
}

/** 选项源片段返回值 */
export interface UseOptionSourceReturn {
  readonly options: OptionItem[]
  readonly loading: boolean
  /** 占位态：远端能力未接入（无 `loader`） */
  readonly isPlaceholder: boolean
  readonly placeholder: string
  readonly mode: OptionSourceMode
  load: (params?: { keyword?: string }) => Promise<OptionItem[]>
  search: (keyword: string) => Promise<OptionItem[]>
  resolveLabel: (value: unknown) => string
  resolveLabels: (values: unknown[]) => string[]
  /** 失效缓存（版本变化 / 手工刷新） */
  invalidate: () => void
}

/** 原始选项归一（支持 `valueKey` / `labelKey` 映射） */
export function normalizeOptions(raw: unknown[], valueKey = 'value', labelKey = 'label'): OptionItem[] {
  return raw.map((item) => {
    const record = item as Record<string, unknown>
    const children = Array.isArray(record.children) ? normalizeOptions(record.children, valueKey, labelKey) : undefined
    return {
      value: (record[valueKey] ?? record.value ?? '') as string | number,
      label: String(record[labelKey] ?? record.label ?? ''),
      ...(record.disabled === true ? { disabled: true } : {}),
      ...(children ? { children } : {}),
    }
  })
}

/** 扁平化（含子级） */
function flattenOptions(items: OptionItem[]): OptionItem[] {
  return items.flatMap((item) => [item, ...(item.children ? flattenOptions(item.children) : [])])
}

/**
 * 获取选项源能力。
 *
 * 用法：`const source = useOptionSource({ loader: fetchDict, version })`；
 * 后端未就绪时省略 `loader` 即可得到占位行为（界面按 `isPlaceholder` 降级）。
 */
export function useOptionSource(options: UseOptionSourceOptions = {}): UseOptionSourceReturn {
  const capability = declareFragment('option-source')
  const valueFragment = useValue<unknown>()

  const remoteOptions = ref<OptionItem[]>([])
  const loading = ref(false)
  const loadedVersion = ref<string | number | undefined>(undefined)
  const isPlaceholder = computed(() => options.loader === undefined)
  const mode = computed<OptionSourceMode>(() => toValue(options.mode) ?? (options.loader ? 'remote' : 'static'))

  const staticOptions = computed(() => toValue(options.options) ?? [])
  const optionItems = computed(() => (staticOptions.value.length > 0 ? staticOptions.value : remoteOptions.value))

  const load = async (params: { keyword?: string } = {}): Promise<OptionItem[]> => {
    if (!options.loader) {
      // 占位：不请求、不报错，仅回静态选项
      capability.log('debug', 'option-source 占位：远端选项未接入，返回静态选项')
      return staticOptions.value
    }
    const useCache = toValue(options.cache) ?? true
    const version = toValue(options.version)
    if (useCache && params.keyword === undefined && loadedVersion.value === version && remoteOptions.value.length > 0) {
      return remoteOptions.value
    }
    loading.value = true
    try {
      const raw = await options.loader(params)
      remoteOptions.value = normalizeOptions(raw, options.valueKey, options.labelKey)
      loadedVersion.value = version
      return remoteOptions.value
    } finally {
      loading.value = false
    }
  }

  const search = async (keyword: string): Promise<OptionItem[]> => {
    if (!toValue(options.searchable)) {
      return optionItems.value
    }
    if (options.loader) {
      loading.value = true
      try {
        const raw = await options.loader({ keyword })
        return normalizeOptions(raw, options.valueKey, options.labelKey)
      } finally {
        loading.value = false
      }
    }
    const lower = keyword.trim().toLowerCase()
    return flattenOptions(optionItems.value).filter((item) => item.label.toLowerCase().includes(lower))
  }

  const resolveLabel = (input: unknown): string => {
    const normalized = valueFragment.normalize(input)
    if (normalized === undefined) {
      return ''
    }
    const hit = flattenOptions(optionItems.value).find((item) => item.value === normalized)
    return hit ? hit.label : String(normalized)
  }

  return {
    get options() {
      return optionItems.value
    },
    get loading() {
      return loading.value
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get placeholder() {
      return String(toValue(options.placeholder) ?? '')
    },
    get mode() {
      return mode.value
    },
    load,
    search,
    resolveLabel,
    resolveLabels: (values) => values.map((value) => resolveLabel(value)),
    invalidate: () => {
      loadedVersion.value = undefined
      remoteOptions.value = []
    },
  }
}
