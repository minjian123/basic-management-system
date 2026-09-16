export default {
  app: {
    title: 'BMS 基础管理系统',
    backend: '后端服务',
    backendOffline: '后端服务未连通',
  },
  common: {
    enabled: '启用',
    disabled: '停用',
  },
  // 错误码文案：error.{code}（最小集；完整错误码总表随后端接入补齐）
  error: {
    default: '操作失败，请稍后重试',
    network: '网络异常，请检查网络',
    server: '服务异常，请稍后重试',
    forbidden: '没有操作权限',
    notFound: '资源不存在',
    conflict: '记录已被修改',
    sessionExpired: '登录已过期，请重新登录',
    19001: '该功能尚未实现',
    10001: '请求参数有误',
    10003: '操作冲突，请刷新后重试',
    10005: '操作过于频繁，请稍后再试',
    20001: '登录已过期，请重新登录',
    30001: '没有操作权限',
  },
}
