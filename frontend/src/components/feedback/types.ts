/**
 * 反馈组件公共类型（错误页 / 空态操作按钮）。
 */

/** 操作按钮（错误页 / 空态共用；`key` 错误页缺省动作必填：`home` / `retry` / `contact`） */
export interface FeedbackAction {
  /** 动作键（错误页缺省为 home / retry / contact；自定义键需提供 handler） */
  key?: string
  /** 按钮文案（缺省按场景取 i18n） */
  text?: string
  /** 按钮类型（缺省 default；首个缺省动作 primary） */
  type?: 'primary' | 'default'
  /** 自定义处理（提供则不执行缺省行为 / 不 emit） */
  handler?: () => void
}
