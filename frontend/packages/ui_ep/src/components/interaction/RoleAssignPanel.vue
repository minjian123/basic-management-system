<script setup lang="ts">
// 角色分配件（08-4-4，新口径）：用户分配——已分配列表 + 「选择用户」多选弹窗 + 移除 + 计数；不设上限。
// 样式（11-01）：弹窗改 el-dialog、按钮与输入改组件库件，补 <style scoped> 消费 --bms-* 令牌。
import type { AssignedUser } from '@bms/core'
import { ElButton, ElCheckbox, ElDialog, ElInput } from 'element-plus'
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
function toggle(id: string, value: boolean | string | number): void {
  const next = new Set(picked.value)
  if (value === true) {
    next.add(id)
  } else {
    next.delete(id)
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
      <el-button data-test="role-assign-open" size="small" type="primary" :disabled="disabled" @click="open">
        选择用户
      </el-button>
      <span class="bms-role-assign__count" data-test="role-assign-count">已分配 {{ count }}</span>
    </div>

    <p v-if="users.length === 0" class="bms-role-assign__empty" data-test="empty">{{ emptyText }}</p>

    <ul class="bms-role-assign__list" data-test="role-assign-list">
      <li v-for="user in users" :key="user.id" class="bms-role-assign__item" :data-test="`assigned-${user.id}`">
        <span class="bms-role-assign__name">{{ user.name }}</span>
        <small class="bms-role-assign__username">{{ user.username }}</small>
        <span v-if="user.status !== 'enabled'" class="bms-role-assign__disabled" data-test="assigned-disabled">停用</span>
        <el-button
          class="bms-role-assign__unbind"
          data-test="role-assign-unbind"
          link
          type="danger"
          size="small"
          :disabled="disabled"
          @click="emit('unbind', { id: user.id })"
        >
          移除
        </el-button>
      </li>
    </ul>

    <el-dialog
      v-model="dialogOpen"
      class="bms-role-assign__dialog"
      data-test="role-assign-dialog"
      title="选择用户"
      width="520px"
      append-to-body
    >
      <div class="bms-role-assign__dialog-head">
        <el-input
          v-model="keyword"
          data-test="role-assign-search"
          placeholder="搜索账号 / 姓名"
          size="small"
          clearable
          @input="emit('search', keyword)"
        />
      </div>
      <p v-if="loading" class="bms-role-assign__loading" data-test="role-assign-loading">加载中…</p>
      <div class="bms-role-assign__candidates">
        <label v-for="user in available" :key="user.id" class="bms-role-assign__candidate" :data-test="`candidate-${user.id}`">
          <el-checkbox :model-value="picked.has(user.id)" @update:model-value="(value) => toggle(user.id, value)">
            <span class="bms-role-assign__name">{{ user.name }}</span>
            <small class="bms-role-assign__username">{{ user.username }}</small>
          </el-checkbox>
        </label>
        <p v-if="available.length === 0" class="bms-role-assign__empty">暂无可选用户</p>
      </div>
      <template #footer>
        <el-button data-test="role-assign-cancel" @click="dialogOpen = false">取消</el-button>
        <el-button data-test="role-assign-confirm" type="primary" :disabled="picked.size === 0" @click="confirm">
          确定
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.bms-role-assign {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
  min-width: 0;
}

.bms-role-assign__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
}

.bms-role-assign__count {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.bms-role-assign__empty {
  margin: 0;
  padding: var(--bms-space-6) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}

.bms-role-assign__list {
  margin: 0;
  padding: 0;
  list-style: none;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-role-assign__item {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  padding: var(--bms-space-2) var(--bms-space-3);
  border-bottom: 1px solid var(--bms-color-border);
  font-size: var(--bms-font-size-sm);
}

.bms-role-assign__item:last-child {
  border-bottom: none;
}

.bms-role-assign__name {
  color: var(--bms-color-text);
}

.bms-role-assign__username {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.bms-role-assign__disabled {
  padding: 0 var(--bms-space-1);
  color: var(--bms-perm-detached-color);
  font-size: var(--bms-font-size-xs);
  background: var(--bms-color-warning-bg);
  border-radius: var(--bms-radius-sm);
}

.bms-role-assign__unbind {
  margin-left: auto;
}

.bms-role-assign__dialog-head {
  margin-bottom: var(--bms-space-3);
}

.bms-role-assign__loading {
  margin: 0 0 var(--bms-space-2);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.bms-role-assign__candidates {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
  max-height: 320px;
  overflow: auto;
}

.bms-role-assign__candidate {
  display: flex;
  align-items: center;
  min-height: var(--bms-control-height);
  padding: 0 var(--bms-space-2);
  border-radius: var(--bms-radius-sm);
}

.bms-role-assign__candidate:hover {
  background: var(--bms-color-fill);
}
</style>
