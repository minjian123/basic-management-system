<script setup lang="ts">
// 角色分配（权限配置第四页签）：用户分配内建（岗位 / 部门分配由 mdm 插件插入，缺失即隐藏）。
// 变更**随宿主保存**（原型口径：保存只在页面工具栏一处）——页签内只记挂起变更，`save()` 统一提交。
//
// **具名插槽宿主（非路由承载）**：本页签非独立路由（无 `:id` 路由参数），故当前角色标识经
// **显式上下文注入通道**（`ModuleAreaOutlet` 的 `context`，需求 `05-11`）交给区域项插件——
// 宿主页**只声明挂接位与上下文**，不 import 任何具体插件。
import { EmptyState, ModuleAreaOutlet } from '@bms/ui-ep'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import {
  assignRoleUsers,
  listRoleUsers,
  unassignRoleUser,
  type AssignedUserItem,
} from '@/api/role'
import { listUsers, type UserItem } from '@/api/user'
import { registries, registriesRevision } from '@/module/registries'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{
  /** 角色主键。 */
  roleId: string
}>()

/** 具名插槽标识（`{域}.{页面}.{区域}`）：角色表单「角色分配」页签的插件挂接位。 */
const ROLE_ASSIGN_SLOT = 'sys.role.detail.assign'

const session = useSessionStore()

/** 已持有权限码（插槽项按权限显隐；随会话变化刷新）。 */
const permissionCodes = computed(() => session.codes)

/**
 * 具名插槽显式上下文（只读；非路由承载页的作用实体标识经此通道给区域项）。
 *
 * 插件经 `useModuleSlotContext()` / `useModuleSlotField('roleId')` 只读取得；缺失即自行降级（不请求）。
 */
const slotContext = computed<Record<string, unknown>>(() => ({ roleId: props.roleId }))

const emit = defineEmits<{ dirty: [dirty: boolean] }>()

/** 每页条数。 */
const PAGE_SIZE = 10
/** 单次分配上限（与后端批量分配口径一致）。 */
const ASSIGN_LIMIT = 200

/** 已分配用户（服务端）。 */
const assigned = ref<AssignedUserItem[]>([])
/** 已分配总数。 */
const total = ref(0)
/** 当前页。 */
const page = ref(1)
/** 已分配列表关键字。 */
const keyword = ref('')
/** 载入中。 */
const loading = ref(false)
/** 待新增（用户主键 → 展示行）。 */
const pendingAdds = ref<Map<string, UserItem>>(new Map())
/** 待移除（用户主键 → 展示行）。 */
const pendingRemoves = ref<Map<string, AssignedUserItem>>(new Map())
/** 选择用户弹窗可见。 */
const pickerVisible = ref(false)
/** 弹窗关键字。 */
const pickerKeyword = ref('')
/** 弹窗候选用户。 */
const candidates = ref<UserItem[]>([])
/** 弹窗勾选用户主键。 */
const picked = ref<string[]>([])
/** 提交中。 */
const saving = ref(false)

/** 是否存在未提交变更。 */
const dirty = computed(() => pendingAdds.value.size > 0 || pendingRemoves.value.size > 0)

/** 合并待变更后的展示行（待移除已剔除、待新增置顶）。 */
const rows = computed(() => {
  const removes = pendingRemoves.value
  const adds = [...pendingAdds.value.values()].map((item) => ({
    user_id: item.id,
    username: item.username,
    name: item.name,
    status: item.status,
  }))
  return [...adds, ...assigned.value.filter((item) => !removes.has(item.user_id))]
})

watch(dirty, (value) => emit('dirty', value))

/**
 * 载入已分配用户（按关键字与分页）。
 */
async function load(): Promise<void> {
  if (props.roleId === '' || props.roleId === 'new') {
    assigned.value = []
    total.value = 0
    return
  }
  loading.value = true
  try {
    const data = await listRoleUsers(props.roleId, {
      kw: keyword.value || undefined,
      page: page.value,
      size: PAGE_SIZE,
    })
    assigned.value = data.list ?? []
    total.value = data.total ?? 0
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '已分配用户加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 打开「选择用户」弹窗并载入候选（排除已分配 / 待新增 / 停用）。
 */
async function openPicker(): Promise<void> {
  pickerKeyword.value = ''
  picked.value = []
  pickerVisible.value = true
  await loadCandidates()
}

/**
 * 载入弹窗候选用户（仅启用账号）。
 */
async function loadCandidates(): Promise<void> {
  try {
    const data = await listUsers({ kw: pickerKeyword.value || undefined, status: 'enabled', size: 50 })
    candidates.value = data.list ?? []
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '用户列表加载失败')
  }
}

/**
 * 选择用户弹窗确认（登记为待新增，随宿主保存提交）。
 */
function confirmPick(): void {
  const chosenUsername = new Set(assigned.value.map((item) => item.username))
  for (const id of picked.value) {
    const user = candidates.value.find((item) => item.id === id)
    if (user !== undefined && !chosenUsername.has(user.username)) {
      pendingAdds.value.set(id, user)
    }
  }
  pendingAdds.value = new Map(pendingAdds.value)
  pickerVisible.value = false
}

/**
 * 标记移除（随宿主保存提交）；未保存的新增行直接撤回。
 *
 * @param userId 用户主键。
 */
function markRemove(userId: string): void {
  if (pendingAdds.value.has(userId)) {
    pendingAdds.value.delete(userId)
    pendingAdds.value = new Map(pendingAdds.value)
    return
  }
  const item = assigned.value.find((row) => row.user_id === userId)
  if (item !== undefined) {
    pendingRemoves.value.set(userId, item)
    pendingRemoves.value = new Map(pendingRemoves.value)
  }
}

/**
 * 撤销全部挂起变更。
 */
function revert(): void {
  pendingAdds.value = new Map()
  pendingRemoves.value = new Map()
}

/**
 * 提交挂起变更（宿主工具栏「保存」调用）：批量分配 → 解绑 → 重载。
 *
 * @returns 是否提交成功（无变更视为成功）。
 */
async function save(): Promise<boolean> {
  if (pendingAdds.value.size > ASSIGN_LIMIT) {
    ElMessage.error(`单次最多分配 ${ASSIGN_LIMIT} 个用户`)
    return false
  }
  if (!dirty.value) {
    return true
  }
  saving.value = true
  try {
    const addIds = [...pendingAdds.value.keys()]
    if (addIds.length > 0) {
      await assignRoleUsers(props.roleId, { user_ids: addIds })
    }
    for (const userId of pendingRemoves.value.keys()) {
      await unassignRoleUser(props.roleId, userId)
    }
    pendingAdds.value = new Map()
    pendingRemoves.value = new Map()
    await load()
    return true
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '角色分配保存失败')
    return false
  } finally {
    saving.value = false
  }
}

/**
 * 关键字检索（服务端筛选）。
 */
function search(): void {
  page.value = 1
  void load()
}

watch(
  () => props.roleId,
  () => {
    revert()
    page.value = 1
    keyword.value = ''
    void load()
  },
)

onMounted(() => {
  void load()
})

defineExpose({ save, revert })
</script>

<template>
  <div class="role-assign" data-test="role-assign">
    <div class="role-assign__bar">
      <el-input
        v-model="keyword"
        class="role-assign__kw"
        placeholder="账号 / 姓名"
        clearable
        data-test="role-assign-kw"
        @keyup.enter="search"
      />
      <el-button data-test="role-assign-search" @click="search">查询</el-button>
      <el-button type="primary" data-test="role-assign-pick" @click="openPicker">选择用户</el-button>
      <span v-if="loading" class="role-assign__loading" data-test="role-assign-loading">载入中…</span>
      <span class="role-assign__count" data-test="role-assign-count">已分配 {{ rows.length }} 人</span>
    </div>

    <el-table :data="rows" border size="small" data-test="role-assign-table">
      <el-table-column prop="username" label="账号" min-width="140" />
      <el-table-column prop="name" label="姓名" min-width="140" />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
            {{ row.status === 'enabled' ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="danger" :data-test="`role-assign-remove-${row.user_id}`" @click="markRemove(row.user_id)">
            移除
          </el-button>
        </template>
      </el-table-column>
      <template #empty>
        <empty-state type="data" title="尚未分配用户" description="点击「选择用户」批量分配后随页面保存生效。" />
      </template>
    </el-table>

    <div class="role-assign__foot">
      <span v-if="dirty" class="role-assign__dirty" data-test="role-assign-dirty">● 有未保存的分配变更</span>
      <el-pagination
        v-model:current-page="page"
        :page-size="PAGE_SIZE"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="load"
      />
    </div>

    <!-- 具名插槽：岗位 / 部门分配由 mdm 插件插入（缺失 / 未启用 / 无权限即隐藏，不报错、不阻塞本页其余） -->
    <div class="role-assign__slots">
      <module-area-outlet
        :area="ROLE_ASSIGN_SLOT"
        variant="tabs"
        :registries="registries"
        :revision="registriesRevision"
        :permission-codes="permissionCodes"
        :context="slotContext"
      />
    </div>

    <el-dialog v-model="pickerVisible" title="选择用户" width="560" align-center>
      <div class="role-assign__picker">
        <el-input
          v-model="pickerKeyword"
          placeholder="账号 / 姓名"
          clearable
          data-test="role-assign-picker-kw"
          @keyup.enter="loadCandidates"
        />
        <el-button data-test="role-assign-picker-search" @click="loadCandidates">查询</el-button>
      </div>
      <el-table
        :data="candidates"
        border
        size="small"
        data-test="role-assign-picker-table"
        @selection-change="(rows: UserItem[]) => (picked = rows.map((item) => item.id))"
      >
        <el-table-column type="selection" width="46" />
        <el-table-column prop="username" label="账号" min-width="140" />
        <el-table-column prop="name" label="姓名" min-width="140" />
      </el-table>
      <template #footer>
        <el-button @click="pickerVisible = false">取消</el-button>
        <el-button type="primary" data-test="role-assign-picker-confirm" @click="confirmPick">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.role-assign__bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.role-assign__kw {
  width: 200px;
}

.role-assign__loading {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.role-assign__count {
  margin-left: auto;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.role-assign__foot {
  display: flex;
  align-items: center;
  margin-top: var(--bms-space-3);
}

.role-assign__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.role-assign__slots {
  margin-top: var(--bms-space-4);
}

.role-assign__picker {
  display: flex;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}
</style>
