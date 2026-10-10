/**
 * 扫码登录领域纯函数与数据模型：四态状态机相位 / 相位文案 / 轮询指数退避 / 可扫码身份源过滤 / 契约归一。
 *
 * 与后端 `GET /auth/sso/{idp_key}/authorize-url` 契约同源（域二 `02_04`）：授权 URL + `state` + `expires_in`。
 * 平台（企微 / 钉钉）**不对外暴露「已扫待确认」态**，`scanned` 仅由可注入状态源回报（平台限制，见任务详细设计）。
 * 纯数据、零依赖：不触 DOM、不请求、不依赖渲染框架与第三方库，供核心能力基类 / 组合式 / 移动端同契约复用。
 */
/** 扫码状态（四态：待扫 / 已扫待确认 / 已确认 / 过期）。 */
export const SSO_QR_STATUSES = ['pending', 'scanned', 'confirmed', 'expired'];
/** 扫码相位（四态 + 失败）。 */
export const SSO_QR_PHASES = [...SSO_QR_STATUSES, 'failed'];
/** 可扫码身份源类型（企业微信 / 钉钉）。 */
export const SSO_QR_IDP_TYPES = ['wecom', 'dingtalk'];
/** 轮询间隔基数（毫秒）。 */
export const SSO_QR_POLL_BASE = 2000;
/** 轮询退避上限（毫秒）。 */
export const SSO_QR_POLL_MAX = 30_000;
/** 轮询连续失败阈值（达阈值转 `failed`）。 */
export const SSO_QR_MAX_FAILURES = 5;
/** 标题文案。 */
export const SSO_QR_TITLE_TEXT = '扫码登录';
/** 待扫文案。 */
export const SSO_QR_PENDING_TEXT = '请使用企业微信 / 钉钉扫码登录';
/** 已扫待确认文案。 */
export const SSO_QR_SCANNED_TEXT = '已扫码，请在移动端确认';
/** 已确认文案。 */
export const SSO_QR_CONFIRMED_TEXT = '已确认，正在进入系统…';
/** 已过期文案。 */
export const SSO_QR_EXPIRED_TEXT = '二维码已过期';
/** 刷新文案。 */
export const SSO_QR_REFRESH_TEXT = '刷新';
/** 失败文案。 */
export const SSO_QR_FAILED_TEXT = '扫码登录暂不可用，请稍后重试';
/** 空态文案（无可扫码入口）。 */
export const SSO_QR_EMPTY_TEXT = '当前租户未配置可扫码登录方式';
/** 返回账号登录文案。 */
export const SSO_QR_BACK_TEXT = '返回账号登录';
/** 切换入口文案。 */
export const SSO_QR_SWITCH_TEXT = '切换登录方式';
/** 取授权 URL 失败原因。 */
export const SSO_QR_INIT_ERROR_REASON = 'init-failed';
/** 轮询连续失败原因。 */
export const SSO_QR_POLL_ERROR_REASON = 'poll-failed';
/**
 * 是否可扫码身份源类型。
 *
 * @param type 身份源类型。
 */
export function isScannableIdpType(type) {
    return SSO_QR_IDP_TYPES.includes(type);
}
/**
 * 过滤可扫码入口并按 `sort` 升序（缺省按原序；不修改入参）。
 *
 * @param providers 原始入口清单。
 */
export function selectScannableProviders(providers) {
    return providers
        .filter((provider) => isScannableIdpType(provider.type))
        .slice()
        .sort((left, right) => (left.sort ?? 0) - (right.sort ?? 0));
}
/**
 * 指数退避轮询间隔：`base * 2^(attempt - 1)`，封顶 `max`。
 *
 * @param attempt 连续失败次数（自 1 起；成功回报后复位）。
 * @param options 退避选项。
 */
export function nextSsoQrPollDelay(attempt, options = {}) {
    const base = options.base ?? SSO_QR_POLL_BASE;
    const max = options.max ?? SSO_QR_POLL_MAX;
    const exponent = Math.max(0, Math.floor(attempt) - 1);
    return Math.min(base * 2 ** exponent, max);
}
/**
 * 是否终态（终态停止轮询）。
 *
 * @param phase 扫码相位。
 */
export function isSsoQrTerminal(phase) {
    return phase === 'confirmed' || phase === 'expired' || phase === 'failed';
}
/**
 * 相位文案映射。
 *
 * @param phase 扫码相位。
 */
export function resolveSsoQrStatusText(phase) {
    switch (phase) {
        case 'pending':
            return SSO_QR_PENDING_TEXT;
        case 'scanned':
            return SSO_QR_SCANNED_TEXT;
        case 'confirmed':
            return SSO_QR_CONFIRMED_TEXT;
        case 'expired':
            return SSO_QR_EXPIRED_TEXT;
        case 'failed':
            return SSO_QR_FAILED_TEXT;
    }
}
/**
 * 归一授权信息（后端字段 → 领域结构；非法入参回落缺省，不抛错）。
 *
 * @param raw 原始响应。
 */
export function normalizeSsoQrAuthorizeInfo(raw) {
    const value = raw !== null && typeof raw === 'object' ? raw : {};
    const expiresRaw = typeof value.expires_in === 'number' ? value.expires_in : Number(value.expires_in);
    const expiresIn = Number.isFinite(expiresRaw) && expiresRaw > 0 ? Math.floor(expiresRaw) : 0;
    return {
        authorizeUrl: typeof value.authorize_url === 'string' ? value.authorize_url : '',
        state: typeof value.state === 'string' ? value.state : '',
        expiresIn,
    };
}
/**
 * 归一轮询结果（未知状态回落 `pending`；非字符串 / 空串 `redirect` 丢弃）。
 *
 * @param raw 原始响应。
 */
export function normalizeSsoQrPollResult(raw) {
    const value = raw !== null && typeof raw === 'object' ? raw : {};
    const status = SSO_QR_STATUSES.includes(value.status)
        ? value.status
        : 'pending';
    const redirect = typeof value.redirect === 'string' && value.redirect !== '' ? value.redirect : undefined;
    return redirect === undefined ? { status } : { status, redirect };
}
