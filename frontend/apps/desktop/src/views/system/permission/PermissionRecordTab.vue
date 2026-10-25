<script setup lang="ts">
// 权限码记录页签：两子页签「详细信息 / 系统信息」。
// 组合创建后只读（换绑 = 删除重建）：新增用业务码 × 动作码下拉派生组合；编辑仅允许改状态。
defineOptions({ name: 'PermissionRecordTab' })

import { DictRecordLayout, type SysInfoData } from '@bms/ui_ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import type { MetaStatus } from '@/api/menuMeta'
import { createPermission, deletePermission, updatePermission, type PermissionItem } from '@/api/permission'
import { useMenuMetaStore } from '@/stores/menuMeta'

const props = defineProps<{
  /** 权限码主键（新增态为 `new`）。 */
  permissionId: string
}>()

const emit = defineEmits<{
  /** 保存成功。 */
  saved: [item: PermissionItem]
  /** 删除成功。 */
  removed: []
  /** 脏态同步。 */
  dirty: [dirty: boolean]
  /** 请求关闭。 */
  close: []
}>()

/** 新增态标识。 */
const NEW_KEY = 'new'

const meta = useMenuMetaStore()

/** 当前子页签。 */
const section = ref('detail')
/** 是否新增态。 */
const isNew = computed(() => props.permissionId === NEW_KEY)
/** 是否编辑态。 */
const editing = ref(false)
/** 权限码详情。 */
const detail = ref<PermissionItem | null>(null)
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 业务码草稿。 */
const businessId = ref('')
/** 动作码草稿。 */
const actionId = ref('')
/** 状态草稿。 */
const status = ref<MetaStatus>('enabled')
/** 载入基线指纹。 */
const baseline = ref('')

/**
 * 草稿指纹。
 *
 * @returns 指纹。
 */
function fingerprint(): string {
  return JSON.stringify({ businessId: businessId.value, actionId: actionId.value, status: status.value })
}

/** 是否存在未保存变更。 */
const dirty = computed(() => fingerprint() !== baseline.value)
watch(dirty, (value) => emit('dirty', value))

/** 业务码选项（新增仅启用项）。 */
const businessOptions = computed(() =>
  meta.businesses
    .filter((item) => item.status === 'enabled')
    .map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
)
/** 动作码选项（新增仅启用项）。 */
const actionOptions = computed(() =>
  meta.actions
    .filter((item) => item.status === 'enabled')
    .map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
)
/** 选中的业务码。 */
const selectedBusiness = computed(() => meta.businesses.find((item) => item.id === businessId.value))
/** 选中的动作码。 */
const selectedAction = computed(() => meta.actions.find((item) => item.id === actionId.value))
/** 组合派生权限码。 */
const derivedCode = computed(() =>
  selectedBusiness.value !== undefined && selectedAction.value !== undefined
    ? `${selectedBusiness.value.code}:${selectedAction.value.code}`
    : detail.value?.code ?? '',
)
/** 组合派生名称。 */
const derivedName = computed(() =>
  selectedBusiness.value !== undefined && selectedAction.value !== undefined
    ? `${selectedBusiness.value.name}·${selectedAction.value.name}`
    : detail.value?.name ?? '',
)
/** 系统信息。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: null,
  createdBy: null,
  createdAt: null,
  updatedBy: null,
  updatedAt: null,
  formKey: 'permission',
  formLabel: '权限码管理',
}))

/**
 * 载入权限码记录。
 */
async function load(): Promise<void> {
  loading.value = true
  editing.value = false
  try {
    await Promise.all([meta.ensurePermissions(true), meta.ensureBusinesses(), meta.ensureActions()])
    if (isNew.value) {
      detail.value = null
      businessId.value = ''
      actionId.value = ''
      status.value = 'enabled'
      baseline.value = fingerprint()
      editing.value = true
      return
    }
    const row = meta.permissions.find((item) => item.id === props.permissionId)
    if (row === undefined) {
      detail.value = null
      ElMessage.error('权限码不存在或已删除')
      return
    }
    detail.value = row
    businessId.value = row.business_id
    actionId.value = row.action_id
    status.value = row.status === 'disabled' ? 'disabled' : 'enabled'
    baseline.value = fingerprint()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '权限码详情加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 保存（新增 POST 组合 / 编辑仅 PUT 状态）。
 */
async function save(): Promise<void> {
  if (isNew.value) {
    if (businessId.value === '' || actionId.value === '') {
      ElMessage.error('请选择业务码与动作码')
      return
    }
  }
  saving.value = true
  try {
    const saved = isNew.value
      ? await createPermission({ business_id: businessId.value, action_id: actionId.value, status: status.value })
      : await updatePermission(props.permissionId, { status: status.value })
    if (isNew.value) {
      ElMessage.success('权限码已创建')
    } else {
      await load()
      ElMessage.success('权限码已保存')
    }
    emit('saved', saved)
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 取消编辑（恢复基线；新增态清空）。
 */
function cancel(): void {
  if (isNew.value) {
    businessId.value = ''
    actionId.value = ''
    status.value = 'enabled'
    baseline.value = fingerprint()
    editing.value = true
    return
  }
  if (detail.value !== null) {
    businessId.value = detail.value.business_id
    actionId.value = detail.value.action_id
    status.value = detail.value.status === 'disabled' ? 'disabled' : 'enabled'
  }
  baseline.value = fingerprint()
  editing.value = false
}

/**
 * 删除权限码（被按钮 / 角色授权引用时 `40206`）。
 */
async function remove(): Promise<void> {
  if (isNew.value) {
    return
  }
  try {
    await ElMessageBox.confirm('删除权限码后按钮挂接与角色授权将不可用，确认删除？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePermission(props.permissionId)
    emit('removed')
    ElMessage.success('权限码已删除')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

watch(
  () => props.permissionId,
  () => {
    void load()
  },
)

onMounted(() => {
  void load()
})

defineExpose({ save, load, remove })
</script>

<template>
  <div data-test="permission-record">
    <dict-record-layout v-model="section" :info="sysInfo" :disabled="!editing">
      <template #toolbar>
        <template v-if="editing">
          <el-button type="primary" :loading="saving" data-test="permission-record-save" @click="save">保存</el-button>
          <el-button data-test="permission-record-cancel" @click="cancel">取消</el-button>
        </template>
        <template v-else>
          <el-button type="primary" data-test="permission-record-edit" @click="editing = true">修改</el-button>
          <el-button type="danger" plain data-test="permission-record-delete" @click="remove">删除</el-button>
          <el-button data-test="permission-record-refresh" @click="load">刷新</el-button>
        </template>
        <el-button data-test="permission-record-close" @click="emit('close')">关闭</el-button>
        <span class="permission-record__side">
          <span v-if="loading" class="permission-record__hint" data-test="permission-record-loading">载入中…</span>
          <span v-if="dirty" class="permission-record__dirty" data-test="permission-record-dirty">● 有未保存变更</span>
        </span>
      </template>

      <template #first-row>
        <el-col :span="8">
          <el-form-item label="业务码" required>
            <el-select
              v-model="businessId"
              filterable
              :disabled="!isNew"
              placeholder="请选择业务码"
              style="width: 100%"
              data-test="permission-record-business"
            >
              <el-option v-for="item in businessOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="动作码" required>
            <el-select
              v-model="actionId"
              filterable
              :disabled="!isNew"
              placeholder="请选择动作码"
              style="width: 100%"
              data-test="permission-record-action"
            >
              <el-option v-for="item in actionOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="状态">
            <el-switch
              :model-value="status === 'enabled'"
              active-text="启用"
              inactive-text="停用"
              data-test="permission-record-status"
              @update:model-value="(value: boolean) => (status = value ? 'enabled' : 'disabled')"
            />
            <div class="permission-record__hint">停用时被按钮 / 角色授权引用将拒绝（40206）</div>
          </el-form-item>
        </el-col>
      </template>

      <template #fields>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="权限码（组合派生）">
              <el-input :model-value="derivedCode" readonly data-test="permission-record-code" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="名称（组合派生）">
              <el-input :model-value="derivedName" readonly data-test="permission-record-name" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="说明">
              <span class="permission-record__hint">
                权限码 = 业务码 × 动作码，只能选已存在的组合；组合创建后只读（换绑 = 删除重建）；平台维护、租户只读（40204）
              </span>
            </el-form-item>
          </el-col>
        </el-row>
      </template>
    </dict-record-layout>
  </div>
</template>

<style scoped>
.permission-record__side {
  margin-left: auto;
}

.permission-record__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.permission-record__hint {
  margin-top: var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}
</style>
