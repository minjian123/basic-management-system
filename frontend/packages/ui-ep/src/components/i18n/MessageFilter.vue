<script setup lang="ts">
// 文案筛选件（08_07）：模块前缀 / 关键词 / 缺失 / 仅已修改 / 语言聚焦；变更不直接请求（由容器放行后重取）。
import type { I18nFilter } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseMessageCatalog } from '../../composables/useBaseMessageCatalog'

interface Props {
  /** 筛选条件。 */
  modelValue: I18nFilter
  /** 语言清单（语言聚焦下拉）。 */
  locales?: readonly { code: string; name: string }[]
  /** 存在缺失翻译的语言（强调提示）。 */
  missingCodes?: readonly string[]
  /** 禁用（占位 / 无权）。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  locales: () => [],
  missingCodes: () => [],
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: I18nFilter]
  search: []
  reset: []
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { catalog } = useBaseMessageCatalog()

/** 本地草稿条件（受控：变更即上抛，父件未回写时仍可即时筛选）。 */
const draft = ref<I18nFilter>({ ...props.modelValue })

watch(
  () => props.modelValue,
  (value) => {
    draft.value = { ...value }
  },
  { deep: true },
)

const missingHint = computed(() => props.missingCodes.length > 0)

/**
 * 更新单项条件（先更新本地草稿供即时渲染，再上抛受控值）。
 *
 * @param patchValue 变更条件。
 */
function patch(patchValue: Partial<I18nFilter>): void {
  draft.value = { ...draft.value, ...patchValue }
  emit('update:modelValue', { ...draft.value })
}

/**
 * 关键词回车提交。
 *
 * @param event 键盘事件。
 */
function onKeywordEnter(event: KeyboardEvent): void {
  if ((event.target as HTMLInputElement).value !== undefined) {
    emit('search')
  }
}

/** 清空全部条件。 */
function onReset(): void {
  draft.value = { prefix: '', keyword: '', missingOnly: false, modifiedOnly: false, locale: '' }
  emit('update:modelValue', { ...draft.value })
  emit('reset')
}
</script>

<template>
  <div class="bms-message-filter" data-test="message-filter" :data-source="catalog.identifier">
    <label class="bms-message-filter__item">
      <span>模块前缀</span>
      <input
        type="text"
        data-test="filter-prefix"
        :disabled="disabled"
        :value="draft.prefix"
        placeholder="如 user.form."
        @input="patch({ prefix: ($event.target as HTMLInputElement).value })"
        @keyup.enter="onKeywordEnter"
      />
    </label>

    <label class="bms-message-filter__item">
      <span>关键词</span>
      <input
        type="text"
        data-test="filter-keyword"
        :disabled="disabled"
        :value="draft.keyword"
        placeholder="匹配 key 或任一语言值"
        @input="patch({ keyword: ($event.target as HTMLInputElement).value })"
        @keyup.enter="onKeywordEnter"
      />
    </label>

    <label class="bms-message-filter__item">
      <input
        type="checkbox"
        data-test="filter-missing"
        :disabled="disabled"
        :checked="draft.missingOnly"
        @change="patch({ missingOnly: ($event.target as HTMLInputElement).checked })"
      />
      <span>只看缺失</span>
    </label>
    <span v-if="missingHint" class="bms-message-filter__hint" data-test="filter-missing-hint">
      存在缺失语言：{{ missingCodes.join('、') }}
    </span>

    <label class="bms-message-filter__item">
      <input
        type="checkbox"
        data-test="filter-modified"
        :disabled="disabled"
        :checked="draft.modifiedOnly"
        @change="patch({ modifiedOnly: ($event.target as HTMLInputElement).checked })"
      />
      <span>仅已修改</span>
    </label>

    <label class="bms-message-filter__item">
      <span>语言聚焦</span>
      <select
        data-test="filter-locale"
        :disabled="disabled"
        :value="draft.locale"
        @change="patch({ locale: ($event.target as HTMLSelectElement).value })"
      >
        <option value="">全部语言</option>
        <option v-for="item in locales" :key="item.code" :value="item.code">{{ item.name }}</option>
      </select>
    </label>

    <button type="button" data-test="filter-search" :disabled="disabled" @click="emit('search')">查询</button>
    <button type="button" data-test="filter-reset" :disabled="disabled" @click="onReset">重置</button>

    <slot name="extra" />
  </div>
</template>

<style scoped>
.bms-message-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.bms-message-filter__item {
  display: inline-flex;
  gap: 4px;
  align-items: center;
}

.bms-message-filter__hint {
  color: var(--bms-color-warning);
}
</style>
