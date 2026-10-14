<script setup lang="ts">
// 错误页：按状态码呈现缺省文案与操作（返回 / 重试），不暴露技术堆栈。
import { ElButton } from 'element-plus'
import { computed, watch } from 'vue'

import errorImage from '../../assets/images/error.svg'
import { useBaseDisplay } from '../../composables/useBaseDisplay'

/** 错误页状态码。 */
export type ErrorPageCode = 403 | 404 | 500

interface Props {
  /** 状态码。 */
  code: ErrorPageCode
  /** 标题（缺省按状态码）。 */
  title?: string
  /** 描述（缺省按状态码）。 */
  description?: string
  /** 追加显示重试（503 等场景；500 默认显示）。 */
  retry?: boolean
}

const DEFAULT_TEXT: Record<ErrorPageCode, { title: string; description: string }> = {
  403: { title: '无访问权限', description: '你没有访问该页面的权限，请联系管理员开通后重试。' },
  404: { title: '页面不存在', description: '你访问的页面已被移除或地址有误，请检查后重试。' },
  500: { title: '服务异常', description: '服务暂时不可用，请稍后重试；若持续异常请联系管理员。' },
}

const props = defineProps<Props>()
const emit = defineEmits<{ home: []; retry: []; back: []; contact: [] }>()

const resolvedTitle = computed(() => props.title || DEFAULT_TEXT[props.code].title)
const resolvedDescription = computed(() => props.description || DEFAULT_TEXT[props.code].description)
const retryable = computed(() => props.retry === true || props.code === 500)

/** 403 缺省操作含「联系管理员」（对齐《组件设计 · 异常与空状态》§3）。 */
const contactable = computed(() => props.code === 403)

const { display, value: titleValue } = useBaseDisplay<string>()
watch(resolvedTitle, (title) => display.setValue(title), { immediate: true })
</script>

<template>
  <div class="bms-error-page">
    <img class="bms-error-page__image" :src="errorImage" :alt="`错误 ${code}`" />
    <p class="bms-error-page__code" data-test="error-code">{{ code }}</p>
    <h2 class="bms-error-page__title">{{ titleValue }}</h2>
    <p class="bms-error-page__description">{{ resolvedDescription }}</p>
    <div class="bms-error-page__actions">
      <el-button data-test="error-back" @click="emit('back')">返回上一页</el-button>
      <el-button data-test="error-home" @click="emit('home')">返回首页</el-button>
      <el-button v-if="contactable" data-test="error-contact" @click="emit('contact')">联系管理员</el-button>
      <el-button v-if="retryable" data-test="error-retry" type="primary" @click="emit('retry')">重试</el-button>
      <slot name="action" />
    </div>
  </div>
</template>

<style scoped>
.bms-error-page {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
  align-items: center;
  justify-content: center;
  padding: var(--bms-space-8) var(--bms-space-4);
  text-align: center;
}

.bms-error-page__image {
  width: var(--bms-illustration-size);
  height: var(--bms-illustration-size);
  object-fit: contain;
}

.bms-error-page__code {
  margin: 0;
  font-size: calc(var(--bms-font-size-lg) * 2);
  font-weight: 700;
  line-height: 1.1;
  color: var(--bms-color-primary);
}

.bms-error-page__title {
  margin: 0;
  font-size: var(--bms-font-size-lg);
  font-weight: 600;
  color: var(--bms-color-text);
}

.bms-error-page__description {
  max-width: 460px;
  margin: 0;
  font-size: var(--bms-font-size-sm);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}

.bms-error-page__actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  justify-content: center;
  margin-top: var(--bms-space-3);
}
</style>

