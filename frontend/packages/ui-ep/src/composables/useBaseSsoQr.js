/** 扫码登录投影：把核心扫码登录能力域基类 `BaseSsoQr` 投影为组合式（相位 / 授权 URL / 轮询 / 过期 / 可见性）。 */
import { BaseSsoQr, isSsoQrTerminal, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体扫码登录能力（可实例化）。 */
class SsoQrState extends BaseSsoQr {
}
/**
 * 使用扫码登录投影。
 *
 * @param options 选项。
 * @returns 扫码登录实例与响应式面。
 */
export function useBaseSsoQr(options = {}) {
    const instance = new SsoQrState();
    instance.setOptions({
        ...(options.pollBase === undefined ? {} : { pollBase: options.pollBase }),
        ...(options.pollMax === undefined ? {} : { pollMax: options.pollMax }),
        ...(options.maxFailures === undefined ? {} : { maxFailures: options.maxFailures }),
        ...(options.pauseWhenHidden === undefined ? {} : { pauseWhenHidden: options.pauseWhenHidden }),
    });
    instance.setTenant(options.tenant ?? null);
    if (options.ready !== undefined) {
        instance.setReady(options.ready);
    }
    if (options.source !== undefined) {
        instance.setSource(options.source);
    }
    if (options.providers !== undefined) {
        instance.setProviders(options.providers);
    }
    const ready = ref(instance.ready);
    const degraded = ref(instance.degraded);
    const phase = ref(instance.phase);
    const authorizeUrl = ref(instance.authorizeUrl);
    const providers = ref([...instance.providers]);
    const activeIdpKey = ref(instance.activeIdpKey);
    const redirect = ref(instance.redirect);
    const remaining = ref(instance.remaining);
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        ready.value = instance.ready;
        degraded.value = instance.degraded;
        phase.value = instance.phase;
        authorizeUrl.value = instance.authorizeUrl;
        providers.value = [...instance.providers];
        activeIdpKey.value = instance.activeIdpKey;
        redirect.value = instance.redirect;
        remaining.value = instance.remaining;
    }
    const off = instance.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        instance.dispose();
    });
    const statusText = computed(() => instance.statusText);
    const empty = computed(() => providers.value.length === 0);
    const terminal = computed(() => isSsoQrTerminal(phase.value));
    return {
        instance,
        ready,
        degraded,
        phase,
        statusText,
        authorizeUrl,
        providers,
        activeIdpKey,
        redirect,
        remaining,
        empty,
        terminal,
        setProviders: (next) => {
            instance.setProviders(next);
            sync();
        },
        setActiveProvider: (next) => {
            instance.setActiveProvider(next);
            sync();
        },
        setSource: (next) => {
            instance.setSource(next);
            sync();
        },
        setReady: (next) => {
            instance.setReady(next);
            sync();
        },
        setOptions: (next) => {
            instance.setOptions({
                ...(next.pollBase === undefined ? {} : { pollBase: next.pollBase }),
                ...(next.pollMax === undefined ? {} : { pollMax: next.pollMax }),
                ...(next.maxFailures === undefined ? {} : { maxFailures: next.maxFailures }),
                ...(next.pauseWhenHidden === undefined ? {} : { pauseWhenHidden: next.pauseWhenHidden }),
            });
            sync();
        },
        init: () => instance.init(),
        refresh: () => instance.refresh(),
        pause: () => instance.pause(),
        resume: () => instance.resume(),
    };
}
