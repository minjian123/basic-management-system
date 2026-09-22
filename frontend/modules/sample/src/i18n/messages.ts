/**
 * 样例模块文案真源（模块注册声明与模块内视图共用同一份，避免两处漂移）。
 *
 * 说明：这里同时是 `i18nPacks` 注册载荷的来源与模块内视图的 `t()` 来源——注册进宿主 `moduleI18n`
 * 供宿主消费，模块内视图经 `useSampleI18n()` 读取同源文案（模块不直连宿主 i18n 实例）。
 */

/** 中文（默认）文案。 */
export const SAMPLE_MESSAGES_ZH_CN: Readonly<Record<string, string>> = {
  'sample.title': '示例数据管理',
  'sample.module': '示例模块',
  'sample.card.title': '示例数据概览',
  'sample.card.unit': '条',
  'sample.header.readonly': '只读',
  'sample.header.ready': '可编辑',
  'sample.header.permissions': '接入 {count} 项权限',

  'sample.list.title': '示例数据管理',
  'sample.list.description': '查询筛选 + 列表 + 详情 / 表单（占位数据通路，真实接口随后续窗口联调）',
  'sample.list.create': '新建',
  'sample.list.detail': '详情',
  'sample.list.edit': '编辑',
  'sample.list.remove': '删除',
  'sample.list.removeConfirm': '确认删除该记录？',
  'sample.list.refresh': '刷新',
  'sample.list.keyword': '关键词',
  'sample.list.keywordPlaceholder': '编码 / 名称',
  'sample.list.category': '分类',
  'sample.list.status': '状态',
  'sample.list.total': '共 {total} 条',
  'sample.list.empty': '暂无数据',

  'sample.detail.title': '记录详情',
  'sample.detail.back': '返回列表',
  'sample.detail.edit': '编辑',
  'sample.detail.notFound': '记录不存在或已删除',
  'sample.detail.remark': '备注',
  'sample.detail.updatedAt': '更新时间',

  'sample.form.createTitle': '新建记录',
  'sample.form.editTitle': '编辑记录',
  'sample.form.name': '名称',
  'sample.form.category': '分类',
  'sample.form.priority': '优先级',
  'sample.form.amount': '金额',
  'sample.form.owner': '负责人',
  'sample.form.status': '状态',
  'sample.form.remark': '备注',
  'sample.form.submit': '保存',
  'sample.form.cancel': '取消',
  'sample.form.required': '该项为必填',
  'sample.form.amountRange': '金额须在 0 ~ 1000000 之间',
  'sample.form.saved': '已保存',
  'sample.form.saveFailed': '保存失败',

  'sample.column.code': '编码',
  'sample.column.name': '名称',
  'sample.column.category': '分类',
  'sample.column.priority': '优先级',
  'sample.column.amount': '金额',
  'sample.column.status': '状态',
  'sample.column.owner': '负责人',
  'sample.column.createdAt': '创建时间',

  'sample.category.hardware': '硬件',
  'sample.category.software': '软件',
  'sample.category.service': '服务',
  'sample.category.other': '其他',
  'sample.priority.low': '低',
  'sample.priority.normal': '普通',
  'sample.priority.high': '高',
  'sample.priority.urgent': '紧急',
  'sample.status.draft': '草稿',
  'sample.status.pending': '待处理',
  'sample.status.active': '生效',
  'sample.status.closed': '已关闭',
}

/** 英文文案。 */
export const SAMPLE_MESSAGES_EN: Readonly<Record<string, string>> = {
  'sample.title': 'Sample data',
  'sample.module': 'Sample module',
  'sample.card.title': 'Sample overview',
  'sample.card.unit': 'items',
  'sample.header.readonly': 'Read-only',
  'sample.header.ready': 'Editable',
  'sample.header.permissions': '{count} permissions',

  'sample.list.title': 'Sample data',
  'sample.list.description': 'Query filter + list + detail / form (placeholder data source)',
  'sample.list.create': 'Create',
  'sample.list.detail': 'Detail',
  'sample.list.edit': 'Edit',
  'sample.list.remove': 'Delete',
  'sample.list.removeConfirm': 'Delete this record?',
  'sample.list.refresh': 'Refresh',
  'sample.list.keyword': 'Keyword',
  'sample.list.keywordPlaceholder': 'Code / name',
  'sample.list.category': 'Category',
  'sample.list.status': 'Status',
  'sample.list.total': '{total} items',
  'sample.list.empty': 'No data',

  'sample.detail.title': 'Record detail',
  'sample.detail.back': 'Back',
  'sample.detail.edit': 'Edit',
  'sample.detail.notFound': 'Record not found',
  'sample.detail.remark': 'Remark',
  'sample.detail.updatedAt': 'Updated at',

  'sample.form.createTitle': 'Create record',
  'sample.form.editTitle': 'Edit record',
  'sample.form.name': 'Name',
  'sample.form.category': 'Category',
  'sample.form.priority': 'Priority',
  'sample.form.amount': 'Amount',
  'sample.form.owner': 'Owner',
  'sample.form.status': 'Status',
  'sample.form.remark': 'Remark',
  'sample.form.submit': 'Save',
  'sample.form.cancel': 'Cancel',
  'sample.form.required': 'Required',
  'sample.form.amountRange': 'Amount must be within 0 ~ 1000000',
  'sample.form.saved': 'Saved',
  'sample.form.saveFailed': 'Save failed',

  'sample.column.code': 'Code',
  'sample.column.name': 'Name',
  'sample.column.category': 'Category',
  'sample.column.priority': 'Priority',
  'sample.column.amount': 'Amount',
  'sample.column.status': 'Status',
  'sample.column.owner': 'Owner',
  'sample.column.createdAt': 'Created at',

  'sample.category.hardware': 'Hardware',
  'sample.category.software': 'Software',
  'sample.category.service': 'Service',
  'sample.category.other': 'Other',
  'sample.priority.low': 'Low',
  'sample.priority.normal': 'Normal',
  'sample.priority.high': 'High',
  'sample.priority.urgent': 'Urgent',
  'sample.status.draft': 'Draft',
  'sample.status.pending': 'Pending',
  'sample.status.active': 'Active',
  'sample.status.closed': 'Closed',
}

/** 缺省语言（模块内视图使用；语言标识小写）。 */
export const SAMPLE_DEFAULT_LOCALE = 'zh-cn'

/** 文案源（语言标识 → 文案映射）。 */
export const SAMPLE_MESSAGES: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  'zh-cn': SAMPLE_MESSAGES_ZH_CN,
  en: SAMPLE_MESSAGES_EN,
}
