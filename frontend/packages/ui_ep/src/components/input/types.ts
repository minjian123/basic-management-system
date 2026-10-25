/** 基础控件选项类型（静态选项：无数据源语义，字典 / 枚举归域 06）。 */

/** 选项。 */
export interface InputOption<T = string | number> {
  /** 文案。 */
  label: string
  /** 值。 */
  value: T
  /** 是否禁用。 */
  disabled?: boolean
  /** 语义色（只读标签用，缺省回退默认色；枚举选项集解析消费）。 */
  color?: string
  /** 展示顺序（枚举选项集解析按此升序，缺省 0）。 */
  sort?: number
}

/** 选项分组。 */
export interface InputOptionGroup<T = string | number> {
  /** 分组文案。 */
  label: string
  /** 分组内选项。 */
  options: InputOption<T>[]
}

/** 选项或分组。 */
export type InputOptions<T = string | number> = (InputOption<T> | InputOptionGroup<T>)[]
