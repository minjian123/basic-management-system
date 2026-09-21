/**
 * 字段分发映射：控件语义键 → 具体组件（统一提供者注册表覆盖）。
 *
 * 语义键由核心 `domain/form-render` 产出（框架无关）；本工具是**映射表的唯一出口**
 * （核心与投影不触具体组件）。自定义 / 业务字段类型经 `FieldRendererRegistry` 优先命中，未登记回落内建映射。
 *
 * 说明：控件本体均已进 `ui-ep` 根出口（对外契约冻结，不可移除），故此处**静态引用**——
 * 动态导入对已静态导出的模块不会分包（vite 报 `INEFFECTIVE_DYNAMIC_IMPORT`），
 * 真实首屏收益为 0 且徒增一次异步边界；渲染主体 `FormRendererBody` 自身的分包保持不变。
 */

import type { FieldRendererRegistry, FormWidget } from '@bms/core'
import { isKnownFieldType, resolveFieldWidget } from '@bms/core'
import type { Component } from 'vue'

import AmountField from '../components/field/AmountField.vue'
import CaptchaField from '../components/field/CaptchaField.vue'
import CascadeField from '../components/field/CascadeField.vue'
import DateTimeField from '../components/field/DateTimeField.vue'
import DictSelectField from '../components/field/DictSelectField.vue'
import EnumField from '../components/field/EnumField.vue'
import FileUploadField from '../components/field/FileUploadField.vue'
import ImageUploadField from '../components/field/ImageUploadField.vue'
import NumberField from '../components/field/NumberField.vue'
import OrgSelectField from '../components/field/OrgSelectField.vue'
import RichTextField from '../components/field/RichTextField.vue'
import SwitchField from '../components/field/SwitchField.vue'
import TagInputField from '../components/field/TagInputField.vue'
import TransferField from '../components/field/TransferField.vue'
import TreeSelectField from '../components/field/TreeSelectField.vue'
import CheckboxInput from '../components/input/CheckboxInput.vue'
import NumberInput from '../components/input/NumberInput.vue'
import RadioInput from '../components/input/RadioInput.vue'
import SelectInput from '../components/input/SelectInput.vue'
import TextareaInput from '../components/input/TextareaInput.vue'
import TextInput from '../components/input/TextInput.vue'

/** 内建控件映射（语义键 → 组件）；`plain` 无组件（由件层渲染纯文本）。 */
const BUILTIN_WIDGETS: Readonly<Record<string, Component>> = {
  text: TextInput,
  textarea: TextareaInput,
  number: NumberInput,
  datetime: DateTimeField,
  select: SelectInput,
  'multi-select': SelectInput,
  radio: RadioInput,
  checkbox: CheckboxInput,
  switch: SwitchField,
  file: FileUploadField,
  image: FileUploadField,
  'file-upload': FileUploadField,
  'image-upload': ImageUploadField,
  richtext: RichTextField,
  'tree-select': TreeSelectField,
  'org-select': OrgSelectField,
  'dict-select': DictSelectField,
  'dict-multi': DictSelectField,
  transfer: TransferField,
  cascader: CascadeField,
  tags: TagInputField,
  captcha: CaptchaField,
}

/** 字段类型专用件（同语义键下按类型细分：金额 / 枚举；字典类型经内建映射分发 `DictSelectField`）。 */
const TYPE_OVERRIDES: Readonly<Record<string, Component>> = {
  amount: AmountField,
  percent: AmountField,
  number: NumberField,
  radio: EnumField,
  multi_select: EnumField,
}

/**
 * 取语义键对应的内建组件（未映射返回 `undefined`）。
 *
 * @param widget 控件语义键。
 */
export function getFieldWidget(widget: FormWidget): Component | undefined {
  return BUILTIN_WIDGETS[widget]
}

/**
 * 解析字段渲染组件（注册表自定义类型优先 → 内建语义键 → 未命中返回 `undefined`）。
 *
 * @param input 输入（语义键 / 字段类型 / 注册表）。
 */
export function resolveFieldComponent(input: {
  widget: FormWidget
  fieldType: string
  registry?: FieldRendererRegistry | undefined
}): Component | undefined {
  const custom = input.registry?.resolveByType(input.fieldType)?.component
  if (custom !== undefined && custom !== null) {
    return custom as Component
  }
  if (input.widget === 'plain') {
    return undefined
  }
  // 同语义键下按字段类型细分专用件（金额 / 枚举 / 字典）。
  if (isKnownFieldType(input.fieldType)) {
    const overridden = TYPE_OVERRIDES[input.fieldType]
    if (overridden !== undefined) {
      return overridden
    }
  }
  return getFieldWidget(input.widget)
}

/**
 * 由字段类型直接解析组件（语义键 + 内建映射，注册表可选）。
 *
 * @param fieldType 字段类型。
 * @param registry 注册表。
 */
export function resolveFieldComponentByType(
  fieldType: string,
  registry?: FieldRendererRegistry,
): Component | undefined {
  return resolveFieldComponent({ widget: resolveFieldWidget(fieldType), fieldType, registry })
}

/** 多选语义键集合（件层据此传 `multiple`；表单渲染器复用为唯一来源）。 */
export const MULTIPLE_WIDGETS: readonly FormWidget[] = [
  'multi-select',
  'checkbox',
  'transfer',
  'tags',
  'org-select',
  'dict-multi',
  'file-upload',
  'image-upload',
]
