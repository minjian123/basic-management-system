/** 验证码投影：把核心验证码族组件基类 `BaseCaptcha` 投影为组合式（挑战 / 倒计时 / 校验 / 滑块轨迹 / 阈值联动）。 */
import { BaseCaptcha, } from '@bms/core';
import { computed, onScopeDispose, ref } from 'vue';
/** 具体验证码族（可实例化）。 */
class CaptchaState extends BaseCaptcha {
}
/**
 * 使用验证码投影。
 *
 * @param options 选项。
 * @returns 验证码族实例与响应式面。
 */
export function useBaseCaptcha(options = {}) {
    const captcha = new CaptchaState();
    const localDisabled = ref(options.disabled ?? false);
    captcha.setOptions({
        ready: options.ready ?? false,
        kind: options.kind ?? 'image',
        scene: options.scene ?? 'login',
        ...(options.source === undefined ? {} : { source: options.source }),
        ...(options.phone === undefined ? {} : { phone: options.phone }),
        ...(options.cooldown === undefined ? {} : { cooldown: options.cooldown }),
        ...(options.failCount === undefined ? {} : { failCount: options.failCount }),
        ...(options.failThreshold === undefined ? {} : { failThreshold: options.failThreshold }),
        ...(options.inputLength === undefined ? {} : { inputLength: options.inputLength }),
        ...(options.required === undefined ? {} : { required: options.required }),
        ...(options.imageUrl === undefined ? {} : { imageUrl: options.imageUrl }),
    });
    if (options.value !== undefined) {
        captcha.setValue(options.value);
    }
    const ready = ref(captcha.ready);
    const degraded = ref(captcha.degraded);
    const requestCount = ref(captcha.requestCount);
    const value = ref(captcha.value);
    const kind = ref(captcha.kind);
    const scene = ref(captcha.scene);
    const imageUrl = ref(captcha.imageUrl);
    const challengeId = ref(captcha.challengeId);
    const payload = ref(captcha.payload);
    const sliderParams = ref(captcha.sliderParams);
    const phase = ref(captcha.phase);
    const countdown = ref(captcha.countdown);
    const cooldown = ref(captcha.cooldown);
    const sending = ref(captcha.sending);
    const verifying = ref(captcha.verifying);
    const passed = ref(captcha.passed);
    const needsChallenge = ref(captcha.needsChallenge);
    const maskedTarget = ref(captcha.maskedTarget);
    const inputMaxLength = ref(captcha.inputMaxLength);
    const inputHint = ref(captcha.inputHint);
    const errorCode = ref(captcha.errorCode);
    const errorMessage = ref(captcha.errorMessage);
    const errorText = ref(captcha.errorText);
    const error = ref(captcha.error);
    const empty = ref(captcha.empty);
    const hasImage = ref(captcha.hasImage);
    const trace = ref([...captcha.trace]);
    const policy = ref(captcha.policyData);
    /** 同步核心实例状态到响应式面。 */
    function sync() {
        ready.value = captcha.ready;
        degraded.value = captcha.degraded;
        requestCount.value = captcha.requestCount;
        value.value = captcha.value;
        kind.value = captcha.kind;
        scene.value = captcha.scene;
        imageUrl.value = captcha.imageUrl;
        challengeId.value = captcha.challengeId;
        payload.value = captcha.payload;
        sliderParams.value = captcha.sliderParams;
        phase.value = captcha.phase;
        countdown.value = captcha.countdown;
        cooldown.value = captcha.cooldown;
        sending.value = captcha.sending;
        verifying.value = captcha.verifying;
        passed.value = captcha.passed;
        needsChallenge.value = captcha.needsChallenge;
        maskedTarget.value = captcha.maskedTarget;
        inputMaxLength.value = captcha.inputMaxLength;
        inputHint.value = captcha.inputHint;
        errorCode.value = captcha.errorCode;
        errorMessage.value = captcha.errorMessage;
        errorText.value = captcha.errorText;
        error.value = captcha.error;
        empty.value = captcha.empty;
        hasImage.value = captcha.hasImage;
        trace.value = [...captcha.trace];
        policy.value = captcha.policyData;
    }
    const off = captcha.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    const offValue = captcha.onChange(() => sync());
    onScopeDispose(() => {
        off();
        offValue();
        captcha.dispose();
    });
    const disabled = computed(() => localDisabled.value || !ready.value);
    const api = {
        captcha,
        ready,
        degraded,
        disabled,
        requestCount,
        value,
        kind,
        scene,
        imageUrl,
        challengeId,
        payload,
        sliderParams,
        phase,
        countdown,
        cooldown,
        sending,
        verifying,
        passed,
        needsChallenge,
        maskedTarget,
        inputMaxLength,
        inputHint,
        errorCode,
        errorMessage,
        errorText,
        error,
        empty,
        hasImage,
        trace,
        policy,
        setReady: (next) => captcha.setReady(next),
        setSource: (next) => captcha.setSource(next),
        setKind: (next) => captcha.setKind(next),
        setScene: (next) => captcha.setScene(next),
        setValue: (next) => captcha.setValue(next),
        syncValue: (next) => {
            captcha.setValue(next);
            sync();
        },
        setPhone: (next) => captcha.setPhone(next),
        setCooldown: (next) => captcha.setCooldown(next),
        setFailCount: (next) => captcha.setFailCount(next),
        setRequired: (next) => captcha.setRequired(next),
        setImageUrl: (next) => captcha.setImageUrl(next),
        setOptions: (next) => {
            if (next.disabled !== undefined) {
                localDisabled.value = next.disabled;
            }
            const { disabled: _disabled, value: initialValue, ...rest } = next;
            void _disabled;
            captcha.setOptions(rest);
            if (initialValue !== undefined) {
                captcha.setValue(initialValue);
            }
            sync();
        },
        loadPolicy: () => captcha.loadPolicy(),
        loadChallenge: () => captcha.loadChallenge(),
        refresh: () => captcha.refresh(),
        sendSms: () => captcha.sendSms(),
        verify: () => captcha.verify(),
        submitSlider: () => captcha.submitSlider(),
        pushTrace: (point) => captcha.pushTrace(point),
        clearTrace: () => captcha.clearTrace(),
        startCountdown: (seconds) => captcha.startCountdown(seconds),
        stopCountdown: () => captcha.stopCountdown(),
        tickCountdown: () => captcha.tickCountdown(),
        invalidate: () => captcha.invalidate(),
        reset: () => captcha.reset(),
        clearInput: () => captcha.clearInput(),
        onValueChange: (listener) => captcha.onChange(listener),
    };
    return api;
}
