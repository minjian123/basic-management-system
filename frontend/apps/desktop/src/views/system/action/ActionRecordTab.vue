<script setup lang="ts">
// 动作码记录页签：两子页签「详细信息 / 系统信息」，工具栏单一保存 + dirty 拦截。
// 动作码创建后只读（全局动词、不归属业务）；停用联动其权限码（任一被引用整批拒绝 40206）。
defineOptions({ name: 'ActionRecordTab' })

import { DictRecordLayout, MultilingualNameField, type SysInfoData } from '@bms/ui_ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import { createAction, deleteAction, listActions, updateAction, type ActionItem } from '@/api/action'
import type { I18nNames, MetaStatus } from '@/api/menuMeta'

import { ENABLED_LOCALES, currentUserLocale } from '../metaLocale'

const props = defineProps<{
  /** 动作码主键（新增态为 `new`）。 */
  actionId: string
}>()

const emit = defineEmits<{
  /** 保存成功。 */
  saved: [item: ActionItem]
  /** 删除成功。 */
  removed: []
  /** 脏态同步。 */
  dirty: [dirty: boolean]
  /** 请求关闭。 */
  close: []
}>()

/** 新增态标识。 */
const NEW_KEY = 'new'

/** 当前子页签。 */
const section = ref('detail')
/** 当前登录用户语言。 */
const userLocale = ref(currentUserLocale())
/** 是否新增态。 */
const isNew = computed(() => props.actionId === NEW_KEY)
/** 是否编辑态。 */
const editing = ref(false)
/** 动作码详情。 */
const detail = ref<ActionItem | null>(null)
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 动作码草稿。 */
const code = ref('')
/** 名称草稿。 */
const names = ref<I18nNames>({})
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
  return JSON.stringify({
    code: code.value.trim(),
    status: status.value,
    i18n: Object.keys(names.value)
      .sort()
      .map((key) => [key, names.value[key] ?? '']),
  })
}

/** 是否存在未保存变更。 */
const dirty = computed(() => fingerprint() !== baseline.value)
watch(dirty, (value) => emit('dirty', value))

/**
 * 回写多语言名称（内容相同不回写，避免受控件同步回环）。
 *
 * @param next 多语言映射。
 */
function applyNames(next: I18nNames): void {
  const keys = new Set([...Object.keys(next), ...Object.keys(names.value)])
  for (const key of keys) {
    if ((next[key] ?? '') !== (names.value[key] ?? '')) {
      names.value = { ...next }
      return
    }
  }
}

/** 系统信息。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: null,
  createdBy: null,
  createdAt: null,
  updatedBy: null,
  updatedAt: null,
  formKey: 'action',
  formLabel: '动作码管理',
}))

/**
 * 载入动作码记录。
 */
async function load(): Promise<void> {
  loading.value = true
  editing.value = false
  try {
    if (isNew.value) {
      detail.value = null
      code.value = ''
      names.value = {}
      status.value = 'enabled'
      baseline.value = fingerprint()
      editing.value = true
      return
    }
    const row = (await listActions()).items?.find((item) => item.id === props.actionId)
    if (row === undefined) {
      detail.value = null
      ElMessage.error('动作码不存在或已删除')
      return
    }
    detail.value = row
    code.value = row.code
    names.value = { ...row.i18n }
    status.value = row.status === 'disabled' ? 'disabled' : 'enabled'
    baseline.value = fingerprint()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '动作码详情加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 保存（新增 POST / 编辑 PUT）。
 */
async function save(): Promise<void> {
  if (code.value.trim() === '') {
    ElMessage.error('动作码必填')
    return
  }
  if (!/^[a-z][a-z0-9_]*$/.test(code.value.trim())) {
    ElMessage.error('动作码须小写字母开头，仅含小写字母 / 数字 / 下划线')
    return
  }
  if ((names.value[userLocale.value] ?? '').trim() === '') {
    ElMessage.error(`名称（${userLocale.value}）不能为空`)
    return
  }
  saving.value = true
  try {
    const saved = isNew.value
      ? await createAction({ code: code.value.trim(), status: status.value, i18n: names.value })
      : await updateAction(props.actionId, { status: status.value, i18n: names.value })
    if (isNew.value) {
      ElMessage.success('动作码已创建')
    } else {
      await load()
      ElMessage.success('动作码已保存')
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
    code.value = ''
    names.value = {}
    status.value = 'enabled'
    baseline.value = fingerprint()
    editing.value = true
    return
  }
  if (detail.value !== null) {
    code.value = detail.value.code
    names.value = { ...detail.value.i18n }
    status.value = detail.value.status === 'disabled' ? 'disabled' : 'enabled'
  }
  baseline.value = fingerprint()
  editing.value = false
}

/**
 * 删除动作码（其下有权限码时 `40206`）。
 */
async function remove(): Promise<void> {
  if (isNew.value) {
    return
  }
  try {
    await ElMessageBox.confirm('删除动作码后其权限码将不可用，确认删除？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteAction(props.actionId)
    emit('removed')
    ElMessage.success('动作码已删除')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

watch(
  () => props.actionId,
  () => {
    void load()
  },
)

onMounted(() => {
  userLocale.value = currentUserLocale()
  void load()
})

defineExpose({ save, load, remove })
</script>

<template>
  <div data-test="action-record">
    <dict-record-layout v-model="section" :info="sysInfo" :disabled="!editing">
      <template #toolbar>
        <template v-if="editing">
          <el-button type="primary" :loading="saving" data-test="action-record-save" @click="save">保存</el-button>
          <el-button data-test="action-record-cancel" @click="cancel">取消</el-button>
        </template>
        <template v-else>
          <el-button type="primary" data-test="action-record-edit" @click="editing = true">修改</el-button>
          <el-button type="danger" plain data-test="action-record-delete" @click="remove">删除</el-button>
          <el-button data-test="action-record-refresh" @click="load">刷新</el-button>
        </template>
        <el-button data-test="action-record-close" @click="emit('close')">关闭</el-button>
        <span class="action-record__side">
          <span v-if="loading" class="action-record__hint" data-test="action-record-loading">载入中…</span>
          <span v-if="dirty" class="action-record__dirty" data-test="action-record-dirty">● 有未保存变更</span>
        </span>
      </template>

      <template #first-row>
        <el-col :span="8">
          <el-form-item label="动作码" required>
            <el-input v-model="code" :disabled="!isNew" placeholder="如 create" data-test="action-record-code" />
            <div class="action-record__hint">{{ isNew ? 'snake_case：小写字母开头，仅小写字母 / 数字 / 下划线；创建后只读' : '动作码创建后只读（换码 = 新建 + 迁移 + 停用旧码）' }}</div>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="名称" required>
            <multilingual-name-field
              :model-value="names"
              :locales="ENABLED_LOCALES"
              :user-locale="userLocale"
              required
              data-test="action-record-name"
              @change="applyNames"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="状态">
            <el-switch
              :model-value="status === 'enabled'"
              active-text="启用"
              inactive-text="停用"
              data-test="action-record-status"
              @update:model-value="(value: boolean) => (status = value ? 'enabled' : 'disabled')"
            />
            <div class="action-record__hint">停用将连带停用其权限码（被按钮 / 角色引用时整批拒绝 40206）</div>
          </el-form-item>
        </el-col>
      </template>

      <template #fields>
        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="说明">
              <span class="action-record__hint">
                动作码为全局动词维度（不归属业务），与业务码组合成权限码；名称按 locale 存多语言附表
              </span>
            </el-form-item>
          </el-col>
        </el-row>
      </template>
    </dict-record-layout>
  </div>
</template>

<style scoped>
.action-record__side {
  margin-left: auto;
}

.action-record__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.action-record__hint {
  margin-top: var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}
</style>
