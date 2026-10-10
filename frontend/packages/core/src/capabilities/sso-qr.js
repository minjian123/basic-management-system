/**
 * 扫码登录能力域基类：四态状态机 / 授权二维码取址 / 轮询与指数退避 / 过期自动重取一次 / 可见性暂停。
 *
 * 全链：`BaseObject → BaseFrameworkObject → BaseCapability → BasePluggable → BaseComponent
 *        → BasePlaceholderState → BaseSsoQr`（能力键 `sso-qr`）。
 * 数据通路经注入式 `SsoQrLoginSourceAdapter`（可替换实现经 `SsoQrSourceRegistry` 登记），**未注入即占位零请求**；
 * 核心不依赖 Vue / DOM / 浏览器 API（定时器为环境级能力，随释放停表）。
 *
 * 平台不对外暴露「已扫待确认」态，`scanned` 仅由可注入状态源回报（平台限制，见领域模块说明）。
 */
import { SSO_QR_MAX_FAILURES, SSO_QR_POLL_BASE, SSO_QR_POLL_MAX, isSsoQrTerminal, nextSsoQrPollDelay, normalizeSsoQrAuthorizeInfo, normalizeSsoQrPollResult, resolveSsoQrStatusText, selectScannableProviders, } from '../domain/sso-qr';
import { BasePlaceholderState } from './placeholder-state';
/** 扫码登录能力域基类（抽象）。 */
export class BaseSsoQr extends BasePlaceholderState {
    /** 能力键。 */
    identifier = 'sso-qr';
    /** 依赖能力键。 */
    depends = ['placeholder-state'];
    /** 当前相位。 */
    phase = 'pending';
    /** 可扫码入口（已过滤 / 排序）。 */
    providers = [];
    /** 当前 IdP 标识（可扫码入口之一）。 */
    activeIdpKey = null;
    /** 租户编码（可选；由宿主注入）。 */
    tenant = null;
    /** 状态源（未注入即占位零请求）。 */
    source;
    /** 授权 URL（供渲染二维码）。 */
    authorizeUrl = '';
    /** 流程状态（一次性）。 */
    state = '';
    /** 有效期（秒；0 表示不自动过期）。 */
    expiresIn = 0;
    /** 剩余有效期（秒；起过期计时时写入）。 */
    remaining = 0;
    /** 连续轮询失败次数。 */
    failures = 0;
    /** 是否已自动重取过（每次过期至多一次）。 */
    autoRefreshed = false;
    /** 确认后的完成跳转地址（状态源回报）。 */
    redirect;
    /** 轮询间隔基数（毫秒）。 */
    pollBase = SSO_QR_POLL_BASE;
    /** 轮询退避上限（毫秒）。 */
    pollMax = SSO_QR_POLL_MAX;
    /** 连续失败阈值。 */
    maxFailures = SSO_QR_MAX_FAILURES;
    /** 页面隐藏时是否暂停轮询。 */
    pauseWhenHidden = true;
    /** 是否暂停（不可见）。 */
    #paused = false;
    /** 代数（异步竞态防护：仅当次代数有效）。 */
    #generation = 0;
    /** 过期时间戳（毫秒）。 */
    #expiresAt = 0;
    /** 过期计时器。 */
    #expiryTimer;
    /** 轮询计时器。 */
    #pollTimer;
    /** 相位监听器。 */
    #listeners = [];
    /** 是否降级（占位）：未就绪或未注入状态源。 */
    get degraded() {
        return super.degraded || this.source === undefined;
    }
    /** 当前生效入口。 */
    get activeProvider() {
        return this.providers.find((provider) => provider.idp_key === this.activeIdpKey);
    }
    /** 相位文案。 */
    get statusText() {
        return resolveSsoQrStatusText(this.phase);
    }
    /** 是否终态（停止轮询）。 */
    get terminal() {
        return isSsoQrTerminal(this.phase);
    }
    /**
     * 设置可扫码入口（过滤 + 排序）；当前入口失效时回落首个。
     *
     * @param providers 原始入口清单。
     */
    setProviders(providers) {
        this.providers = selectScannableProviders(providers);
        if (!this.providers.some((provider) => provider.idp_key === this.activeIdpKey)) {
            this.activeIdpKey = this.providers[0]?.idp_key ?? null;
        }
        this.#notifyUpdate();
    }
    /**
     * 切换当前入口（重置自动重取标记；由调用方随后 `init()`）。
     *
     * @param idpKey IdP 标识。
     */
    setActiveProvider(idpKey) {
        this.activeIdpKey = idpKey;
        this.autoRefreshed = false;
        this.#notifyUpdate();
    }
    /**
     * 注入状态源。
     *
     * @param source 状态源（`undefined` 即占位）。
     */
    setSource(source) {
        this.source = source;
        this.#notifyUpdate();
    }
    /**
     * 设置租户编码。
     *
     * @param tenant 租户编码。
     */
    setTenant(tenant) {
        this.tenant = tenant;
    }
    /**
     * 设置选项（缺省项不覆盖）。
     *
     * @param options 选项。
     */
    setOptions(options) {
        if (options.pollBase !== undefined) {
            this.pollBase = options.pollBase;
        }
        if (options.pollMax !== undefined) {
            this.pollMax = options.pollMax;
        }
        if (options.maxFailures !== undefined) {
            this.maxFailures = options.maxFailures;
        }
        if (options.pauseWhenHidden !== undefined) {
            this.pauseWhenHidden = options.pauseWhenHidden;
        }
    }
    /**
     * 注册相位变化监听器。
     *
     * @param listener 监听器。
     * @returns 取消函数（幂等）。
     */
    onPhaseChange(listener) {
        this.#listeners.push(listener);
        return () => {
            const index = this.#listeners.indexOf(listener);
            if (index >= 0) {
                this.#listeners.splice(index, 1);
            }
        };
    }
    /**
     * 初始化：取授权 URL → 起过期计时与轮询。
     *
     * 占位（未注入状态源 / 无可用入口）时不动作；取址失败转 `failed`。
     */
    async init() {
        const provider = this.activeProvider;
        const source = this.source;
        if (this.isDisposed || this.degraded || provider === undefined || source?.init === undefined) {
            return;
        }
        const generation = ++this.#generation;
        this.#clearTimers();
        this.failures = 0;
        this.redirect = undefined;
        this.authorizeUrl = '';
        this.state = '';
        this.expiresIn = 0;
        this.remaining = 0;
        this.markLoaded();
        let raw;
        try {
            raw = await source.init({ idpKey: provider.idp_key, tenant: this.tenant });
        }
        catch (error) {
            if (generation !== this.#generation || this.isDisposed) {
                return;
            }
            this.reportError(error, { scope: 'BaseSsoQr.init' });
            this.#setPhase('failed');
            return;
        }
        if (generation !== this.#generation || this.isDisposed) {
            return;
        }
        const info = normalizeSsoQrAuthorizeInfo(raw);
        this.authorizeUrl = info.authorizeUrl;
        this.state = info.state;
        this.expiresIn = info.expiresIn;
        this.remaining = info.expiresIn;
        this.#expiresAt = info.expiresIn > 0 ? Date.now() + info.expiresIn * 1000 : 0;
        this.#notifyUpdate();
        this.#setPhase('pending');
        this.#startExpiryTimer();
        this.#schedulePoll(generation);
    }
    /** 手动刷新（重置自动重取标记后重新初始化）。 */
    refresh() {
        this.autoRefreshed = false;
        void this.init();
    }
    /** 暂停（页面不可见）：停轮询与过期计时。 */
    pause() {
        if (this.#paused) {
            return;
        }
        this.#paused = true;
        this.#clearTimers();
    }
    /** 恢复（页面可见）：续过期计时与轮询。 */
    resume() {
        if (!this.#paused) {
            return;
        }
        this.#paused = false;
        if (this.isDisposed || this.terminal) {
            return;
        }
        const generation = this.#generation;
        this.#startExpiryTimer();
        this.#schedulePoll(generation);
    }
    /** 轮询一次（供内部计时器与测试调用）。 */
    async pollOnce() {
        await this.#poll(this.#generation);
    }
    /** 释放：清定时器与监听器。 */
    onDispose() {
        this.#generation += 1;
        this.#clearTimers();
        this.#listeners.length = 0;
        super.onDispose();
    }
    /**
     * 设置相位并广播（变化时）。
     *
     * @param phase 目标相位。
     */
    #setPhase(phase) {
        if (this.phase === phase) {
            return;
        }
        this.phase = phase;
        for (const listener of [...this.#listeners]) {
            try {
                listener(phase);
            }
            catch (error) {
                this.reportError(error, { scope: 'BaseSsoQr.phase' });
            }
        }
        this.#notifyUpdate();
    }
    /** 生命周期更新通知（释放后忽略）。 */
    #notifyUpdate() {
        if (!this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
    /**
     * 起过期计时器（`expiresIn <= 0` 或已暂停 / 终态不起）。
     */
    #startExpiryTimer() {
        this.#clearExpiryTimer();
        if (this.#paused || this.isDisposed || this.terminal || this.#expiresAt <= 0) {
            return;
        }
        const delay = Math.max(0, this.#expiresAt - Date.now());
        this.#expiryTimer = setTimeout(() => {
            this.#enterExpired();
        }, delay);
    }
    /**
     * 调度下一次轮询（按当前失败次数退避）。
     *
     * @param generation 代数。
     */
    #schedulePoll(generation) {
        this.#clearPollTimer();
        if (this.#paused || this.isDisposed || this.terminal) {
            return;
        }
        const delay = nextSsoQrPollDelay(this.failures + 1, { base: this.pollBase, max: this.pollMax });
        this.#pollTimer = setTimeout(() => {
            void this.#poll(generation);
        }, delay);
    }
    /**
     * 轮询一次并应用结果（失败退避；连续失败达阈值转 `failed`）。
     *
     * @param generation 代数。
     */
    async #poll(generation) {
        if (generation !== this.#generation || this.#paused || this.isDisposed || this.terminal) {
            return;
        }
        const provider = this.activeProvider;
        const source = this.source;
        if (provider === undefined || source?.poll === undefined) {
            return;
        }
        let raw;
        try {
            raw = await source.poll({
                idpKey: provider.idp_key,
                tenant: this.tenant,
                state: this.state,
                attempt: this.failures + 1,
            });
        }
        catch (error) {
            if (generation !== this.#generation || this.isDisposed) {
                return;
            }
            this.failures += 1;
            this.reportError(error, { scope: 'BaseSsoQr.poll' });
            if (this.failures >= this.maxFailures) {
                this.#clearPollTimer();
                this.#setPhase('failed');
                return;
            }
            this.#schedulePoll(generation);
            return;
        }
        if (generation !== this.#generation || this.isDisposed) {
            return;
        }
        this.failures = 0;
        const result = normalizeSsoQrPollResult(raw);
        if (result.status === 'confirmed') {
            this.redirect = result.redirect;
            this.#clearTimers();
            this.#setPhase('confirmed');
            return;
        }
        if (result.status === 'expired') {
            this.#enterExpired();
            return;
        }
        this.#setPhase(result.status);
        this.#schedulePoll(generation);
    }
    /** 进入过期：停轮询；未自动重取过则重取一次。 */
    #enterExpired() {
        this.#clearPollTimer();
        this.#setPhase('expired');
        if (!this.autoRefreshed) {
            this.autoRefreshed = true;
            void this.init();
        }
    }
    /** 清过期计时器。 */
    #clearExpiryTimer() {
        if (this.#expiryTimer !== undefined) {
            clearTimeout(this.#expiryTimer);
            this.#expiryTimer = undefined;
        }
    }
    /** 清轮询计时器。 */
    #clearPollTimer() {
        if (this.#pollTimer !== undefined) {
            clearTimeout(this.#pollTimer);
            this.#pollTimer = undefined;
        }
    }
    /** 清全部计时器。 */
    #clearTimers() {
        this.#clearExpiryTimer();
        this.#clearPollTimer();
    }
}
