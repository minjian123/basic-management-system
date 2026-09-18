<script setup lang="ts">
// 验证码字段（占位版，06_01）：图形 / 滑块 / 短信三类形态的契约先行冻结；未就绪不发送。
import { computed, watch } from 'vue'

import { useFieldPlaceholder } from '../../composables/useFieldPlaceholder'

/** 验证码形态。 */
export type CaptchaKind = 'image' | 'slider' | 'sms'

interface Props {
  /** 值（受控）。 */
  modelValue?: string
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 形态。 */
  kind?: CaptchaKind
  /** 图形验证码地址（就绪后由后端提供）。 */
  imageUrl?: string
  /** 短信倒计时（秒）。 */
  countdown?: number
  /** 禁用。 */
  disabled?: boolean
  /** 占位提示。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: undefined,
  ready: false,
  kind: 'image',
  imageUrl: '',
  countdown: 60,
  disabled: false,
  placeholder: '请输入验证码',
  degradeText: '验证码未就绪（占位）',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  refresh: []
  send: []
}>()

const field = useFieldPlaceholder({ ready: props.ready, disabled: props.disabled })

watch(
  () => props.ready,
  (next) => field.setReady(next),
)

/** 发送按钮文案（短信形态）。 */
const sendText = computed(() => (props.kind === 'sms' ? `发送验证码（${props.countdown}s）` : '刷新'))
</script>

<template>
  <div
    class="bms-captcha-field"
    :data-ready="field.ready.value"
    :data-degraded="field.degraded.value"
    :data-kind="kind"
  >
    <slot v-if="field.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <div v-else class="bms-captcha-field__live">
      <input
        class="bms-captcha-field__input"
        :value="modelValue"
        :disabled="field.disabled.value"
        :placeholder="placeholder"
        @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <button
        type="button"
        :disabled="field.disabled.value"
        data-test="captcha-send"
        @click="kind === 'sms' ? emit('send') : emit('refresh')"
      >
        {{ sendText }}
      </button>
      <img v-if="kind === 'image' && imageUrl !== ''" class="bms-captcha-field__image" :src="imageUrl" alt="验证码" />
    </div>
  </div>
</template>
