/**
 * 模块文案真源（兼作 `i18nPacks` 注册载荷）：模块内组合式与页面只从此取文案，不硬编码中文。
 */

/** 缺省语言。 */
export const SLOT_SAMPLE_DEFAULT_LOCALE = 'zh-cn'

/** 中文文案。 */
export const SLOT_SAMPLE_MESSAGES_ZH_CN: Record<string, string> = {
  'slotSample.list.title': '用户扩展示例',
  'slotSample.list.create': '新增扩展信息',
  'slotSample.list.refresh': '刷新',
  'slotSample.list.empty': '暂无扩展信息',
  'slotSample.column.label': '标签',
  'slotSample.column.remark': '备注',
  'slotSample.column.updatedAt': '更新时间',
  'slotSample.form.label': '标签',
  'slotSample.form.remark': '备注',
  'slotSample.form.save': '保存',
  'slotSample.form.cancel': '取消',
  'slotSample.hint.noEntity': '未选择用户（宿主页未提供路由参数 id），暂不发起请求。',
  'slotSample.detail.title': '扩展示例明细',
  'slotSample.detail.empty': '暂无明细（无写权限时不渲染本区域项）',
  'slotSample.error.load': '扩展信息加载失败',
  'slotSample.error.save': '保存失败',
}

/** 英文文案。 */
export const SLOT_SAMPLE_MESSAGES_EN: Record<string, string> = {
  'slotSample.list.title': 'User extensions',
  'slotSample.list.create': 'New extension',
  'slotSample.list.refresh': 'Refresh',
  'slotSample.list.empty': 'No extensions',
  'slotSample.column.label': 'Label',
  'slotSample.column.remark': 'Remark',
  'slotSample.column.updatedAt': 'Updated at',
  'slotSample.form.label': 'Label',
  'slotSample.form.remark': 'Remark',
  'slotSample.form.save': 'Save',
  'slotSample.form.cancel': 'Cancel',
  'slotSample.hint.noEntity': 'No user selected (host route param `id` missing); no request issued.',
  'slotSample.detail.title': 'Extension details',
  'slotSample.detail.empty': 'No details (item hidden without write permission)',
  'slotSample.error.load': 'Failed to load extensions',
  'slotSample.error.save': 'Failed to save',
}

/** 各语言文案包（键为语言标识小写）。 */
export const SLOT_SAMPLE_MESSAGES: Record<string, Record<string, string>> = {
  'zh-cn': SLOT_SAMPLE_MESSAGES_ZH_CN,
  en: SLOT_SAMPLE_MESSAGES_EN,
}
