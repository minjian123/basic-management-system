<script setup lang="ts">
/**
 * 权限按钮（框架无关最小版）：按动作权限码控制渲染。
 *
 * - `fallback="hide"`（默认）：无权限不渲染；
 * - `fallback="disable"`：无权限渲染禁用按钮 + `title` 提示（缺省 `common.noPermission`）；
 * - 禁用态点击被拦截（不 emit `click`）；关闭自动 attrs 继承由原生 button 承接 class / style。
 */

import { computed } from 'vue'

import { i18n } from '@/i18n'
import { hasPerm } from '@/utils/perm'

const props = withDefaults(
  defineProps<{
    /** 权限码（string / string[]；空值视为不限制） */
    perm?: string | string[]
    /** 数组判定模式（缺省 anyOf） */
    mode?: 'any' | 'all'
    /** 无权限时的行为（缺省隐藏） */
    fallback?: 'hide' | 'disable'
    /** 外部禁用（与权限无关） */
    disabled?: boolean
    /** 禁用提示文案（缺省 `common.noPermission`） */
    tip?: string
  }>(),
  {
    perm: '',
    mode: 'any',
    fallback: 'hide',
    disabled: false,
    tip: '',
  },
)

const emit = defineEmits<{
  click: [event: MouseEvent]
}>()

const allowed = computed(() => {
  const perm = props.perm
  if (!perm || (Array.isArray(perm) && perm.length === 0)) {
    return true
  }
  return hasPerm(perm, props.mode)
})

const visible = computed(() => allowed.value || props.fallback === 'disable')
const blocked = computed(() => props.disabled || !allowed.value)

const tipText = computed(() => {
  if (props.tip) {
    return props.tip
  }
  if (blocked.value && !props.disabled) {
    const t = i18n.global.t as unknown as (key: string) => string
    const text = t('common.noPermission')
    return text === 'common.noPermission' ? undefined : text
  }
  return undefined
})

const onClick = (event: MouseEvent): void => {
  if (blocked.value) {
    return
  }
  emit('click', event)
}
</script>

<template>
  <button v-if="visible" type="button" :disabled="blocked" :title="tipText" @click="onClick">
    <slot />
  </button>
</template>
