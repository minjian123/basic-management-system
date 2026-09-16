<script setup lang="ts">
/**
 * 权限按钮（框架无关最小版）：按动作权限码控制渲染。
 *
 * - `fallback="hide"`（默认）：无权限不渲染；
 * - `fallback="disable"`：无权限渲染禁用按钮 + `title` 提示（缺省 `common.noPermission`）；
 * - 禁用态点击被拦截（不 emit `click`）；关闭自动 attrs 继承由原生 button 承接 class / style。
 */

import { computed, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'
import { checkPerm } from '../../permission'

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

// 组件根（通用 props / 令牌属性协议 / 透传；原生 button 承接）
const base = useComponentBase({ ns: 'bms', identifier: 'perm-button' })
const attrs = useAttrs()

const buttonAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [base.nsClass('perm-button'), cls],
    style: sty,
    ...rest,
  })
})

const allowed = computed(() => {
  const perm = props.perm
  if (!perm || (Array.isArray(perm) && perm.length === 0)) {
    return true
  }
  return checkPerm(perm, props.mode)
})

const visible = computed(() => allowed.value || props.fallback === 'disable')
const blocked = computed(() => props.disabled || !allowed.value)

const tipText = computed(() => {
  if (props.tip) {
    return props.tip
  }
  if (blocked.value && !props.disabled) {
    return '没有操作权限'
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
  <button
    v-if="visible"
    v-bind="buttonAttrs"
    type="button"
    :disabled="blocked"
    :title="tipText"
    @click="onClick"
  >
    <slot />
  </button>
</template>
