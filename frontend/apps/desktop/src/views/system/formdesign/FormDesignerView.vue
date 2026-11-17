<script setup lang="ts">
// 表单定制设计器页（10_02）：表单选择 + 三级层级 + 角色视图 + 设计器三区 + 结构化属性面板。
// 结构对照原型《07_表单定制/02_表单设计器.html》：动作集一致（保存 / 发布 / 恢复默认 / 新建自定义字段），
// 位置分为页面工具栏（刷新 / 关闭 / 帮助）与设计器工具栏两处。取数口径见详细设计 §6.2：
// 三层布局与属性取 `/form-design/layouts`，平台字段取 `/forms/{code}/layout-effective`，自建字段取清单。
import type {
  DesignerExtFieldResult,
  DesignerJobs,
  DesignerLevel,
  DesignerSelection,
  DesignerSnapshot,
  FormField,
} from '@bms/core'
import { EXT_FIELD_TYPES, FORMDESIGN_PERM, extFieldNeedsOptions } from '@bms/core'
import type { ToolbarActionOverride } from '@bms/core'
import { FieldAttrPanel, FormDesigner, ListToolbar, PageContainer, type FieldAttrsPatch } from '@bms/ui_ep'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createExtField,
  deleteAttrs,
  deleteLayout,
  getEffectiveLayout,
  listExtFields,
  listLayouts,
  retryExtField,
  saveAttrs,
  saveLayout,
  toLayerAttrs,
  toLevels,
  type ExtFieldItem,
  type FieldAttrRow,
  type LayoutEffectiveResponse,
  type LayoutLevelRow,
} from '@/api/formDesign'
import { listOptionSetKeys } from '@/api/optionSets'
import { listRoles } from '@/api/role'
import { usePageHelpContext } from '@/composables/usePageHelpContext'
import { useSessionStore } from '@/stores/session'
import { useMenuMetaStore } from '@/stores/menuMeta'

import { attrsPayload, designerFields, extFieldKey, pickRowId, toAttrDraft } from './layoutMapping'

defineOptions({ name: 'SystemFormDesign' })

/** 设计器默认层级（租户覆盖：最常用）。 */
const DEFAULT_LEVEL: DesignerLevel = 'tenant'
/** 角色下拉取数上限（平台角色数量远小于该值）。 */
const ROLE_PAGE_SIZE = 100

const router = useRouter()
const session = useSessionStore()
const meta = useMenuMetaStore()

/** 页面帮助上下文（无锚点时不显示帮助入口）。 */
const { help: pageHelp, fetcher: helpFetcher } = usePageHelpContext()

/** 业务码清单（表单选择器）。 */
const businesses = computed(() => meta.businesses)
/** 角色清单（角色视图）。 */
const roles = ref<{ id: string; name: string }[]>([])
/** 已注册选项集标识（属性面板与自建字段下拉）。 */
const optionSetKeys = ref<string[]>([])

/** 选中表单（业务码）。 */
const formCode = ref('')
/** 当前层级。 */
const level = ref<DesignerLevel>(DEFAULT_LEVEL)
/** 选中角色（角色视图）。 */
const roleId = ref('')
/** 数据通路就绪（置真即触发设计器装载）。 */
const ready = ref(false)
/** 设计器重挂载令牌（重载后件内本地态归零）。 */
const loadToken = ref(0)
/** 载入中。 */
const loading = ref(false)
/** 合并字段清单。 */
const fields = ref<FormField[]>([])
/** 自建字段行（含主键与 DDL 状态，重试用）。 */
const extItems = ref<ExtFieldItem[]>([])
/** 布局行（恢复默认定位待删行）。 */
const layoutRows = ref<LayoutLevelRow[]>([])
/** 属性行（层内属性初值）。 */
const attrRows = ref<FieldAttrRow[]>([])
/** 生效布局响应（平台字段来源）。 */
const effective = ref<LayoutEffectiveResponse | undefined>(undefined)
/** 层内属性草稿（字段键 → 面板补丁）。 */
const drafts = ref<Record<string, FieldAttrsPatch>>({})
/** 属性是否有未保存修改。 */
const attrsDirty = ref(false)
/** 布局是否有未保存修改。 */
const layoutDirty = ref(false)
/** 画布选中对象。 */
const selected = ref<DesignerSelection | null>(null)
/** 最近一次装载快照（件内取数直接消费，避免重复请求）。 */
const snapshotCache = ref<DesignerSnapshot>({ levels: {}, fields: [] })

/** 是否持维护权限（后端为准，页面据此决定只读提示）。 */
const canManage = computed(() => session.codes.includes(FORMDESIGN_PERM))
/** 当前层级是否只读。 */
const levelReadonly = computed(() => level.value === 'platform')
/** 属性面板禁用（无权限 / 平台默认层级）。 */
const panelDisabled = computed(() => !canManage.value || levelReadonly.value)
/** 当前选中字段。 */
const selectedField = computed(() => {
  if (selected.value === null || selected.value.kind !== 'field') {
    return null
  }
  return fields.value.find((field) => field.key === selected.value?.key) ?? null
})
/** 当前字段的属性草稿。 */
const selectedAttrs = computed<FieldAttrsPatch>(() => {
  const field = selectedField.value
  return field === null ? {} : (drafts.value[field.key] ?? {})
})
/** 未保存提示（布局脏或属性脏）。 */
const dirtyHint = computed(() => layoutDirty.value || attrsDirty.value)

/** 列表工具栏覆盖（保留刷新 / 关闭，隐藏新增与批量动作）。 */
const toolbarOverrides: ToolbarActionOverride[] = [
  { key: 'create', hidden: true },
  { key: 'batch-toggle', hidden: true },
  { key: 'batch-delete', hidden: true },
  { key: 'refresh', label: '刷新', order: 10 },
  { key: 'close', label: '关闭', order: 20 },
]

/**
 * 取当前层属性并重建草稿（切换层级 / 装载完成后）。
 */
function applyLayer(): void {
  const scope = level.value
  const role = scope === 'role' ? roleId.value : '0'
  const layer = toLayerAttrs(attrRows.value, scope, role)
  const next: Record<string, FieldAttrsPatch> = {}
  for (const field of fields.value) {
    next[field.key] = toAttrDraft(layer[field.key])
  }
  drafts.value = next
  attrsDirty.value = false
}

/**
 * 取数并落页面态（三层布局 + 平台字段 + 自建字段）。
 *
 * @param code 表单标识（业务码）。
 * @returns 设计器快照。
 */
async function loadSnapshot(code: string): Promise<DesignerSnapshot> {
  const [layouts, effectiveResponse, extList] = await Promise.all([
    listLayouts(code),
    getEffectiveLayout(code),
    listExtFields(code),
  ])
  layoutRows.value = [...(layouts.layouts ?? [])]
  attrRows.value = [...(layouts.attrs ?? [])]
  effective.value = effectiveResponse
  extItems.value = [...(extList.items ?? [])]
  fields.value = designerFields(effectiveResponse, extItems.value)
  selected.value = null
  layoutDirty.value = false
  const levels = toLevels(layoutRows.value, roleId.value === '' ? undefined : roleId.value)
  snapshotCache.value = { levels, fields: fields.value }
  return snapshotCache.value
}

/**
 * 重载设计器（重挂载 + 重新取数）。
 */
async function reload(): Promise<void> {
  if (formCode.value === '') {
    return
  }
  loading.value = true
  ready.value = false
  await nextTick()
  loadToken.value += 1
  await nextTick()
  try {
    await loadSnapshot(formCode.value)
    applyLayer()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '表单定制数据加载失败')
  } finally {
    loading.value = false
    ready.value = true
  }
}

/**
 * 切换表单（脏数据先拦）。
 *
 * @param next 业务码。
 */
function onFormChange(next: string): void {
  if (next === formCode.value) {
    return
  }
  if (dirtyHint.value) {
    ElMessage.warning('存在未保存修改，请先保存或撤销后再切换表单')
    return
  }
  formCode.value = next
  void reload()
}

/**
 * 切换层级（脏数据先拦；层级只换工作副本，不重新取数）。
 *
 * @param next 层级。
 */
function onLevelChange(next: string | number | boolean | undefined): void {
  const target = next as DesignerLevel
  if (target === level.value) {
    return
  }
  if (dirtyHint.value) {
    ElMessage.warning('存在未保存修改，请先保存或撤销后再切换层级')
    return
  }
  level.value = target
  selected.value = null
  applyLayer()
}

/**
 * 切换角色（角色视图）。
 *
 * @param next 角色主键。
 */
function onRoleChange(next: string): void {
  if (next === roleId.value) {
    return
  }
  if (dirtyHint.value) {
    ElMessage.warning('存在未保存修改，请先保存或撤销后再切换角色')
    return
  }
  roleId.value = next
  void reload()
}

/**
 * 画布选中联动属性面板。
 *
 * @param target 选中对象。
 */
function onSelect(target: DesignerSelection | null): void {
  selected.value = target
}

/**
 * 属性补丁落草稿。
 *
 * @param patch 补丁。
 */
function onAttrChange(patch: FieldAttrsPatch): void {
  const field = selectedField.value
  if (field === null || panelDisabled.value) {
    return
  }
  drafts.value = { ...drafts.value, [field.key]: { ...drafts.value[field.key], ...patch } }
  attrsDirty.value = true
}

/**
 * 删除某条校验规则。
 *
 * @param index 规则下标。
 */
function onRemoveRule(index: number): void {
  const field = selectedField.value
  if (field === null || panelDisabled.value) {
    return
  }
  const current = drafts.value[field.key]?.rules ?? []
  const rules = current.filter((_rule, position) => position !== index)
  drafts.value = { ...drafts.value, [field.key]: { ...drafts.value[field.key], rules } }
  attrsDirty.value = true
}

/**
 * 角色主键的传输形态（契约声明为整型，实际按字符串提交以避免雪花 ID 精度丢失；后端宽松解析）。
 *
 * @param role 角色主键（空串表示非角色层级）。
 * @returns 请求体 `role_id`。
 */
function roleIdPayload(role: string): number {
  return (role === '' ? '0' : role) as unknown as number
}

/**
 * 取自建字段下一排序值。
 *
 * @returns 排序号（空清单从 1 起）。
 */
function nextSort(): number {
  return extItems.value.reduce((max, item) => Math.max(max, item.sort), 0) + 1
}

/**
 * 设计器处理函数集（注入件内驱动真实编排）。
 */
const jobs: DesignerJobs = {
  load: () => Promise.resolve(snapshotCache.value),
  save: async (input) => {
    const role = roleIdPayload(input.roleId ?? '')
    await saveLayout({
      form_code: input.formCode,
      scope: input.level,
      role_id: role,
      layout_config: input.layout as unknown as Record<string, unknown>,
    })
    const items = attrsPayload(fields.value, drafts.value)
    try {
      await saveAttrs({ form_code: input.formCode, scope: input.level, role_id: role, fields: items })
      attrsDirty.value = false
    } catch (error: unknown) {
      attrsDirty.value = true
      ElMessage.warning(
        `布局已保存，字段属性保存失败：${error instanceof Error ? error.message : '未知错误'}（可修正后再次保存）`,
      )
    }
    void reload()
    return {}
  },
  publish: () => {
    ElMessage.success('已发布：布局保存在前，sys.form.updated 随保存事务发出')
    return Promise.resolve()
  },
  restore: async (input) => {
    const role = input.level === 'role' ? (input.roleId ?? '0') : '0'
    const layoutId = pickRowId(layoutRows.value, input.level, role)
    const attrId = pickRowId(attrRows.value, input.level, role)
    if (layoutId !== '') {
      await deleteLayout(layoutId)
    }
    if (attrId !== '') {
      await deleteAttrs(attrId)
    }
    void reload()
  },
  createField: async (input) => {
    const key = extFieldKey(input.draft.nameEn ?? '')
    if (key === '') {
      throw new Error('请填写英文名称（用于字段键与物理列名）')
    }
    if (fields.value.some((field) => field.key === key)) {
      throw new Error(`字段键已存在：${key}`)
    }
    const created = await createExtField({
      form_code: input.formCode,
      field_key: key,
      name: input.draft.name,
      type: input.draft.type,
      sort: nextSort(),
      ...(extFieldNeedsOptions(input.draft.type) ? { option_set_key: input.draft.options?.[0]?.value } : {}),
    })
    const list = await listExtFields(input.formCode)
    extItems.value = [...(list.items ?? [])]
    return {
      fieldKey: created.field_key,
      columnName: created.column_name,
      ddlStatus: created.ddl_status as DesignerExtFieldResult['ddlStatus'],
    }
  },
  retryField: async (input) => {
    const target = extItems.value.find((item) => item.field_key === input.fieldKey)
    if (target === undefined) {
      throw new Error(`未找到自建字段：${input.fieldKey}（请刷新后重试）`)
    }
    const result = await retryExtField(target.id)
    const list = await listExtFields(input.formCode)
    extItems.value = [...(list.items ?? [])]
    return {
      fieldKey: result.field_key,
      columnName: result.column_name,
      ddlStatus: result.ddl_status as DesignerExtFieldResult['ddlStatus'],
    }
  },
}

/**
 * 布局变更（记脏）。
 */
function onChange(): void {
  layoutDirty.value = true
}

/**
 * 设计器失败提示。
 *
 * @param payload 失败载荷。
 */
function onFailed(payload: { message: string }): void {
  ElMessage.error(payload.message)
}

/**
 * 保存成功提示。
 */
function onSaved(): void {
  layoutDirty.value = false
  ElMessage.success('已保存（布局与字段属性已生效，缓存已失效）')
}

/**
 * 新字段创建成功提示。
 *
 * @param result 创建结果。
 */
function onFieldCreated(result: DesignerExtFieldResult): void {
  ElMessage.success(
    result.ddlStatus === 'active'
      ? `字段已生效（${result.columnName}），可拖入布局`
      : `字段已登记（${result.columnName}），建列失败可重试`,
  )
}

/**
 * 工具栏动作。
 *
 * @param key 动作键。
 */
function onToolbarAction(key: string): void {
  if (key === 'refresh') {
    void reload()
    return
  }
  if (key === 'close') {
    void router.push('/')
  }
}

/**
 * 取默认表单（优先「用户」，否则首个业务码）。
 *
 * @returns 业务码（无业务码返回空串）。
 */
function defaultFormCode(): string {
  const codes = businesses.value.map((item) => item.code)
  return codes.includes('user') ? 'user' : (codes[0] ?? '')
}

onMounted(async () => {
  try {
    await meta.ensureBusinesses(true)
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '业务码加载失败')
  }
  try {
    const [rolePage, keys] = await Promise.all([listRoles({ page: 1, size: ROLE_PAGE_SIZE }), listOptionSetKeys()])
    roles.value = (rolePage.list ?? []).map((role) => ({ id: role.id, name: role.name }))
    optionSetKeys.value = keys
  } catch {
    // 角色与选项集为增强项：失败不阻断设计器（角色视图 / 枚举属性各自降级）。
    roles.value = []
    optionSetKeys.value = []
  }
  formCode.value = defaultFormCode()
  await nextTick()
  await reload()
})
</script>

<template>
  <page-container
    title="表单定制"
    description="在线设计表单布局与字段属性：三级层级（平台默认 → 租户覆盖 → 角色视图）、租户自建字段与动态建列"
  >
    <list-toolbar
      :overrides="toolbarOverrides"
      :loading="loading"
      :help="pageHelp"
      :help-fetcher="helpFetcher"
      data-test="form-design-toolbar"
      @action="onToolbarAction"
    />

    <div class="form-design__picker">
      <span class="form-design__label">表单</span>
      <el-select
        :model-value="formCode"
        class="form-design__select"
        placeholder="选择业务码"
        filterable
        data-test="form-design-form"
        @update:model-value="onFormChange"
      >
        <el-option
          v-for="item in businesses"
          :key="item.code"
          :label="`${item.code} · ${item.name}`"
          :value="item.code"
        />
      </el-select>
      <span class="form-design__label">层级</span>
      <el-radio-group :model-value="level" data-test="form-design-level" @update:model-value="onLevelChange">
        <el-radio-button value="platform">平台默认</el-radio-button>
        <el-radio-button value="tenant">租户覆盖</el-radio-button>
        <el-radio-button value="role">角色视图</el-radio-button>
      </el-radio-group>
      <template v-if="level === 'role'">
        <span class="form-design__label">角色</span>
        <el-select
          :model-value="roleId"
          class="form-design__select"
          placeholder="选择角色"
          data-test="form-design-role"
          @update:model-value="onRoleChange"
        >
          <el-option v-for="item in roles" :key="item.id" :label="item.name" :value="item.id" />
        </el-select>
      </template>
      <span v-if="loading" class="form-design__hint" data-test="form-design-loading">载入中…</span>
      <span v-if="dirtyHint" class="form-design__dirty" data-test="form-design-dirty">
        ● {{ attrsDirty ? '字段属性有未保存修改' : '布局有未保存修改' }}
      </span>
      <el-tag v-if="levelReadonly" type="info" size="small" data-test="form-design-readonly">
        平台默认层级只读
      </el-tag>
    </div>

    <p v-if="!canManage" class="form-design__hint" data-test="form-design-no-perm">
      当前账号无表单定制维护权限（formdesign:manage），仅可查看布局
    </p>

    <form-designer
      v-if="formCode !== ''"
      :key="loadToken"
      :ready="ready"
      :form-code="formCode"
      :level="level"
      :role-id="roleId"
      :fields="fields"
      :jobs="jobs"
      :read-only="!canManage"
      :registered-types="[...EXT_FIELD_TYPES]"
      data-test="form-design-canvas"
      @select="onSelect"
      @change="onChange"
      @saved="onSaved"
      @failed="onFailed"
      @field-created="onFieldCreated"
    >
      <template #properties>
        <field-attr-panel
          :field="selectedField"
          :attrs="selectedAttrs"
          :option-sets="optionSetKeys"
          :disabled="panelDisabled"
          @change="onAttrChange"
          @remove-rule="onRemoveRule"
        />
      </template>
    </form-designer>
    <p v-else class="form-design__hint" data-test="form-design-no-form">暂无可用业务码，无法进入设计器</p>
  </page-container>
</template>

<style scoped>
.form-design__picker {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.form-design__label {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.form-design__select {
  width: 220px;
}

.form-design__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.form-design__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-warning);
}
</style>
