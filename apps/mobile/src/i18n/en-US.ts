export default {
  app: {
    title: 'BMS Basic Management System',
    backend: 'Backend service',
    backendOffline: 'Backend service unavailable',
  },
  common: {
    enabled: 'Enabled',
    disabled: 'Disabled',
    noPermission: 'No permission',
    forbidden: 'Access denied',
    justNow: 'Just now',
    yesterday: 'Yesterday',
    yes: 'Yes',
    no: 'No',
    hour: 'h',
    minute: 'm',
    second: 's',
  },
  // 容器组件类文案
  container: {
    fullscreenTip: 'Press Esc to exit fullscreen',
    retry: 'Retry',
    loadingFailed: 'Failed to load',
    emptyText: 'No data',
  },
  // 错误码文案：error.{code}（最小集；完整错误码总表随后端接入补齐）
  error: {
    default: 'Operation failed, please try again later',
    network: 'Network error, please check your connection',
    server: 'Server error, please try again later',
    forbidden: 'No permission',
    notFound: 'Resource not found',
    conflict: 'Record has been modified',
    sessionExpired: 'Session expired, please sign in again',
    19001: 'Feature not implemented yet',
    10001: 'Invalid request parameters',
    10003: 'Operation conflict, please refresh and retry',
    10005: 'Too many requests, please try again later',
    20001: 'Session expired, please sign in again',
    30001: 'No permission',
  },
}
