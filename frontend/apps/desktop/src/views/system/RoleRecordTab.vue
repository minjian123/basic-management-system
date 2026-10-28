<script setup lang="ts">
// 角色记录 Tab（表单框架的记录页）：经字典记录页骨架件对齐《布局设计 · 字典页》——
// 工具栏 + 信息栏（详细信息 / 权限配置 / 系统信息，业务 Tab 插在固定两 Tab 之间）；
// 详细信息首行固定三字段（角色码 / 角色名 / 状态，三列等宽），其余字段排首行之后；
// 工具栏**单一保存**：详细信息页签保存基本信息，权限配置页签保存授权（角色分配随宿主保存）。
import { DictRecordLayout, type SysInfoData } from '@bms/ui_ep'
import { ElMessage } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import {
  applyRoleAssignments,
  createRole,
  getRole,
  updateRole,
  type RoleAssignmentsPayload,
  type RoleDetail,
  type RoleStatus,
} from '@/api/role'

import RolePermissionConfig from './role/RolePermissionConfig.vue'
import { roleTypeLabel } from './role/labels'

const props = defineProps<{
  /** 角色主键（新增态为 `new`）。 */
  roleId: string
}>()

const emit = defineEmits<{ saved: [role: RoleDetail]; dirty: [dirty: boolean]; close: [] }>()

/** 新增态标识（记录页签键 `record:new`）。 */
const NEW_KEY = 'new'

/** 当前子页签（骨架件受控键：`detail` / `permission` / `sys`）。 */
const section = ref<string>('detail')
/** 是否新增态。 */
const isNew = computed(() => props.roleId === NEW_KEY)
/** 是否编辑态（查看 ⇄ 编辑分态）。 */
const editing = ref(false)
/** 角色详情（查看态数据源）。 */
const detail = ref<RoleDetail | null>(null)
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 表单（角色码可改；角色类型只读展示、不入表单）。 */
const form = ref<{ code: string; name: string; status: RoleStatus; version: number }>({
  code: '',
  name: '',
  status: 'enabled',
  version: 1,
})
/** 权限配置页签脏态（授权未保存变更）。 */
const permissionDirty = ref(false)
/** 基本信息脏态。 */
const detailDirty = ref(false)
/** 载入时的基本信息基线（用于判定「基本信息是否真的改过」）。 */
const baseline = ref<{ code: string; name: string; status: RoleStatus }>({
  code: '',
  name: '',
  status: 'enabled',
})
/** 权限配置容器引用（工具栏保存分派）。 */
const permissionRef = ref<InstanceType<typeof RolePermissionConfig> | null>(null)

/** 是否内置角色（不可删除 / 停用；角色码与名称可改）。 */
const builtin = computed(() => detail.value?.builtin === true)
/** 角色类型文案（只读展示；新增态恒为自定义）。 */
const roleTypeText = computed(() => roleTypeLabel(isNew.value ? 'custom' : detail.value?.role_type))
/** 是否存在未保存变更（任一子页签）。 */
const dirty = computed(() => detailDirty.value || permissionDirty.value)
/** 系统信息（记录页「系统信息」子页签数据）。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: detail.value?.version ?? null,
  createdBy: detail.value?.created_by ?? null,
  createdAt: detail.value?.created_at ?? null,
  updatedBy: detail.value?.updated_by ?? null,
  updatedAt: detail.value?.updated_at ?? null,
  formKey: 'role',
  formLabel: '角色管理',
}))

watch(dirty, (value) => emit('dirty', value))

// 基本信息改动判定：与载入基线逐字段比对（避免「载入即脏」的误判）
watch(
  form,
  () => {
    if (!editing.value || isNew.value) {
      detailDirty.value = false
      return
    }
    const b = baseline.value
    detailDirty.value =
      form.value.code !== b.code || form.value.name !== b.name || form.value.status !== b.status
  },
  { deep: true },
)

/**
 * 归一角色状态（详情契约 `status` 为 string，写接口要求 `enabled` / `disabled`）。
 *
 * @param value 原始状态。
 */
function toStatus(value: string | undefined): RoleStatus {
  return value === 'disabled' ? 'disabled' : 'enabled'
}

/**
 * 载入角色详情（新增态直接进编辑态）。
 */
async function load(): Promise<void> {
  if (isNew.value) {
    editing.value = true
    detail.value = null
    form.value = { code: '', name: '', status: 'enabled', version: 1 }
    baseline.value = { code: '', name: '', status: 'enabled' }
    detailDirty.value = false
    return
  }
  loading.value = true
  try {
    const data = await getRole(props.roleId)
    detail.value = data
    form.value = {
      code: data.code ?? '',
      name: data.name ?? '',
      status: toStatus(data.status),
      version: data.version ?? 1,
    }
    baseline.value = {
      code: form.value.code,
      name: form.value.name,
      status: form.value.status,
    }
    editing.value = false
    detailDirty.value = false
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '角色详情加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 切换编辑态（查看 → 编辑按详情回填）。
 */
function toggleEditing(): void {
  if (editing.value) {
    form.value = {
      code: detail.value?.code ?? '',
      name: detail.value?.name ?? '',
      status: toStatus(detail.value?.status),
      version: detail.value?.version ?? 1,
    }
    editing.value = false
    detailDirty.value = false
    return
  }
  editing.value = true
}

/**
 * 组装角色分配编排载荷（草稿段；`null` = 不参与）。
 *
 * @param hasRole 角色本体是否参与（乐观锁版本随附）。
 */
function buildAssignmentsPayload(hasRole: boolean): RoleAssignmentsPayload {
  const segments = permissionRef.value?.buildAssignSegments() ?? {}
  const userIds = segments.user_ids?.user_ids as string[] | undefined
  const postIds = segments.role_posts?.post_ids as string[] | undefined
  const deptIds = segments.role_depts?.dept_ids as string[] | undefined
  return {
    role: hasRole
      ? { code: form.value.code, name: form.value.name, status: form.value.status, version: form.value.version }
      : null,
    user_ids: userIds !== undefined ? userIds : null,
    role_posts: postIds !== undefined ? { post_ids: postIds } : null,
    role_depts: deptIds !== undefined ? { dept_ids: deptIds } : null,
  }
}

/**
 * 提交保存（工具栏唯一入口，全局一次保存）。
 *
 * 角色本体 + 「角色分配」页签（用户分配 + 产品插件的岗位 / 部门插件草稿）经**角色保存编排端点**
 * 一次原子提交（`PUT /roles/{id}/assignments`）；仅本体改动时走既有 `PUT /roles/{id}`；
 * 授权（菜单 / 字段 / 数据权限）各自既有端点单独提交（见 `02_03/_02` 详设 §6.3）。
 */
async function save(): Promise<void> {
  if (isNew.value) {
    saving.value = true
    try {
      const created = await createRole({ code: form.value.code, name: form.value.name, status: form.value.status })
      detail.value = created
      form.value.version = created.version ?? 1
      detailDirty.value = false
      emit('saved', created)
      ElMessage.success('角色已创建')
    } catch (error: unknown) {
      ElMessage.error(error instanceof Error ? error.message : '保存失败')
    } finally {
      saving.value = false
    }
    return
  }

  const segments = permissionRef.value?.buildAssignSegments() ?? {}
  const hasAssignments = Object.keys(segments).length > 0
  const configDirty = permissionRef.value?.isConfigDirty() ?? false
  const roleChanged = detailDirty.value
  if (!hasAssignments && !configDirty && !roleChanged) {
    editing.value = false
    return
  }

  saving.value = true
  try {
    if (hasAssignments) {
      const result = await applyRoleAssignments(props.roleId, buildAssignmentsPayload(roleChanged))
      detail.value = result.role
      form.value.version = result.role.version ?? form.value.version
    } else if (roleChanged) {
      await updateRole(props.roleId, {
        code: form.value.code,
        name: form.value.name,
        status: form.value.status,
        version: form.value.version,
      })
    }
    if (configDirty) {
      await permissionRef.value?.save()
    }
    await load()
    permissionRef.value?.revert()
    detailDirty.value = false
    permissionDirty.value = false
    editing.value = false
    emit('saved', detail.value as RoleDetail)
    ElMessage.success('角色已保存')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 撤销未保存变更（授权 / 角色分配草稿与基本信息按需复位）。
 */
function revert(): void {
  if (permissionDirty.value) {
    permissionRef.value?.revert()
    permissionDirty.value = false
  }
  if (detailDirty.value) {
    toggleEditing()
  }
}

watch(
  () => props.roleId,
  () => {
    void load()
  },
)

onMounted(() => {
  void load()
})

defineExpose({ save, isDirty: (): boolean => dirty.value })
</script>

<template>
  <div data-test="role-record">
    <dict-record-layout v-model="section" :info="sysInfo" :disabled="!editing">
      <template #toolbar>
        <el-button v-if="isNew" type="primary" :loading="saving" data-test="role-record-save" @click="save">
          保存
        </el-button>
        <template v-else>
          <el-button
            v-if="editing || dirty"
            type="primary"
            :loading="saving"
            data-test="role-record-save"
            @click="save"
          >
            保存
          </el-button>
          <el-button v-if="dirty" data-test="role-record-revert" @click="revert">撤销</el-button>
          <el-button v-else-if="!editing" data-test="role-record-edit" @click="toggleEditing">编辑</el-button>
        </template>
        <el-button data-test="role-record-close" @click="emit('close')">关闭</el-button>
        <span class="role-record__side">
          <span v-if="loading" class="role-record__hint" data-test="role-record-loading">载入中…</span>
          <span v-if="dirty" class="role-record__dirty" data-test="role-record-dirty">● 有未保存变更</span>
          <span v-else-if="builtin" class="role-record__hint" data-test="role-record-builtin">
            内置角色：不可删除 / 停用 / 变更类型（角色码与名称可改）
          </span>
        </span>
      </template>

      <template #first-row>
        <el-col :span="8">
          <el-form-item label="角色码" required>
            <el-input v-model="form.code" placeholder="角色码（租户内唯一，可修改）" data-test="role-record-code" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="角色名" required>
            <el-input v-model="form.name" data-test="role-record-name" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="状态">
            <el-select v-model="form.status" :disabled="builtin" data-test="role-record-status">
              <el-option label="启用" value="enabled" />
              <el-option label="停用" value="disabled" />
            </el-select>
          </el-form-item>
        </el-col>
      </template>

      <template #fields>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="角色类型">
              <el-input :model-value="roleTypeText" disabled data-test="role-record-type" />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <template #extra-tabs>
        <el-tab-pane label="权限配置" name="permission">
          <role-permission-config
            ref="permissionRef"
            :role-id="isNew ? 'new' : props.roleId"
            @dirty="(value: boolean) => (permissionDirty = value)"
          />
        </el-tab-pane>
      </template>
    </dict-record-layout>
  </div>
</template>

<style scoped>
.role-record__side {
  margin-left: auto;
}

.role-record__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.role-record__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}
</style>
