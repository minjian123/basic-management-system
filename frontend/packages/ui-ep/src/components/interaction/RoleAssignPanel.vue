<script setup lang="ts">
// 角色分配件（08-4-4，新口径）：用户分配——已分配列表 + 「选择用户」多选弹窗 + 移除 + 计数；不设上限。
import type { AssignedUser } from '@bms/core'
import { computed, ref } from 'vue'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'

interface Props {
  /** 已分配用户。 */
  users?: AssignedUser[]
  /** 选择用户弹窗候选。 */
  candidates?: AssignedUser[]
  /** 是否禁用。 */
  disabled?: boolean
  /** 候选加载态。 */
  loading?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  users: () => [],
  candidates: () => [],
  disabled: false,
  loading: false,
  emptyText: '暂无已分配用户',
})

const emit = defineEmits<{
  bind: [users: AssignedUser[]]
  unbind: [payload: { id: string }]
  search: [keyword: string]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
useBasePermissionConfig()

/** 弹窗开关。 */
const dialogOpen = ref(false)
/** 弹窗关键词。 */
const keyword = ref('')
/** 弹窗内勾选用户 id。 */
const picked = ref<Set<string>>(new Set())

/** 已分配计数。 */
const count = computed(() => props.users.length)

/** 弹窗候选（剔除已分配）。 */
const available = computed(() => props.candidates.filter((user) => !props.users.some((item) => item.id === user.id)))

/** 打开弹窗。 */
function open(): void {
  picked.value = new Set()
  keyword.value = ''
  dialogOpen.value = true
  emit('search', '')
}

/** 切换勾选。 */
function toggle(id: string): void {
  const next = new Set(picked.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  picked.value = next
}

/** 确认分配。 */
function confirm(): void {
  const chosen = props.candidates.filter((user) => picked.value.has(user.id))
  if (chosen.length > 0) {
    emit('bind', chosen)
  }
  dialogOpen.value = false
}
</script>

<template>
  <div class="bms-role-assign" data-test="role-assign" :data-disabled="disabled || undefined">
    <div class="bms-role-assign__toolbar">
      <button type="button" data-test="role-assign-open" :disabled="disabled" @click="open">选择用户</button>
      <span data-test="role-assign-count">已分配 {{ count }}</span>
    </div>

    <p v-if="users.length === 0" data-test="empty">{{ emptyText }}</p>

    <ul class="bms-role-assign__list" data-test="role-assign-list">
      <li v-for="user in users" :key="user.id" :data-test="`assigned-${user.id}`">
        <span>{{ user.name }}</span>
        <small>{{ user.username }}</small>
        <em v-if="user.status !== 'enabled'" data-test="assigned-disabled">停用</em>
        <button type="button" data-test="role-assign-unbind" :disabled="disabled" @click="emit('unbind', { id: user.id })">
          移除
        </button>
      </li>
    </ul>

    <div v-if="dialogOpen" class="bms-role-assign__dialog" data-test="role-assign-dialog" role="dialog">
      <header>
        <strong>选择用户</strong>
        <input
          v-model="keyword"
          type="search"
          data-test="role-assign-search"
          placeholder="搜索账号 / 姓名"
          @input="emit('search', keyword)"
        />
      </header>
      <p v-if="loading" data-test="role-assign-loading">加载中…</p>
      <label v-for="user in available" :key="user.id" :data-test="`candidate-${user.id}`">
        <input type="checkbox" :checked="picked.has(user.id)" @change="toggle(user.id)" />
        <span>{{ user.name }}</span>
        <small>{{ user.username }}</small>
      </label>
      <footer>
        <button type="button" data-test="role-assign-cancel" @click="dialogOpen = false">取消</button>
        <button type="button" data-test="role-assign-confirm" :disabled="picked.size === 0" @click="confirm">确定</button>
      </footer>
    </div>
  </div>
</template>
