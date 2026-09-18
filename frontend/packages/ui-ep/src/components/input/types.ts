/** 基础控件选项类型（静态选项：无数据源语义，字典 / 枚举归域 06）。 */

/** 选项。 */
export interface InputOption<T = string | number> {
  /** 文案。 */
  label: string
  /** 值。 */
  value: T
  /** 是否禁用。 */
  disabled?: boolean
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
