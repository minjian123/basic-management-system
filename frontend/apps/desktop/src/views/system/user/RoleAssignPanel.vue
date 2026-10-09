<script setup lang="ts">
// 平台内建区域项「角色分配」（挂 `sys.user.detail.tabs`，与 mdm 岗位 / 部门插件同槽并列）。
//
// 宿主记录页「用户分配」页签内的第一个子页签；改动**只进草稿**，由宿主工具栏「保存」经
// 用户保存编排端点（`PUT /users/{id}/assignments`）与本体一次原子提交（见 `02_02/_01` 详设）。
// 无宿主通道（如阶段五样例宿主页）时**只读**，避免绕过编排直写关系表。
import { EmptyState, useModuleSlotField, type HostSubmitterRegistrar } from '@bms/ui-ep'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import { listRoles, type RoleItem } from '@/api/role'
import { listUserRoles, type UserRoleItem } from '@/api/user'
import { useSessionStore } from '@/stores/session'

import { roleTypeLabel } from '../role/labels'

/** 本区域项承担的分段名（与编排端点 `role_ids` 字段对应）。 */
const SEGMENT_KEY = 'role_ids'

const session = useSessionStore()

/** 作用实体标识（宿主记录页显式注入）。 */
const userId = useModuleSlotField<string>('userId')
/** 宿主提交器注册通道（值即函数；缺失 ⇒ 只读）。 */
const registrar = useModuleSlotField<HostSubmitterRegistrar>('registerSubmitter')

/** 已分配（服务端口径）。 */
const assigned = ref<UserRoleItem[]>([])
/** 草稿勾选集合。 */
const picked = ref<string[]>([])
/** 候选角色。 */
const candidates = ref<RoleItem[]>([])
/** 载入中。 */
const loading = ref(false)
/** 弹窗可见。 */
const pickerVisible = ref(false)
/** 弹窗关键字。 */
const keyword = ref('')

/** 是否可写（需宿主通道与 `user:assign_role` 权限码）。 */
const writable = computed(() => registrar.value !== undefined && session.codes.includes('user:assign_role'))
/** 是否存在未提交改动（集合差异）。 */
const dirty = computed(() => {
  const saved = assigned.value.map((item) => String(item.role_id))
  return saved.length !== picked.value.length || saved.some((id) => !picked.value.includes(id))
})

/**
 * 载入已分配角色（上下文缺失即短路，不请求）。
 */
async function load(): Promise<void> {
  const id = userId.value
  if (id === undefined || id === '') {
    return
  }
  loading.value = true
  try {
    const data = await listUserRoles(id)
    assigned.value = data.items ?? []
    picked.value = assigned.value.map((item) => String(item.role_id))
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '已分配角色加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 载入候选角色（已启用）。
 */
async function loadCandidates(): Promise<void> {
  try {
    const data = await listRoles({ status: 'enabled', size: 200 })
    candidates.value = data.list ?? []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '角色列表加载失败')
  }
}

/** 打开选择角色弹窗。 */
function openPicker(): void {
  keyword.value = ''
  pickerVisible.value = true
  void loadCandidates()
}

/** 弹窗内勾选变化（只改草稿）。 */
function onPickChange(ids: (string | number | boolean)[]): void {
  picked.value = ids.map((id) => String(id))
}

/** 关闭弹窗（草稿保留）。 */
function closePicker(): void {
  pickerVisible.value = false
}

/** 弹窗候选（按关键字过滤）。 */
const filteredCandidates = computed<RoleItem[]>(() => {
  const key = keyword.value.trim().toLowerCase()
  if (key === '') {
    return candidates.value
  }
  return candidates.value.filter((item) => `${item.code ?? ''}${item.name ?? ''}`.toLowerCase().includes(key))
})

// 宿主收草稿：登记提交器（无改动返回 null）
watch(
  registrar,
  (target) => {
    target?.({
      isDirty: () => dirty.value,
      buildSegment: () => (dirty.value ? { key: SEGMENT_KEY, value: { role_ids: [...picked.value] } } : null),
      reload: load,
    })
  },
  { immediate: true },
)

watch(userId, () => {
  void load()
})

onMounted(() => {
  void load()
})
</script>

<template>
  <div class="user-role-assign" data-test="user-role-assign">
    <empty-state
      v-if="userId === undefined || userId === ''"
      type="data"
      title="尚未选择用户"
      description="用户创建 / 打开记录后可分配角色。"
      data-test="user-role-context-absent"
    />

    <template v-else>
      <div class="user-role-assign__bar">
        <el-button
          v-if="writable"
          type="primary"
          size="small"
          data-test="user-role-open"
          @click="openPicker"
        >
          选择角色
        </el-button>
        <span class="user-role-assign__hint">
          与角色管理页「角色分配 — 用户分配」同一张关系表（`sys_user_role`）；改动随工具栏「保存」提交
        </span>
        <span class="user-role-assign__count" data-test="user-role-count">已分配 {{ picked.length }}</span>
      </div>

      <p v-if="!writable" class="user-role-assign__hint" data-test="user-role-readonly">
        只读：需具备 `user:assign_role` 权限码且在记录页内打开。
      </p>
      <p v-if="loading" class="user-role-assign__hint" data-test="user-role-loading">载入中…</p>
      <p v-if="dirty" class="user-role-assign__dirty" data-test="user-role-dirty">● 有未保存的角色分配变更</p>

      <el-table :data="assigned" border size="small" data-test="user-role-table">
        <el-table-column prop="role_name" label="角色名称" min-width="160" />
        <el-table-column prop="role_code" label="角色码" min-width="140" />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">{{ roleTypeLabel(row.role_type) }}</template>
        </el-table-column>
        <template #empty>
          <empty-state type="data" title="暂未分配角色" description="点击「选择角色」后随工具栏「保存」生效。" />
        </template>
      </el-table>

      <el-dialog v-model="pickerVisible" title="选择角色" width="520" align-center>
        <el-input
          v-model="keyword"
          placeholder="搜索角色码 / 名称"
          clearable
          data-test="user-role-picker-kw"
        />
        <el-checkbox-group
          :model-value="picked"
          class="user-role-assign__picker"
          data-test="user-role-picker"
          @change="onPickChange"
        >
          <el-checkbox
            v-for="item in filteredCandidates"
            :key="String(item.id)"
            :value="String(item.id)"
            :data-test="`user-role-candidate-${item.id}`"
          >
            {{ item.name }}（{{ item.code }}）
          </el-checkbox>
        </el-checkbox-group>
        <template #footer>
          <el-button data-test="user-role-picker-cancel" @click="closePicker">取消</el-button>
          <el-button type="primary" data-test="user-role-picker-confirm" @click="closePicker">确定</el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<style scoped>
.user-role-assign__bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-2);
}

.user-role-assign__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.user-role-assign__count {
  margin-left: auto;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.user-role-assign__dirty {
  margin: 0 0 var(--bms-space-2);
  color: var(--bms-color-warning);
  font-size: var(--bms-font-size-sm);
}

.user-role-assign__picker {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  margin-top: var(--bms-space-2);
  overflow: auto;
}
</style>
