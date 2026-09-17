/**
 * 选项契约（框架无关核心）：静态选项、字典选项与枚举选项的统一定义。
 *
 * 下拉框 / 单选 / 复选 / 字典字段 / 枚举字段共用同一模型，便于字段类继承与共享；
 * 取值类型放宽到 `string | number`（覆盖状态码等数字值场景）。
 */

/** 选项值（字符串 / 数字） */
export type OptionValue = string | number

export interface OptionItem {
  /** 选项值 */
  value: OptionValue
  /** 选项文本（由使用方按 locale 处理后传入） */
  label: string
  /** 禁用（仍展示，不可选） */
  disabled?: boolean
  /** 分组名（同组连续排列；缺省不分组） */
  group?: string
}

/** 选项分组视图（渲染用；顺序保持 `options` 中出现顺序） */
export interface OptionGroup {
  group: string
  items: readonly OptionItem[]
}
