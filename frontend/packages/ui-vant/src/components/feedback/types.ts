/** 反馈件共享类型（与 `ui-ep` 同形状，契约一致）。 */

/** 反馈 / 错误动作（引导按钮或错误页操作） */
export interface FeedbackAction {
  /** 动作键（`home` / `retry` / `contact` / 自定义） */
  key?: string
  /** 文案（缺省按 key 取 i18n） */
  text?: string
  /** 主次语义（缺省第一个 primary） */
  type?: 'primary' | 'default'
  /** 自定义处理（提供则不执行默认行为） */
  handler?: () => void
}
