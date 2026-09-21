<script setup lang="ts">
// 短信验证码件（06_04）：手机号脱敏展示、发送与 60s 倒计时（限流命中不重置）、
// 一次性验证码自动填充语义与错误分类提示；数据通路经注入式数据源（未注入即占位零请求）。
import {
  CAPTCHA_PASS_TEXT,
  CAPTCHA_PLACEHOLDER_TEXT,
  CAPTCHA_RESEND_TEXT,
  CAPTCHA_SEND_TEXT,
  CAPTCHA_SMS_COOLDOWN,
  CAPTCHA_SMS_INPUT_PLACEHOLDER,
  checkCaptchaInput,
  type CaptchaScene,
  type CaptchaSourceAdapter,
} from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseCaptcha } from '../../composables/useBaseCaptcha'

interface Props {
  /** 值（受控）。 */
  modelValue?: string
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 验证码数据源（未注入即占位零请求）。 */
  source?: CaptchaSourceAdapter
  /** 使用场景。 */
  scene?: CaptchaScene
  /** 目标手机号（展示一律脱敏）。 */
  phone?: string
  /** 重发冷却配置（秒）。 */
  countdown?: number
  /** 输入定长覆盖（缺省 6 位）。 */
  inputLength?: number
  /** 禁用。 */
  disabled?: boolean
  /** 输入占位提示。 */
  placeholder?: string
  /** 外部错误文案（优先）。 */
  errorMessage?: string
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  ready: false,
  source: undefined,
  scene: 'login',
  phone: '',
  countdown: CAPTCHA_SMS_COOLDOWN,
  inputLength: 0,
  disabled: false,
  placeholder: CAPTCHA_SMS_INPUT_PLACEHOLDER,
  errorMessage: '',
  degradeText: CAPTCHA_PLACEHOLDER_TEXT,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  send: []
  invalid: [message: string]
  'rate-limit': [cooldown: number]
  pass: []
  fail: [payload: { code?: number; message: string }]
}>()

const api = useBaseCaptcha({
  ready: props.ready,
  kind: 'sms',
  scene: props.scene,
  source: props.source,
  phone: props.phone,
  cooldown: props.countdown,
  inputLength: props.inputLength,
  disabled: props.disabled,
  value: props.modelValue,
})

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.source,
  (next) => api.setSource(next),
)
watch(
  () => props.scene,
  (next) => api.setScene(next),
)
watch(
  () => props.phone,
  (next) => api.setPhone(next),
)
watch(
  () => props.countdown,
  (next) => api.setCooldown(next),
)
watch(
  () => props.inputLength,
  (next) => api.setOptions({ inputLength: next }),
)
watch(
  () => props.disabled,
  (next) => api.setOptions({ disabled: next }),
)
watch(
  () => props.modelValue,
  (next) => api.syncValue(next),
  { immediate: true },
)

api.onValueChange((next) => {
  const value = next ?? ''
  emit('update:modelValue', value)
  emit('change', value)
})

/** 发送按钮文案（倒计时中为「重新发送(ns)」；空闲含配置冷却秒数，兼容 06_01 冻结显示）。 */
const sendText = computed(() => {
  const active = api.countdown.value
  if (active > 0) {
    return `${CAPTCHA_RESEND_TEXT}(${active}s)`
  }
  return `${CAPTCHA_SEND_TEXT}（${api.cooldown.value}s）`
})

/** 发送按钮禁用（占位 / 禁用 / 冷却中 / 发送中 / 手机号缺失）。 */
const sendDisabled = computed(() => api.disabled.value || api.countdown.value > 0 || api.sending.value)

/** 生效错误文案（外部优先）。 */
const errorText = computed(() => (props.errorMessage !== '' ? props.errorMessage : api.errorText.value))

/** 当前受控输入。 */
const inputValue = computed(() => api.value.value ?? '')

/** 发送短信验证码（成功启动倒计时；限流提示且不重置倒计时）。 */
async function onSend(): Promise<void> {
  emit('send')
  const ok = await api.sendSms()
  if (ok) {
    return
  }
  if (api.errorCode.value === 20103) {
    emit('rate-limit', api.cooldown.value)
  }
}

/** 校验当前输入（通过 / 失败上抛）。 */
async function onSubmit(): Promise<void> {
  const precheck = checkCaptchaInput(api.value.value, 'sms', props.inputLength)
  if (!precheck.valid) {
    emit('invalid', precheck.message)
    return
  }
  const ok = await api.verify()
  if (ok) {
    emit('pass')
    return
  }
  emit('fail', { code: api.errorCode.value, message: api.errorText.value })
}

/**
 * 输入变更（受控上报）。
 *
 * @param event 输入事件。
 */
function onInput(event: Event): void {
  api.setValue((event.target as HTMLInputElement).value)
}
</script>

<template>
  <div class="bms-sms-captcha" :data-ready="api.ready.value" :data-degraded="api.degraded.value" data-test="sms-captcha">
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <div class="bms-sms-captcha__row">
        <input
          class="bms-sms-captcha__input"
          :value="inputValue"
          :disabled="api.disabled.value"
          :maxlength="api.inputMaxLength.value"
          :placeholder="placeholder"
          inputmode="numeric"
          autocomplete="one-time-code"
          data-test="captcha-input"
          @input="onInput"
          @keyup.enter="onSubmit"
        />
        <button
          type="button"
          class="bms-sms-captcha__send"
          :disabled="sendDisabled"
          data-test="captcha-send"
          @click="onSend"
        >
          {{ sendText }}
        </button>
      </div>

      <p v-if="api.maskedTarget.value !== ''" class="bms-sms-captcha__target" data-test="captcha-target">
        发送至：{{ api.maskedTarget.value }}
      </p>
      <p v-if="api.countdown.value > 0" class="bms-sms-captcha__countdown" data-test="captcha-countdown">
        {{ api.countdown.value }}s
      </p>
      <p v-if="api.passed.value" class="bms-sms-captcha__pass" data-test="captcha-pass">{{ CAPTCHA_PASS_TEXT }}</p>
      <p v-if="errorText !== ''" class="bms-field-error" data-test="captcha-error">{{ errorText }}</p>
    </template>
  </div>
</template>

<style scoped>
.bms-sms-captcha {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-sms-captcha__row {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
}
.bms-sms-captcha__input {
  flex: 1;
  min-width: 0;
  padding: 0 var(--bms-spacing-md);
  line-height: 32px;
  border: 1px solid var(--bms-captcha-border);
  border-radius: var(--bms-radius-md);
}
.bms-sms-captcha__send {
  padding: 0 var(--bms-spacing-lg);
  line-height: 32px;
  color: var(--bms-color-primary);
  background: transparent;
  border: 1px solid var(--bms-captcha-border);
  border-radius: var(--bms-radius-md);
  cursor: pointer;
  white-space: nowrap;
}
.bms-sms-captcha__send:disabled {
  color: var(--bms-captcha-countdown-color);
  cursor: not-allowed;
}
.bms-sms-captcha__target,
.bms-sms-captcha__countdown {
  margin: 0;
  color: var(--bms-captcha-countdown-color);
  font-size: 12px;
}
.bms-sms-captcha__pass {
  margin: 0;
  color: var(--bms-captcha-pass-color);
  font-size: 12px;
}
</style>
