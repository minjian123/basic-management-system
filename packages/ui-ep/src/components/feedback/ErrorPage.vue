<script setup lang="ts">
/**
 * 错误页：403 / 404 / 500 缺省插画 + 标题 + 说明 + 操作（《布局设计 · 异常与空状态》）。
 *
 * 契约见《组件设计 · 异常与空状态》§3：`code` 决定缺省插画 / 文案 / 操作；**不展示技术堆栈**；
 * 缺省操作点击始终 emit（`home` / `retry` / `contact`，通知语义）并执行缺省行为
 * （返回首页 / 刷新重试），传 `actions` 完全覆盖；独立路由接入 `/403` `/404` `/500`。
 */

import { useI18n } from 'vue-i18n'
import { computed, useAttrs } from 'vue'
import { useRouter } from 'vue-router'

import { ElButton } from 'element-plus'
import 'element-plus/es/components/button/style/css'

import empty403 from '../../assets/images/empty-403.svg'
import empty404 from '../../assets/images/empty-404.svg'
import empty500 from '../../assets/images/empty-500.svg'
import { useComponentBase } from '@bms/vue'

import type { FeedbackAction } from './types'

const props = withDefaults(
  defineProps<{
    code?: 403 | 404 | 500
    title?: string | null
    description?: string | null
    /** 自定义操作（提供即完全覆盖缺省操作；`key` 自定义时需传 `handler`） */
    actions?: FeedbackAction[] | null
  }>(),
  { code: 404, title: null, description: null, actions: null },
)

const emit = defineEmits<{
  home: []
  retry: []
  contact: []
}>()

const base = useComponentBase({ ns: 'bms', identifier: 'error-page' })
const { t } = useI18n()
const attrs = useAttrs()
/** 路由（缺省「返回首页」用；无 router 环境回退 `location.assign`） */
const router = useRouter()

const ILLUSTRATIONS: Record<403 | 404 | 500, string> = {
  403: empty403,
  404: empty404,
  500: empty500,
}

const ACTION_LABEL_KEYS: Record<string, string> = {
  home: 'feedback.backHome',
  retry: 'feedback.retry',
  contact: 'feedback.contactAdmin',
}

const illustration = computed(() => ILLUSTRATIONS[props.code])
const titleText = computed(() => props.title ?? t(`feedback.error${props.code}Title`))

const defaultActions = computed<FeedbackAction[]>(() => {
  if (props.code === 403) {
    return [{ key: 'home', type: 'primary' }, { key: 'contact' }]
  }
  if (props.code === 500) {
    return [{ key: 'retry', type: 'primary' }, { key: 'home' }]
  }
  return [{ key: 'home', type: 'primary' }]
})
const actionList = computed(() => props.actions ?? defaultActions.value)

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({ class: [base.nsClass('error-page'), cls], style: sty, ...rest })
})

function actionText(action: FeedbackAction): string {
  if (action.text) {
    return action.text
  }
  const key = action.key ? ACTION_LABEL_KEYS[action.key] : undefined
  return key ? t(key) : (action.key ?? '')
}

function goHome(): void {
  if (router) {
    void router.push('/')
    return
  }
  if (typeof window !== 'undefined') {
    window.location.assign('/')
  }
}

function reloadPage(): void {
  if (typeof window !== 'undefined' && typeof window.location?.reload === 'function') {
    window.location.reload()
  }
}

function runAction(action: FeedbackAction): void {
  if (action.handler) {
    action.handler()
    return
  }
  if (action.key === 'home') {
    emit('home')
    goHome()
    return
  }
  if (action.key === 'retry') {
    emit('retry')
    reloadPage()
    return
  }
  if (action.key === 'contact') {
    emit('contact')
  }
}
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('error-page')">
    <img :src="illustration" :class="base.nsClass('error-page-illustration')" alt="" />
    <h2 :class="base.nsClass('error-page-title')">{{ titleText }}</h2>
    <p v-if="description" :class="base.nsClass('error-page-description')">{{ description }}</p>
    <div v-if="actionList.length > 0" :class="base.nsClass('error-page-actions')">
      <el-button
        v-for="action in actionList"
        :key="action.key ?? action.text"
        :type="action.type === 'primary' ? 'primary' : 'default'"
        @click="runAction(action)"
      >
        {{ actionText(action) }}
      </el-button>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.bms-error-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bms-space-3);
  padding: var(--bms-space-8) var(--bms-space-4);
  color: var(--bms-color-text);
  text-align: center;
}

.bms-error-page-illustration {
  width: var(--bms-illustration-size);
  height: var(--bms-illustration-size);
  color: var(--bms-color-text-secondary);
}

.bms-error-page-title {
  margin: 0;
  font-size: var(--bms-font-size-lg);
  font-weight: var(--bms-font-weight-semibold);
}

.bms-error-page-description {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-base);
}

.bms-error-page-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-2);
}
</style>
