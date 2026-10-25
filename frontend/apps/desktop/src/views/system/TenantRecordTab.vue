<script setup lang="ts">
// 租户记录 Tab（表单框架的记录页）：基本信息 / 配额与模块 / 系统信息。
// 基本信息支持查看 ⇄ 编辑；配额与模块子页签内配额整组保存、模块开关即时生效。
import { DictRecordLayout, type SysInfoData } from '@bms/ui_ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import {
  fetchTenantModules,
  fetchTenantQuotas,
  getTenant,
  switchTenantModule,
  updateTenant,
  updateTenantQuotas,
  type TenantDetail,
  type TenantModuleItem,
  type TenantQuotaItem,
} from '@/api/tenantAdmin'

import { moduleStatusLabel, quotaLabel, quotaUnit, tenantStatusLabel, tenantStatusTag } from './tenant/labels'

const props = defineProps<{
  /** 租户主键。 */
  tenantId: string
}>()

const emit = defineEmits<{ saved: [tenant: TenantDetail]; dirty: [dirty: boolean]; close: [] }>()

/** 当前子页签（骨架件受控键：`detail` / `quota` / `sys`）。 */
const section = ref<string>('detail')
/** 配额与模块子页签（`quota` / `modules`）。 */
const assetSection = ref<string>('quota')
/** 是否编辑态。 */
const editing = ref(false)
/** 租户详情。 */
const detail = ref<TenantDetail | null>(null)
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 基本信息表单。 */
const form = ref<{ name: string; domain: string; expire_at: string }>({ name: '', domain: '', expire_at: '' })
/** 基本信息基线。 */
const baseline = ref<{ name: string; domain: string; expire_at: string }>({ name: '', domain: '', expire_at: '' })
/** 配额编辑值（维度 → 限额）。 */
const quotaLimits = ref<Record<string, number>>({})
/** 配额基线（维度 → 限额）。 */
const quotaBaseline = ref<Record<string, number>>({})
/** 模块清单。 */
const modules = ref<TenantModuleItem[]>([])
/** 基本信息脏态。 */
const detailDirty = ref(false)
/** 配额脏态。 */
const quotaDirty = ref(false)

/** 是否存在未保存变更。 */
const dirty = computed(() => detailDirty.value || quotaDirty.value)
/** 系统信息。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: detail.value?.version ?? null,
  createdBy: null,
  createdAt: detail.value?.created_at ?? null,
  updatedBy: null,
  updatedAt: detail.value?.updated_at ?? null,
  formKey: 'tenant',
  formLabel: '租户管理',
}))
/** 配额行（按维度排序）。 */
const quotaRows = computed<TenantQuotaItem[]>(() =>
  [...(detail.value?.quotas ?? [])].sort((left, right) => left.quota_key.localeCompare(right.quota_key)),
)

watch(dirty, (value) => emit('dirty', value))

/** 基本信息改动判定（与基线逐字段比对）。 */
watch(
  form,
  () => {
    if (!editing.value) {
      detailDirty.value = false
      return
    }
    const base = baseline.value
    detailDirty.value =
      form.value.name !== base.name || form.value.domain !== base.domain || form.value.expire_at !== base.expire_at
  },
  { deep: true },
)

/** 配额改动判定（与基线逐维度比对）。 */
watch(
  quotaLimits,
  () => {
    const base = quotaBaseline.value
    quotaDirty.value = Object.keys(base).some((key) => quotaLimits.value[key] !== base[key])
  },
  { deep: true },
)

/**
 * 归一到期时间（空 → 空串；去掉毫秒与 Z）。
 *
 * @param value 合同时间。
 */
function toDateText(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  return String(value)
    .replace('T', ' ')
    .replace(/\.\d+Z?$/, '')
    .slice(0, 19)
}

/**
 * 转回契约时间（展示值 `YYYY-MM-DD HH:mm:ss` → `YYYY-MM-DDTHH:mm:ss`）。
 *
 * @param value 展示值。
 */
function toContractDate(value: string): string | null {
  const text = value.trim()
  if (text === '') {
    return null
  }
  return text.includes('T') ? text : text.replace(' ', 'T')
}

/** 载入租户详情 / 模块 / 配额。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await getTenant(props.tenantId)
    detail.value = data
    form.value = {
      name: data.name ?? '',
      domain: data.domain ?? '',
      expire_at: toDateText(data.expire_at),
    }
    baseline.value = { ...form.value }
    quotaLimits.value = Object.fromEntries((data.quotas ?? []).map((item) => [item.quota_key, item.limit_value]))
    quotaBaseline.value = { ...quotaLimits.value }
    modules.value = [...(data.modules ?? [])]
    detailDirty.value = false
    quotaDirty.value = false
    editing.value = false
    try {
      const [quotaResult, moduleResult] = await Promise.all([
        fetchTenantQuotas(props.tenantId),
        fetchTenantModules(props.tenantId),
      ])
      detail.value = { ...data, quotas: quotaResult.items ?? data.quotas, modules: moduleResult.items ?? data.modules }
      quotaLimits.value = Object.fromEntries(
        (detail.value.quotas ?? []).map((item) => [item.quota_key, item.limit_value]),
      )
      quotaBaseline.value = { ...quotaLimits.value }
      modules.value = [...(detail.value.modules ?? [])]
    } catch {
      // 附属清单失败保持详情内嵌数据（不阻断基本信息查看）。
    }
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '租户详情加载失败')
  } finally {
    loading.value = false
  }
}

/** 切换编辑态（取消时回填基线）。 */
function toggleEditing(): void {
  if (editing.value) {
    form.value = { ...baseline.value }
    editing.value = false
    detailDirty.value = false
    return
  }
  editing.value = true
}

/** 提交保存（基本信息 + 配额；模块开关即时生效不参与保存）。 */
async function save(): Promise<void> {
  if (form.value.name.trim() === '') {
    ElMessage.warning('租户名称不能为空')
    return
  }
  saving.value = true
  try {
    if (detailDirty.value) {
      const updated = await updateTenant(props.tenantId, {
        name: form.value.name.trim(),
        domain: form.value.domain.trim() || null,
        expire_at: toContractDate(form.value.expire_at),
      })
      detail.value = updated
    }
    if (quotaDirty.value) {
      await updateTenantQuotas(
        props.tenantId,
        Object.entries(quotaLimits.value).map(([quota_key, limit_value]) => ({ quota_key, limit_value })),
      )
    }
    await load()
    emit('saved', detail.value as TenantDetail)
    ElMessage.success('租户已保存')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 切换模块开关（基础模块只读；即时生效）。
 *
 * @param item 模块项。
 * @param enabled 目标是否启用。
 */
async function toggleModule(item: TenantModuleItem, enabled: boolean): Promise<void> {
  if (!item.optional) {
    return
  }
  try {
    await ElMessageBox.confirm(
      enabled ? `确认开通模块「${item.name}」？` : `确认停用模块「${item.name}」？停用后该模块菜单与接口将不可用。`,
      enabled ? '开通模块' : '停用模块',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    const result = await switchTenantModule(props.tenantId, item.module_key, enabled ? 'enabled' : 'disabled')
    modules.value = [...(result.items ?? modules.value)]
    if (detail.value !== null) {
      detail.value = { ...detail.value, modules: modules.value }
    }
    ElMessage.success(enabled ? '模块已开通' : '模块已停用')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '模块状态切换失败')
  }
}

watch(
  () => props.tenantId,
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
  <div data-test="tenant-record">
    <dict-record-layout v-model="section" :info="sysInfo" :disabled="!editing">
      <template #toolbar>
        <el-button
          v-if="editing || dirty"
          type="primary"
          :loading="saving"
          data-test="tenant-record-save"
          @click="save"
        >
          保存
        </el-button>
        <el-button v-if="dirty" data-test="tenant-record-revert" @click="toggleEditing">撤销</el-button>
        <el-button v-else-if="!editing" data-test="tenant-record-edit" @click="toggleEditing">编辑</el-button>
        <el-button data-test="tenant-record-close" @click="emit('close')">关闭</el-button>
        <span class="tenant-record__side">
          <span v-if="loading" class="tenant-record__hint">载入中…</span>
          <span v-if="dirty" class="tenant-record__dirty" data-test="tenant-record-dirty">● 有未保存变更</span>
        </span>
      </template>

      <template #first-row>
        <el-col :span="8">
          <el-form-item label="租户编码">
            <el-input :model-value="detail?.code ?? ''" disabled data-test="tenant-record-code" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="租户名称" required>
            <el-input v-model="form.name" :disabled="!editing" data-test="tenant-record-name" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="状态">
            <el-tag :type="tenantStatusTag(detail?.status)" data-test="tenant-record-status">
              {{ tenantStatusLabel(detail?.status) }}
            </el-tag>
          </el-form-item>
        </el-col>
      </template>

      <template #fields>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="子域名">
              <el-input
                v-model="form.domain"
                :disabled="!editing"
                placeholder="如 acme.bms.example.com"
                data-test="tenant-record-domain"
              />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="到期时间">
              <el-date-picker
                v-model="form.expire_at"
                type="datetime"
                value-format="YYYY-MM-DD HH:mm:ss"
                :disabled="!editing"
                placeholder="不限"
                data-test="tenant-record-expire"
              />
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <template #extra-tabs>
        <el-tab-pane label="配额与模块" name="quota">
          <el-tabs v-model="assetSection" data-test="tenant-asset-tabs">
            <el-tab-pane label="配额" name="quota">
              <el-table :data="quotaRows" border row-key="quota_key" data-test="tenant-quota-table">
                <el-table-column label="配额维度" min-width="150">
                  <template #default="{ row }">
                    <span>{{ quotaLabel(row.quota_key) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="已用量" min-width="140">
                  <template #default="{ row }">
                    <span>{{ row.used_value }} {{ quotaUnit(row.quota_key) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="限额" min-width="180">
                  <template #default="{ row }">
                    <el-input-number
                      v-model="quotaLimits[row.quota_key]"
                      :min="0"
                      :step="1"
                      :disabled="!editing"
                      data-test="tenant-quota-limit"
                    />
                  </template>
                </el-table-column>
                <template #empty>
                  <empty-state type="data" title="暂无配额" description="该租户尚未配置配额。" />
                </template>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="模块开关" name="modules">
              <el-table :data="modules" border row-key="module_key" data-test="tenant-module-table">
                <el-table-column prop="name" label="模块" min-width="150" />
                <el-table-column prop="module_key" label="标识" min-width="120" />
                <el-table-column label="类型" width="110">
                  <template #default="{ row }">
                    <span>{{ row.optional ? '产品模块' : '基础能力' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="110">
                  <template #default="{ row }">
                    <span>{{ moduleStatusLabel(row.status) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="开关" width="100">
                  <template #default="{ row }">
                    <el-switch
                      :model-value="row.status === 'enabled'"
                      :disabled="!row.optional"
                      data-test="tenant-module-switch"
                      @change="(value: string | number | boolean) => toggleModule(row, value === true)"
                    />
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>
      </template>
    </dict-record-layout>
  </div>
</template>

<style scoped>
.tenant-record__side {
  margin-left: auto;
}

.tenant-record__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.tenant-record__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}
</style>
