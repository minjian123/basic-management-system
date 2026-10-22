<script setup lang="ts">
// 表单记录页签：两子页签「详细信息 / 系统信息」，工具栏单一保存 + dirty 拦截。
// 对照原型《10_菜单管理/13_表单表单页.html》：业务码 1:1、视图组件选择器 + 可手输、关联菜单多选（可空）。
defineOptions({ name: 'FormRecordTab' })

import { DictRecordLayout, type SysInfoData } from '@bms/ui-ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import {
  createForm,
  deleteForm,
  updateForm,
  type FormItem,
  type MetaStatus,
} from '@/api/menuMeta'
import { fetchDataSourceList, fetchFormKeyList } from '@/api/registry'
import { useMenuMetaStore } from '@/stores/menuMeta'

import { toMenuFlatOptions } from '../menu/menuTree'

const props = defineProps<{
  /** 表单主键（新增态为 `new`）。 */
  formId: string
}>()

const emit = defineEmits<{
  /** 保存成功。 */
  saved: [form: FormItem]
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
const isNew = computed(() => props.formId === NEW_KEY)
/** 是否编辑态。 */
const editing = ref(false)
/** 表单详情（查看态数据源）。 */
const detail = ref<FormItem | null>(null)
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 视图组件候选（`/form-keys` + `/data-sources`，允许手输）。 */
const componentOptions = ref<string[]>([])
/** 草稿。 */
const draft = ref<FormDraft>(emptyDraft())
/** 载入基线。 */
const baseline = ref('')

/** 表单草稿。 */
interface FormDraft {
  /** 所属业务码 ID。 */
  business_id: string
  /** 视图组件标识（空串 = 留空）。 */
  component: string
  /** 关联菜单入口 ID。 */
  menu_ids: string[]
  /** 状态。 */
  status: MetaStatus
}

/**
 * 空草稿。
 *
 * @returns 草稿。
 */
function emptyDraft(): FormDraft {
  return { business_id: '', component: '', menu_ids: [], status: 'enabled' }
}

/**
 * 草稿指纹。
 *
 * @param value 草稿。
 * @returns 指纹。
 */
function fingerprint(value: FormDraft): string {
  return JSON.stringify({
    business_id: value.business_id,
    component: value.component.trim(),
    menu_ids: [...value.menu_ids].sort(),
    status: value.status,
  })
}

/** 是否存在未保存变更。 */
const dirty = computed(() => fingerprint(draft.value) !== baseline.value)
watch(dirty, (value) => emit('dirty', value))

/** 业务码选项。 */
const businessOptions = computed(() =>
  meta.businesses.map((item) => ({ value: item.id, label: `${item.code} · ${item.name}` })),
)
/** 关联菜单选项。 */
const menuOptions = computed(() => toMenuFlatOptions(meta.menus))
/** 系统信息。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: null,
  createdBy: null,
  createdAt: detail.value?.created_at ?? null,
  updatedBy: null,
  updatedAt: detail.value?.updated_at ?? null,
  formKey: 'form',
  formLabel: '表单管理',
}))

/**
 * 载入视图组件候选（失败降级为空候选，保留手输）。
 */
async function loadComponentOptions(): Promise<void> {
  try {
    const [formKeys, dataSources] = await Promise.all([fetchFormKeyList(), fetchDataSourceList()])
    const sourceKeys = dataSources.items.flatMap((item) => {
      const key = (item as Record<string, unknown>).data_source_key
      return typeof key === 'string' ? [key] : []
    })
    const values = [...formKeys.items.map((item) => item.form_key), ...sourceKeys]
    componentOptions.value = [...new Set(values)].filter((value) => value !== '')
  } catch {
    componentOptions.value = []
  }
}

/**
 * 契约行 → 草稿。
 *
 * @param row 表单行。
 * @returns 草稿。
 */
function toDraft(row: FormItem): FormDraft {
  return {
    business_id: row.business_id,
    component: row.component ?? '',
    menu_ids: (row.menu_ids ?? []).map(String),
    status: row.status === 'disabled' ? 'disabled' : 'enabled',
  }
}

/**
 * 载入表单记录。
 */
async function load(): Promise<void> {
  loading.value = true
  editing.value = false
  try {
    await Promise.all([meta.ensureForms(true), meta.ensureBusinesses(), meta.ensureMenus(), loadComponentOptions()])
    if (isNew.value) {
      detail.value = null
      draft.value = emptyDraft()
      baseline.value = fingerprint(draft.value)
      editing.value = true
      return
    }
    const row = meta.forms.find((item) => item.id === props.formId)
    if (row === undefined) {
      detail.value = null
      ElMessage.error('表单不存在或已删除')
      return
    }
    detail.value = row
    draft.value = toDraft(row)
    baseline.value = fingerprint(draft.value)
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '表单详情加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 组装请求载荷。
 *
 * @returns 载荷。
 */
function payload(): { menu_ids: string[]; business_id: string; component: string | null; status: MetaStatus } {
  return {
    menu_ids: draft.value.menu_ids.map(String),
    business_id: draft.value.business_id,
    component: draft.value.component.trim() === '' ? null : draft.value.component.trim(),
    status: draft.value.status,
  }
}

/**
 * 保存（新增 POST / 编辑 PUT）。
 */
async function save(): Promise<void> {
  if (draft.value.business_id === '') {
    ElMessage.error('请选择业务码（表单 1:1 挂业务码）')
    return
  }
  saving.value = true
  try {
    const saved = isNew.value
      ? await createForm(payload())
      : await updateForm(props.formId, payload())
    if (isNew.value) {
      ElMessage.success('表单已创建')
    } else {
      await load()
      ElMessage.success('表单已保存')
    }
    emit('saved', saved)
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 取消编辑：恢复载入基线（新增态恢复为空草稿）。
 */
function cancel(): void {
  if (isNew.value) {
    draft.value = emptyDraft()
    baseline.value = fingerprint(draft.value)
    editing.value = true
    return
  }
  if (detail.value !== null) {
    draft.value = toDraft(detail.value)
  }
  baseline.value = fingerprint(draft.value)
  editing.value = false
}

/**
 * 删除表单（被引用时 `40206`）。
 */
async function remove(): Promise<void> {
  if (isNew.value) {
    return
  }
  try {
    await ElMessageBox.confirm('删除表单后其按钮 / 字段与菜单入口将不可用，确认删除？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteForm(props.formId)
    emit('removed')
    ElMessage.success('表单已删除')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

watch(
  () => props.formId,
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
  <div data-test="form-record">
    <dict-record-layout v-model="section" :info="sysInfo" :disabled="!editing">
      <template #toolbar>
        <template v-if="editing">
          <el-button type="primary" :loading="saving" data-test="form-record-save" @click="save">保存</el-button>
          <el-button data-test="form-record-cancel" @click="cancel">取消</el-button>
        </template>
        <template v-else>
          <el-button type="primary" data-test="form-record-edit" @click="editing = true">修改</el-button>
          <el-button type="danger" plain data-test="form-record-delete" @click="remove">删除</el-button>
          <el-button data-test="form-record-refresh" @click="load">刷新</el-button>
        </template>
        <el-button data-test="form-record-close" @click="emit('close')">关闭</el-button>
        <span class="form-record__side">
          <span v-if="loading" class="form-record__hint" data-test="form-record-loading">载入中…</span>
          <span v-if="dirty" class="form-record__dirty" data-test="form-record-dirty">● 有未保存变更</span>
        </span>
      </template>

      <template #first-row>
        <el-col :span="8">
          <el-form-item label="业务码" required>
            <el-select
              v-model="draft.business_id"
              filterable
              placeholder="请选择业务码"
              style="width: 100%"
              data-test="form-record-business"
            >
              <el-option v-for="item in businessOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
            <div class="form-record__hint">表单 1:1 挂业务码；未挂业务即挂接链断裂（40202）</div>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="视图组件">
            <el-select
              v-model="draft.component"
              filterable
              allow-create
              default-first-option
              clearable
              placeholder="选择组件或直接输入"
              style="width: 100%"
              data-test="form-record-component"
            >
              <el-option v-for="item in componentOptions" :key="item" :label="item" :value="item" />
            </el-select>
            <div class="form-record__hint">可从候选组件选择，也可直接输入；留空则缺省取菜单 component</div>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="状态">
            <el-switch
              :model-value="draft.status === 'enabled'"
              active-text="启用"
              inactive-text="停用"
              data-test="form-record-status"
              @update:model-value="(value: boolean) => (draft.status = value ? 'enabled' : 'disabled')"
            />
            <div class="form-record__hint">停用后该表单的按钮 / 字段与菜单入口即时不可用</div>
          </el-form-item>
        </el-col>
      </template>

      <template #fields>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="关联菜单">
              <el-select
                v-model="draft.menu_ids"
                multiple
                filterable
                collapse-tags
                collapse-tags-tooltip
                placeholder="可不选（无菜单入口）"
                style="width: 100%"
                data-test="form-record-menus"
              >
                <el-option v-for="item in menuOptions" :key="item.id" :label="item.label" :value="item.id" />
              </el-select>
              <div class="form-record__hint">
                已关联 {{ draft.menu_ids.length }} 个菜单入口 · <b>多对多</b>（<code>sys_menu_form</code>）；无入口表单独立维护，不构成挂接链断裂
              </div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="说明">
              <span class="form-record__hint">
                按钮（挂权限码）与字段（挂表单）在菜单记录页「挂接配置」维护；字段权限统一在角色管理授予，本模块不提供授予入口
              </span>
            </el-form-item>
          </el-col>
        </el-row>
      </template>
    </dict-record-layout>
  </div>
</template>

<style scoped>
.form-record__side {
  margin-left: auto;
}

.form-record__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.form-record__hint {
  margin-top: var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}
</style>
