<script setup lang="ts">
// 图形验证码件（06_04）：后端图片（base64 → data URL）展示、点击 / 按钮刷新（一次性失效）、
// 输入校验与错误反馈；数据通路经注入式数据源（未注入即占位零请求）。
import {
  CAPTCHA_IMAGE_EMPTY_TEXT,
  CAPTCHA_INPUT_PLACEHOLDER,
  CAPTCHA_PASS_TEXT,
  CAPTCHA_PLACEHOLDER_TEXT,
  CAPTCHA_REFRESH_TEXT,
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
  /** 外部直连图片地址（缺省由数据源获取）。 */
  imageUrl?: string
  /** 验证码数据源（未注入即占位零请求）。 */
  source?: CaptchaSourceAdapter
  /** 使用场景。 */
  scene?: CaptchaScene
  /** 输入定长覆盖（0 按形态缺省 4-6 位）。 */
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
  imageUrl: '',
  source: undefined,
  scene: 'login',
  inputLength: 0,
  disabled: false,
  placeholder: CAPTCHA_INPUT_PLACEHOLDER,
  errorMessage: '',
  degradeText: CAPTCHA_PLACEHOLDER_TEXT,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  change: [value: string]
  refresh: []
  invalid: [message: string]
  pass: []
  fail: [payload: { code?: number; message: string }]
  loaded: [challengeId: string]
}>()

const api = useBaseCaptcha({
  ready: props.ready,
  kind: 'image',
  scene: props.scene,
  source: props.source,
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
  () => props.inputLength,
  (next) => api.setOptions({ inputLength: next }),
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
  { immediate: true },
)
watch(
  () => props.modelValue,
  (next) => api.syncValue(next),
  { immediate: true },
)
watch(
  [() => api.ready.value, () => props.imageUrl],
  ([ready, external]) => {
    if (ready && external === '') {
      void api.loadChallenge()
    }
  },
  { immediate: true },
)

api.onValueChange((next) => {
  const value = next ?? ''
  emit('update:modelValue', value)
  emit('change', value)
})

/** 生效错误文案（外部优先）。 */
const errorText = computed(() => (props.errorMessage !== '' ? props.errorMessage : api.errorText.value))

/** 当前受控输入（未受控时回落实例值）。 */
const inputValue = computed(() => api.value.value ?? '')

/** 刷新挑战（一次性失效后重取；未注入数据源即零请求）。 */
async function onRefresh(): Promise<void> {
  emit('refresh')
  const ok = await api.refresh()
  if (ok) {
    emit('loaded', api.challengeId.value)
  }
}

/** 校验当前输入（通过 / 失败上抛；失败自动刷新图形码）。 */
async function onSubmit(): Promise<void> {
  const precheck = checkCaptchaInput(api.value.value, 'image', props.inputLength)
  if (!precheck.valid) {
    emit('invalid', precheck.message)
    return
  }
  const ok = await api.verify()
  if (ok) {
    emit('pass')
    return
  }
  const code = api.errorCode.value
  const message = api.errorText.value
  if (code === 20101 && props.imageUrl === '') {
    await api.refresh()
  }
  emit('fail', { code, message })
}

/**
 * 输入变更（受控上报）。
 *
 * @param event 输入事件。
 */
function onInput(event: Event): void {
  const value = (event.target as HTMLInputElement).value
  api.setValue(value)
}
</script>

<template>
  <div
    class="bms-image-captcha"
    :data-ready="api.ready.value"
    :data-degraded="api.degraded.value"
    data-test="image-captcha"
  >
    <slot v-if="api.degraded.value" name="degrade">
      <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>

    <template v-else>
      <div class="bms-image-captcha__row">
        <input
          class="bms-image-captcha__input"
          :value="inputValue"
          :disabled="api.disabled.value"
          :maxlength="api.inputMaxLength.value"
          :placeholder="placeholder"
          data-test="captcha-input"
          @input="onInput"
          @keyup.enter="onSubmit"
        />
        <button
          type="button"
          class="bms-image-captcha__refresh"
          :disabled="api.disabled.value"
          data-test="captcha-send"
          @click="onRefresh"
        >
          {{ CAPTCHA_REFRESH_TEXT }}
        </button>
      </div>

      <button
        v-if="api.hasImage.value"
        type="button"
        class="bms-image-captcha__image-button"
        :disabled="api.disabled.value"
        title="点击刷新"
        data-test="captcha-image"
        @click="onRefresh"
      >
        <img class="bms-image-captcha__image" :src="api.imageUrl.value" alt="验证码" />
      </button>
      <div v-else class="bms-image-captcha__image-empty" data-test="captcha-image-empty">
        {{ CAPTCHA_IMAGE_EMPTY_TEXT }}
      </div>

      <p v-if="api.passed.value" class="bms-image-captcha__pass" data-test="captcha-pass">
        {{ CAPTCHA_PASS_TEXT }}
      </p>
      <p v-if="errorText !== ''" class="bms-field-error" data-test="captcha-error">{{ errorText }}</p>
    </template>
  </div>
</template>

<style scoped>
.bms-image-captcha {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-image-captcha__row {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
}
.bms-image-captcha__input {
  flex: 1;
  min-width: 0;
  padding: 0 var(--bms-spacing-md);
  line-height: 32px;
  border: 1px solid var(--bms-captcha-image-border);
  border-radius: var(--bms-radius-md);
}
.bms-image-captcha__refresh {
  padding: 0 var(--bms-spacing-lg);
  line-height: 32px;
  color: var(--bms-color-primary);
  background: transparent;
  border: 1px solid var(--bms-captcha-image-border);
  border-radius: var(--bms-radius-md);
  cursor: pointer;
}
.bms-image-captcha__image-button {
  padding: 0;
  background: transparent;
  border: none;
  cursor: pointer;
}
.bms-image-captcha__image {
  height: 40px;
  background: var(--bms-captcha-image-bg);
  border: 1px solid var(--bms-captcha-image-border);
  border-radius: var(--bms-radius-md);
}
.bms-image-captcha__image-empty {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bms-captcha-countdown-color);
  background: var(--bms-captcha-image-bg);
  border: 1px dashed var(--bms-captcha-image-border);
  border-radius: var(--bms-radius-md);
}
.bms-image-captcha__pass {
  margin: 0;
  color: var(--bms-captcha-pass-color);
  font-size: 12px;
}
</style>
