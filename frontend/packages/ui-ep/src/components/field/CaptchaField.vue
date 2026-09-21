<script setup lang="ts">
// 验证码字段（06_04 真实实现）：图形 / 滑块 / 短信三类形态分发与统一占位语义；
// 数据通路经注入式数据源（未注入即占位零请求），保留 06_01 冻结对外契约（仅向后兼容新增）。
import {
  CAPTCHA_PLACEHOLDER_TEXT,
  CAPTCHA_REQUIRED_TEXT,
  type CaptchaKind as CaptchaKindValue,
  type CaptchaPolicy,
  type CaptchaScene,
  type CaptchaSourceAdapter,
} from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseCaptcha } from '../../composables/useBaseCaptcha'
import ImageCaptcha from './ImageCaptcha.vue'
import SliderCaptcha from './SliderCaptcha.vue'
import SmsCaptcha from './SmsCaptcha.vue'

/** 验证码形态（与核心 `CaptchaKind` 同源）。 */
export type CaptchaKind = CaptchaKindValue

interface Props {
  /** 值（受控）。 */
  modelValue?: string
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 形态。 */
  kind?: CaptchaKind
  /** 图形验证码地址（外部直连；缺省由数据源获取）。 */
  imageUrl?: string
  /** 短信重发冷却配置（秒）。 */
  countdown?: number
  /** 禁用。 */
  disabled?: boolean
  /** 输入占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 使用场景。 */
  scene?: CaptchaScene
  /** 短信目标手机号。 */
  phone?: string
  /** 验证码数据源（未注入即占位零请求）。 */
  source?: CaptchaSourceAdapter
  /** 连续失败计数（阈值联动）。 */
  failCount?: number
  /** 失败阈值。 */
  failThreshold?: number
  /** 输入定长覆盖（0 按形态缺省）。 */
  inputLength?: number
  /** 父页面强制要求。 */
  required?: boolean
  /** 外部错误文案（优先）。 */
  errorMessage?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  ready: false,
  kind: 'image',
  imageUrl: '',
  countdown: 60,
  disabled: false,
  placeholder: '请输入验证码',
  degradeText: CAPTCHA_PLACEHOLDER_TEXT,
  scene: 'login',
  phone: '',
  source: undefined,
  failCount: 0,
  failThreshold: 3,
  inputLength: 0,
  required: false,
  errorMessage: '',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  refresh: []
  send: []
  invalid: [message: string]
  pass: [payload: { kind: CaptchaKind }]
  fail: [payload: { code?: number; message: string }]
  'rate-limit': [cooldown: number]
  expire: []
  policy: [policy: CaptchaPolicy]
}>()

const api = useBaseCaptcha({
  ready: props.ready,
  kind: props.kind,
  scene: props.scene,
  source: props.source,
  phone: props.phone,
  cooldown: props.countdown,
  failCount: props.failCount,
  failThreshold: props.failThreshold,
  inputLength: props.inputLength,
  required: props.required,
  disabled: props.disabled,
  value: props.modelValue,
  ...(props.imageUrl === '' ? {} : { imageUrl: props.imageUrl }),
})

watch(
  () => props.ready,
  (next) => api.setReady(next),
)
watch(
  () => props.kind,
  (next) => api.setKind(next),
)
watch(
  () => props.scene,
  (next) => api.setScene(next),
)
watch(
  () => props.source,
  (next) => api.setSource(next),
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
  () => props.failCount,
  (next) => api.setFailCount(next),
)
watch(
  () => props.failThreshold,
  (next) => api.setOptions({ failThreshold: next }),
)
watch(
  () => props.inputLength,
  (next) => api.setOptions({ inputLength: next }),
)
watch(
  () => props.required,
  (next) => api.setRequired(next),
)
watch(
  () => props.disabled,
  (next) => api.setOptions({ disabled: next }),
)
watch(
  () => props.imageUrl,
  (next) => {
    if (next !== '') {
      api.setImageUrl(next)
    }
  },
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

/** 场景策略加载（就绪后一次；零请求由族基类保证）。 */
watch(
  [() => api.ready.value, () => props.source],
  ([ready, source]) => {
    if (ready && source !== undefined) {
      void api.loadPolicy().then(() => {
        if (api.policy.value !== undefined) {
          emit('policy', api.policy.value)
        }
      })
    }
  },
  { immediate: true },
)

/** 已失效（20102）上抛。 */
watch(
  () => api.errorCode.value,
  (code) => {
    if (code === 20102) {
      emit('expire')
    }
  },
)

/** 生效错误文案（外部优先，其次族基类错误，最后必填提示）。 */
const errorText = computed(() => {
  if (props.errorMessage !== '') {
    return props.errorMessage
  }
  if (api.errorText.value !== '') {
    return api.errorText.value
  }
  if (props.required && api.value.value === '') {
    return CAPTCHA_REQUIRED_TEXT
  }
  return ''
})

/** 壳级重试（重新出题 / 获取策略）。 */
function onRetry(): void {
  void api.refresh()
  void api.loadPolicy()
}
</script>

<template>
  <div
    class="bms-captcha-field"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
    :data-kind="api.kind.value"
    data-test="captcha-field"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <slot v-else name="live" :disabled="api.disabled.value">
      <image-captcha
        v-if="api.kind.value === 'image'"
        :model-value="modelValue"
        :ready="true"
        :image-url="imageUrl"
        :source="source"
        :scene="scene"
        :input-length="inputLength"
        :disabled="disabled"
        :placeholder="placeholder"
        :error-message="errorMessage"
        :degrade-text="degradeText"
        @update:model-value="emit('update:modelValue', $event)"
        @change="emit('change', $event)"
        @refresh="emit('refresh')"
        @invalid="emit('invalid', $event)"
        @pass="emit('pass', { kind: 'image' })"
        @fail="emit('fail', $event)"
      />
      <slider-captcha
        v-else-if="api.kind.value === 'slider'"
        :ready="true"
        :image-url="imageUrl"
        :source="source"
        :scene="scene"
        :disabled="disabled"
        :degrade-text="degradeText"
        @pass="emit('pass', { kind: 'slider' })"
        @fail="emit('fail', $event)"
        @refresh="emit('refresh')"
      />
      <sms-captcha
        v-else
        :model-value="modelValue"
        :ready="true"
        :source="source"
        :scene="scene"
        :phone="phone"
        :countdown="countdown"
        :input-length="inputLength"
        :disabled="disabled"
        :placeholder="placeholder"
        :error-message="errorMessage"
        :degrade-text="degradeText"
        @update:model-value="emit('update:modelValue', $event)"
        @change="emit('change', $event)"
        @send="emit('send')"
        @invalid="emit('invalid', $event)"
        @rate-limit="emit('rate-limit', $event)"
        @pass="emit('pass', { kind: 'sms' })"
        @fail="emit('fail', $event)"
      />
      <slot name="tip" />
    </slot>

    <p v-if="errorText !== ''" class="bms-field-error" data-test="captcha-error">{{ errorText }}</p>
    <button v-if="api.error.value && errorText === ''" type="button" class="bms-captcha-field__retry" data-test="captcha-retry" @click="onRetry">
      重试
    </button>
  </div>
</template>

<style scoped>
.bms-captcha-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-captcha-field__retry {
  align-self: flex-start;
  color: var(--bms-color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
}
</style>
