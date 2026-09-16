/**
 * 字段壳片段（`field-shell`）：字段的 label / 必填 / 帮助 / 错误 / 栅格跨度 / 只读回显。
 *
 * 契约见《组件设计 · 字段壳片段》：壳只负责「字段周围的结构与状态标注」；
 * 实际控件由渲染器或具体组件提供。权限协作口径：`visible=false` 时**整壳不渲染**，
 * 由渲染器调用字段权限片段判定后跳过（本片段提供 `visible` 供其消费）。
 */

import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 字段壳片段参数 */
export interface UseFieldShellOptions {
  label?: MaybeRefOrGetter<string>
  /** 字段标识（渲染为 `data-field`，供错误定位与埋点） */
  fieldKey?: MaybeRefOrGetter<string>
  required?: MaybeRefOrGetter<boolean>
  /** 帮助文案（字段下方说明） */
  help?: MaybeRefOrGetter<string>
  /** 附加信息（如单位 / 提示图标） */
  extra?: MaybeRefOrGetter<string>
  /** 校验错误（由校验方写入） */
  error?: MaybeRefOrGetter<string>
  /** 栅格跨度 */
  span?: MaybeRefOrGetter<number>
  labelWidth?: MaybeRefOrGetter<string | number>
  labelPosition?: MaybeRefOrGetter<'top' | 'left' | 'right'>
  /** label 后缀冒号 */
  colon?: MaybeRefOrGetter<boolean>
  /** 只读回显模式（壳降级为纯文本壳） */
  readonlyMode?: MaybeRefOrGetter<boolean>
  /** 是否显示 label */
  showLabel?: MaybeRefOrGetter<boolean>
  /** 显隐（由字段权限判定后传入；`false` 时整壳不渲染） */
  visible?: MaybeRefOrGetter<boolean>
}

/** 字段壳片段返回值 */
export interface UseFieldShellReturn {
  /** 显示用 label（含冒号，按 `colon` 决定） */
  readonly labelText: string
  readonly labelWidth: string
  readonly labelPosition: string
  readonly isRequired: boolean
  /** 是否显示必填星号（必填且非只读） */
  readonly requiredMark: boolean
  readonly helpText: string
  readonly extraText: string
  readonly errorText: string
  readonly hasError: boolean
  readonly isReadonly: boolean
  readonly showLabel: boolean
  readonly span: number
  readonly visible: boolean
  /** 壳属性（根元素透传：`data-field` / `data-span` / `aria-required` / `aria-invalid` / `data-readonly`） */
  readonly shellAttrs: Record<string, string | boolean | number>
}

/**
 * 获取字段壳能力。
 *
 * 用法：`const shell = useFieldShell({ label, required, error })`，把 `shellAttrs` 透传到字段根元素。
 */
export function useFieldShell(options: UseFieldShellOptions = {}): UseFieldShellReturn {
  declareFragment('field-shell')

  const visible = computed(() => options.visible === undefined || Boolean(toValue(options.visible)))
  const isReadonly = computed(() => Boolean(toValue(options.readonlyMode)))
  const isRequired = computed(() => Boolean(toValue(options.required)))
  const showLabel = computed(() => (options.showLabel === undefined ? true : Boolean(toValue(options.showLabel))))
  const errorText = computed(() => String(toValue(options.error) ?? ''))
  const labelPosition = computed(() => String(toValue(options.labelPosition) ?? 'top'))
  const span = computed(() => Math.max(1, Number(toValue(options.span) ?? 1)))

  const labelText = computed(() => {
    const raw = String(toValue(options.label) ?? '')
    if (!raw) {
      return ''
    }
    return toValue(options.colon) === true ? `${raw}：` : raw
  })

  const labelWidth = computed(() => {
    const width = toValue(options.labelWidth)
    return typeof width === 'number' ? `${width}px` : String(width ?? '')
  })

  const shellAttrs = computed<Record<string, string | boolean | number>>(() => ({
    'data-field': String(toValue(options.fieldKey) ?? ''),
    'data-span': span.value,
    'data-readonly': isReadonly.value ? 'true' : 'false',
    'aria-required': isRequired.value,
    'aria-invalid': errorText.value.length > 0,
  }))

  return {
    get labelText() {
      return labelText.value
    },
    get labelWidth() {
      return labelWidth.value
    },
    get labelPosition() {
      return labelPosition.value
    },
    get isRequired() {
      return isRequired.value
    },
    get requiredMark() {
      return isRequired.value && !isReadonly.value
    },
    get helpText() {
      return String(toValue(options.help) ?? '')
    },
    get extraText() {
      return String(toValue(options.extra) ?? '')
    },
    get errorText() {
      return errorText.value
    },
    get hasError() {
      return errorText.value.length > 0
    },
    get isReadonly() {
      return isReadonly.value
    },
    get showLabel() {
      return showLabel.value
    },
    get span() {
      return span.value
    },
    get visible() {
      return visible.value
    },
    get shellAttrs() {
      return shellAttrs.value
    },
  }
}
