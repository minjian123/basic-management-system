<script setup lang="ts">
// 权限配置容器（08-4-4，新口径）：消费 ui-ep 授权总容器件（菜单 / 表单 / 数据三页签经 jobs 落 platform 授权接口）。
// 「角色分配」页签沿用宿主内建 RoleAssignTab（用户分配 + mdm 岗位 / 部门分配插件挂接位），经容器 `assign-panel` 插槽覆写。
import { BaseAccess, type DataScopePolicyItem, type PermissionJobs } from '@bms/core'
import { PermissionConfig } from '@bms/ui-ep'
import { computed, ref, watch } from 'vue'

import {
  assignRoleUsers,
  getRoleDataScopes,
  getRoleFields,
  getRolePermissions,
  listRoleUsers,
  replaceRoleDataScopes,
  replaceRoleFields,
  replaceRolePermissions,
  unassignRoleUser,
} from '@/api/role'
import { fetchPermissionMetadata } from '@/api/permissionMeta'
import { fetchMyMenus } from '@/api/menu'
import { useSessionStore } from '@/stores/session'
import RoleAssignTab from './RoleAssignTab.vue'

const props = defineProps<{
  /** 角色主键。 */
  roleId: string
}>()

const emit = defineEmits<{ dirty: [dirty: boolean] }>()

const session = useSessionStore()

/** 授权写权限码上下文（未注入权限码时视为有权，后端兜底）。 */
class PermissionAccess extends BaseAccess {}
const access = new PermissionAccess()
access.setCodes(session.codes)
watch(
  () => session.codes,
  (codes) => access.setCodes(codes),
)

/** 授权总容器件引用。 */
const configRef = ref<InstanceType<typeof PermissionConfig> | null>(null)
/** 角色分配页签引用。 */
const assignRef = ref<InstanceType<typeof RoleAssignTab> | null>(null)
/** 权限配置区脏态。 */
const configDirty = ref(false)
/** 角色分配页签脏态。 */
const assignDirty = ref(false)

watch([configDirty, assignDirty], ([left, right]) => emit('dirty', left || right))

/** 当前角色主键（字符串口径）。 */
const currentId = computed(() => props.roleId)

/** 占位文案：新增（未保存）角色提示先保存再配置；其余场景用组件默认文案。 */
const degradeText = computed(() =>
  props.roleId === 'new' ? '新增角色尚未保存，保存后即可配置权限' : undefined,
)

/** 注入的数据通路（元数据 + 三类授权 + 用户差量 + 取码）。 */
const jobs: PermissionJobs = {
  loadMetadata: fetchPermissionMetadata,
  loadGrants: async ({ roleId }) => {
    const id = String(roleId ?? currentId.value)
    const [permissions, fields, scopes, users] = await Promise.all([
      getRolePermissions(id),
      getRoleFields(id),
      getRoleDataScopes(id),
      listRoleUsers(id, { page: 1, size: 200 }),
    ])
    return {
      roleId: id,
      entries: (permissions.items ?? []).map((entry) => ({
        permType: entry.perm_type as 'menu' | 'form' | 'action',
        targetId: String(entry.target_id),
        sourceMenuId: String(entry.source_menu_id ?? '0'),
      })),
      fieldEntries: (fields.items ?? []).map((entry) => ({
        formId: String(entry.form_id),
        fieldId: String(entry.field_id),
        visible: entry.visible,
        editable: entry.editable,
        sourceMenuId: String(entry.source_menu_id ?? '0'),
      })),
      dataScopeEntries: (scopes.items ?? []).map((entry) => ({
        dictTypeId: String(entry.dict_type_id),
        policyType: entry.policy_type as 'select' | 'region' | 'match' | 'extension',
        config: (entry.config ?? []).map((item) => ({ ...item })) as unknown as DataScopePolicyItem[],
      })),
      users: (users.list ?? []).map((user) => ({
        id: String(user.user_id),
        username: user.username,
        name: user.name,
        status: user.status,
      })),
    }
  },
  submitPermissions: async ({ roleId, payload }) => {
    const result = await replaceRolePermissions(String(roleId ?? currentId.value), {
      entries: payload.entries.map((entry) => ({
        perm_type: entry.permType,
        target_id: entry.targetId,
        source_menu_id: entry.sourceMenuId,
      })),
    })
    return { version: result.items?.length }
  },
  submitFields: async ({ roleId, payload }) => {
    await replaceRoleFields(String(roleId ?? currentId.value), {
      entries: payload.entries.map((entry) => ({
        form_id: entry.formId,
        field_id: entry.fieldId,
        visible: entry.visible,
        editable: entry.editable,
        source_menu_id: entry.sourceMenuId,
      })),
    })
    return {}
  },
  submitDataScopes: async ({ roleId, payload }) => {
    await replaceRoleDataScopes(String(roleId ?? currentId.value), {
      entries: payload.entries.map((entry) => ({
        dict_type_id: entry.dictTypeId,
        policy_type: entry.policyType,
        config: entry.config as unknown as Record<string, unknown>[],
      })),
    })
    return {}
  },
  saveUsers: async ({ roleId, added, removed }) => {
    const id = String(roleId ?? currentId.value)
    if (added.length > 0) {
      await assignRoleUsers(id, { user_ids: [...added] })
    }
    for (const userId of removed) {
      await unassignRoleUser(id, userId)
    }
    return {}
  },
  loadPermissionCodes: async () => {
    const data = await fetchMyMenus()
    return data.permissions ?? []
  },
}

/**
 * 提交授权（记录页工具栏「保存」调用）：授权总容器件三类接口（菜单 / 字段 / 数据权限）。
 *
 * 「角色分配」页签（用户分配 + mdm 岗位 / 部门插件）的草稿**不在此提交**——由记录页统一经
 * 角色保存编排端点（`PUT /roles/{id}/assignments`）与角色本体一次原子提交（见 `02_03/_02` 详设）。
 *
 * @returns 是否提交成功。
 */
async function save(): Promise<boolean> {
  const configured = await configRef.value?.save()
  return configured !== undefined
}

/**
 * 收集「角色分配」页签的插件草稿分段（记录页编排用）。
 *
 * @returns 分段名 → 段值（无改动 / 无插件的段不出现）。
 */
function buildAssignSegments(): Record<string, Record<string, unknown>> {
  return assignRef.value?.buildSegments() ?? {}
}

/** 「角色分配」页签是否存在未提交草稿。 */
function isAssignDirty(): boolean {
  return assignRef.value?.isDirty() ?? false
}

/** 授权总容器件（菜单 / 字段 / 数据权限）是否存在未提交变更。 */
function isConfigDirty(): boolean {
  return configDirty.value
}

/**
 * 撤销未保存变更（授权总容器丢弃 + 角色分配草稿复位）。
 */
function revert(): void {
  configRef.value?.discard()
  void assignRef.value?.revert()
}

defineExpose({ save, buildAssignSegments, isAssignDirty, isConfigDirty, revert })
</script>

<template>
  <div class="role-perm" data-test="role-permission-config">
    <permission-config
      ref="configRef"
      :ready="props.roleId !== '' && props.roleId !== 'new'"
      :role-id="props.roleId"
      :jobs="jobs"
      :access="access"
      :degrade-text="degradeText"
      @dirty="(value: boolean) => (configDirty = value)"
    >
      <!-- 角色分配页签：宿主内建（用户分配 + mdm 岗位 / 部门分配插件挂接位） -->
      <template #assign-panel>
        <role-assign-tab
          ref="assignRef"
          :role-id="props.roleId"
          @dirty="(value: boolean) => (assignDirty = value)"
        />
      </template>
    </permission-config>
  </div>
</template>

<style scoped>
.role-perm {
  min-height: 320px;
}
</style>
