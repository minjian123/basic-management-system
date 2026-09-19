<script setup lang="ts">
// 主体绑定件（08_04_02）：用户 / 岗位 / 部门主体与角色的绑定（勾选即绑定、移除即解绑，超上限拒绝并提示）；候选经选项源基类。
import type { PermissionSubject, PermissionSubjectType } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseOptionSource } from '../../composables/useBaseOptionSource'

/** 候选主体选项值。 */
interface SubjectOption {
  /** 主体标识。 */
  id: string
  /** 主体类型。 */
  type: PermissionSubjectType
}

interface Props {
  /** 已绑主体。 */
  subjects?: PermissionSubject[]
  /** 候选主体。 */
  candidates?: PermissionSubject[]
  /** 是否禁用。 */
  disabled?: boolean
  /** 单主体可绑定角色数上限（`0` 表示不限制）。 */
  limit?: number
  /** 主体类型页签。 */
  types?: PermissionSubjectType[]
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  subjects: () => [],
  candidates: () => [],
  disabled: false,
  limit: 20,
  types: () => ['user', 'position', 'dept'] as PermissionSubjectType[],
  emptyText: '暂无主体绑定',
})

const emit = defineEmits<{
  bind: [subject: PermissionSubject]
  unbind: [payload: { id: string; type: PermissionSubjectType }]
}>()

/** 候选主体选项源（本地候选集经加载器注入）。 */
const source = useBaseOptionSource<SubjectOption>({
  loader: async () => props.candidates.map((item) => ({ value: { id: item.id, type: item.type }, label: item.name })),
})
/** 当前主体类型页签。 */
const activeType = ref<PermissionSubjectType>(props.types[0] ?? 'user')
/** 搜索词。 */
const keyword = ref('')

watch(
  () => props.candidates,
  () => {
    void source.load()
  },
  { immediate: true },
)

/** 候选（按名称搜索 + 当前类型过滤 + 剔除已绑）。 */
const candidateList = computed<PermissionSubject[]>(() => {
  // 依赖选项源响应式面（加载完成后重算；选项源基类的搜索读实例态）
  void source.options.value
  const bound = new Set(props.subjects.map((item) => `${item.type}:${item.id}`))
  return source
    .search(keyword.value)
    .map((item) => props.candidates.find((entry) => entry.id === item.value.id && entry.type === item.value.type))
    .filter((item): item is PermissionSubject => item !== undefined)
    .filter((item) => item.type === activeType.value && !bound.has(`${item.type}:${item.id}`))
})

/** 已绑主体（当前类型）。 */
const boundSubjects = computed(() => props.subjects.filter((item) => item.type === activeType.value))

/** 是否已达上限。 */
const limitReached = computed(() => props.limit > 0 && props.subjects.length >= props.limit)

/** 绑定主体。 */
function bind(subject: PermissionSubject): void {
  emit('bind', subject)
}

/** 解绑主体。 */
function unbind(subject: PermissionSubject): void {
  emit('unbind', { id: subject.id, type: subject.type })
}
</script>

<template>
  <div class="bms-subject-binding" data-test="subject-binding" :data-disabled="disabled || undefined">
    <div class="bms-subject-binding__tabs" data-test="subject-tabs">
      <button
        v-for="type in types"
        :key="type"
        type="button"
        :data-test="`subject-tab-${type}`"
        :data-active="type === activeType || undefined"
        @click="activeType = type"
      >
        {{ type }}
      </button>
    </div>

    <div class="bms-subject-binding__search">
      <input
        v-model="keyword"
        type="search"
        data-test="subject-search"
        placeholder="搜索主体名称"
        :disabled="disabled"
      />
      <span data-test="subject-count">{{ subjects.length }} / {{ limit > 0 ? limit : '不限' }}</span>
      <span v-if="limitReached" data-test="subject-limit">已达单主体上限</span>
    </div>

    <p v-if="boundSubjects.length === 0" data-test="empty">{{ emptyText }}</p>

    <ul class="bms-subject-binding__bound" data-test="subject-bound">
      <li v-for="subject in boundSubjects" :key="`${subject.type}:${subject.id}`" :data-type="subject.type">
        <span :data-test="`subject-${subject.id}`">{{ subject.name }}</span>
        <button type="button" data-test="subject-unbind" :disabled="disabled" @click="unbind(subject)">移除</button>
      </li>
    </ul>

    <ul class="bms-subject-binding__candidates" data-test="subject-candidates">
      <li
        v-for="subject in candidateList"
        :key="`${subject.type}:${subject.id}`"
        :data-test="`candidate-${subject.id}`"
      >
        <button type="button" :disabled="disabled || limitReached" @click="bind(subject)">绑定</button>
        <span>{{ subject.name }}</span>
      </li>
    </ul>
  </div>
</template>
