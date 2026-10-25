<script setup lang="ts">
// 菜单记录页签：三子页签「详细信息 / 挂接配置 / 系统信息」，工具栏**单一保存**（本体 + 表单挂接 + 按钮 + 字段）。
// 对照原型《10_菜单管理/03_菜单表单页.html》；字段权限入口已按决策删除（统一在角色管理授予）。
defineOptions({ name: 'MenuRecordTab' })

import { DictRecordLayout, type SysInfoData } from '@bms/ui_ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import {
  createButton,
  createField,
  createMenu,
  deleteButton,
  deleteField,
  deleteMenu,
  listButtons,
  listFields,
  updateButton,
  updateField,
  updateForm,
  updateMenu,
  type ButtonItem,
  type FieldItem,
  type FormItem,
  type I18nNames,
  type MenuItem,
} from '@/api/menuMeta'
import { useMenuMetaStore } from '@/stores/menuMeta'

import MenuDetailSection from './MenuDetailSection.vue'
import MenuLinkSection from './MenuLinkSection.vue'
import {
  diffButtons,
  diffFields,
  linkFingerprint,
  toButtonPayload,
  toFieldPayload,
  validateButtons,
  validateFields,
  type ButtonDraft,
  type FieldDraft,
} from './linkDraft'
import { menuFingerprint, toMenuPayload, validateMenuDraft, type MenuDraft } from './menuDraft'
import { findMenu, nextSort, toMenuTreeOptions } from './menuTree'
import { currentUserLocale } from '../metaLocale'

const props = defineProps<{
  /** 菜单主键（新增态为 `new`）。 */
  menuId: string
}>()

const emit = defineEmits<{
  /** 保存成功（视图侧刷新列表 / 换页签）。 */
  saved: [menu: MenuItem]
  /** 删除成功（视图侧关闭页签并刷新列表）。 */
  removed: []
  /** 脏态同步。 */
  dirty: [dirty: boolean]
  /** 请求关闭（视图侧走脏数据拦截）。 */
  close: []
}>()

/** 新增态标识（记录页签键 `record:new`）。 */
const NEW_KEY = 'new'

const meta = useMenuMetaStore()

/** 当前子页签（`detail` / `attach` / `sys`）。 */
const section = ref('detail')
/** 当前登录用户语言（必填语言）。 */
const userLocale = ref(currentUserLocale())
/** 是否新增态。 */
const isNew = computed(() => props.menuId === NEW_KEY)
/** 是否编辑态（查看 ⇄ 编辑分态）。 */
const editing = ref(false)
/** 菜单详情（查看态数据源；新增态为空）。 */
const detail = ref<MenuItem | null>(null)
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 本体草稿。 */
const form = ref<MenuDraft>(emptyDraft())
/** 本体载入基线。 */
const baselineForm = ref<MenuDraft>(emptyDraft())
/** 关联表单 ID（草稿）。 */
const linkFormIds = ref<string[]>([])
/** 关联表单载入基线。 */
const originalFormIds = ref<string[]>([])
/** 按钮草稿（表单 ID → 行）。 */
const buttons = ref<Record<string, ButtonDraft[]>>({})
/** 字段草稿（表单 ID → 行）。 */
const fields = ref<Record<string, FieldDraft[]>>({})
/** 按钮载入基线（表单 ID → 行）。 */
const baselineButtons = ref<Record<string, ButtonDraft[]>>({})
/** 字段载入基线（表单 ID → 行）。 */
const baselineFields = ref<Record<string, FieldDraft[]>>({})
/** 本体基线指纹。 */
const baselineMenuPrint = ref('')
/** 挂接配置基线指纹。 */
const baselineLinkPrint = ref('')

/** 父级下拉选项（编辑态排除自身子树）。 */
const parentOptions = computed(() => toMenuTreeOptions(meta.menus, isNew.value ? undefined : props.menuId))

/** 是否存在未保存变更（本体 + 挂接配置）。 */
const dirty = computed(
  () =>
    menuFingerprint(form.value) !== baselineMenuPrint.value ||
    linkFingerprint(linkFormIds.value, buttons.value, fields.value) !== baselineLinkPrint.value,
)

/** 系统信息。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: null,
  createdBy: null,
  createdAt: null,
  updatedBy: null,
  updatedAt: null,
  formKey: 'menu',
  formLabel: '菜单管理',
}))

watch(dirty, (value) => emit('dirty', value))

// 新增态切换父级时按同级重算排序（排序只读，由列表拖拽 / 新建落位决定）
watch(
  () => form.value.parent_id,
  (parentId) => {
    if (editing.value && isNew.value) {
      form.value.sort = nextSort(meta.menus, parentId)
    }
  },
)

// 新关联表单：按需拉取按钮 / 字段明细（已有草稿不覆盖）
watch(linkFormIds, (ids) => {
  if (!editing.value) {
    return
  }
  const missing = ids.filter((id) => buttons.value[id] === undefined)
  if (missing.length > 0) {
    void fetchLinkDetails(missing)
  }
})

/**
 * 空本体草稿。
 *
 * @returns 草稿。
 */
function emptyDraft(): MenuDraft {
  return {
    parent_id: '0',
    path: '',
    component: '',
    icon: '',
    sort: 0,
    hidden: false,
    status: 'enabled',
    i18n: {},
  }
}

/**
 * 契约菜单节点 → 本体草稿。
 *
 * @param node 菜单节点。
 * @returns 草稿。
 */
function toDraft(node: MenuItem): MenuDraft {
  return {
    parent_id: node.parent_id,
    path: node.path,
    component: node.component ?? '',
    icon: node.icon ?? '',
    sort: node.sort,
    hidden: node.hidden,
    status: node.status === 'disabled' ? 'disabled' : 'enabled',
    i18n: { ...(node.i18n as I18nNames) },
  }
}

/**
 * 复制本体草稿。
 *
 * @param draft 草稿。
 * @returns 副本。
 */
function cloneDraft(draft: MenuDraft): MenuDraft {
  return { ...draft, i18n: { ...draft.i18n } }
}

/**
 * 契约按钮行 → 草稿。
 *
 * @param item 按钮行。
 * @returns 草稿。
 */
function toButtonDraft(item: ButtonItem): ButtonDraft {
  return {
    id: item.id,
    form_id: item.form_id,
    permission_id: item.permission_id,
    name: item.name,
    type: item.type === 'interface' ? 'interface' : 'toolbar',
    sort: item.sort,
    status: item.status === 'disabled' ? 'disabled' : 'enabled',
  }
}

/**
 * 契约字段行 → 草稿。
 *
 * @param item 字段行。
 * @returns 草稿。
 */
function toFieldDraft(item: FieldItem): FieldDraft {
  return {
    id: item.id,
    form_id: item.form_id,
    field_key: item.field_key,
    type: item.type,
    sort: item.sort,
    status: item.status === 'disabled' ? 'disabled' : 'enabled',
    i18n: { ...(item.i18n as I18nNames) },
  }
}

/**
 * 复制按钮草稿映射。
 *
 * @param source 源映射。
 * @returns 副本。
 */
function cloneButtons(source: Record<string, ButtonDraft[]>): Record<string, ButtonDraft[]> {
  const result: Record<string, ButtonDraft[]> = {}
  for (const key of Object.keys(source)) {
    result[key] = (source[key] as ButtonDraft[]).map((row) => ({ ...row }))
  }
  return result
}

/**
 * 复制字段草稿映射。
 *
 * @param source 源映射。
 * @returns 副本。
 */
function cloneFields(source: Record<string, FieldDraft[]>): Record<string, FieldDraft[]> {
  const result: Record<string, FieldDraft[]> = {}
  for (const key of Object.keys(source)) {
    result[key] = (source[key] as FieldDraft[]).map((row) => ({ ...row, i18n: { ...row.i18n } }))
  }
  return result
}

/**
 * 拉取若干表单的按钮 / 字段明细并写入草稿与基线。
 *
 * @param formIds 表单 ID 清单。
 */
async function fetchLinkDetails(formIds: readonly string[]): Promise<void> {
  await Promise.all(
    formIds.map(async (formId) => {
      const [buttonList, fieldList] = await Promise.all([listButtons(formId), listFields(formId)])
      buttons.value[formId] = (buttonList.items ?? []).map(toButtonDraft)
      fields.value[formId] = (fieldList.items ?? []).map(toFieldDraft)
      baselineButtons.value[formId] = (buttons.value[formId] as ButtonDraft[]).map((row) => ({ ...row }))
      baselineFields.value[formId] = (fields.value[formId] as FieldDraft[]).map((row) => ({
        ...row,
        i18n: { ...row.i18n },
      }))
    }),
  )
}

/**
 * 记录载入基线指纹。
 */
function captureBaseline(): void {
  baselineMenuPrint.value = menuFingerprint(form.value)
  baselineLinkPrint.value = linkFingerprint(linkFormIds.value, buttons.value, fields.value)
}

/**
 * 初始化新增态。
 */
function setupNew(): void {
  const draft = emptyDraft()
  draft.sort = nextSort(meta.menus, '0')
  detail.value = null
  form.value = draft
  baselineForm.value = cloneDraft(draft)
  linkFormIds.value = []
  originalFormIds.value = []
  buttons.value = {}
  fields.value = {}
  baselineButtons.value = {}
  baselineFields.value = {}
  captureBaseline()
  editing.value = true
}

/**
 * 载入菜单记录（含元数据清单与挂接明细）。
 */
async function load(): Promise<void> {
  loading.value = true
  editing.value = false
  try {
    await Promise.all([
      meta.ensureMenus(true),
      meta.ensureForms(true),
      meta.ensureBusinesses(),
      meta.ensurePermissions(),
      meta.ensureIcons(),
    ])
    if (isNew.value) {
      setupNew()
      return
    }
    const node = findMenu(meta.menus, props.menuId)
    if (node === undefined) {
      detail.value = null
      ElMessage.error('菜单不存在或已删除')
      return
    }
    detail.value = node
    form.value = toDraft(node)
    baselineForm.value = cloneDraft(form.value)
    originalFormIds.value = meta.forms
      .filter((item: FormItem) => (item.menu_ids ?? []).map(String).includes(props.menuId))
      .map((item) => item.id)
    linkFormIds.value = [...originalFormIds.value]
    buttons.value = {}
    fields.value = {}
    baselineButtons.value = {}
    baselineFields.value = {}
    await fetchLinkDetails(originalFormIds.value)
    captureBaseline()
    editing.value = false
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '菜单详情加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 保存前本地校验（后端仍为唯一裁决方）。
 *
 * @returns 错误文案；通过返回 `undefined`。
 */
function validate(): string | undefined {
  const menuError = validateMenuDraft(form.value, userLocale.value)
  if (menuError !== undefined) {
    return menuError
  }
  for (const formId of linkFormIds.value) {
    const buttonError = validateButtons(buttons.value[formId] ?? [])
    if (buttonError !== undefined) {
      return buttonError
    }
    const fieldError = validateFields(fields.value[formId] ?? [])
    if (fieldError !== undefined) {
      return fieldError
    }
  }
  return undefined
}

/**
 * 保存表单挂接关系（按差异全量替换受影响表单的 `menu_ids`）。
 *
 * @param menuId 菜单主键。
 */
async function saveFormLinks(menuId: string): Promise<void> {
  const original = new Set(originalFormIds.value)
  const current = new Set(linkFormIds.value)
  for (const formId of new Set([...original, ...current])) {
    const had = original.has(formId)
    const has = current.has(formId)
    if (had === has) {
      continue
    }
    const form = meta.forms.find((item) => item.id === formId)
    if (form === undefined) {
      continue
    }
    const menuIds = new Set((form.menu_ids ?? []).map(String))
    if (has) {
      menuIds.add(menuId)
    } else {
      menuIds.delete(menuId)
    }
    await updateForm(formId, {
      menu_ids: [...menuIds],
      business_id: form.business_id,
      component: form.component ?? null,
      status: form.status === 'disabled' ? 'disabled' : 'enabled',
    })
  }
}

/**
 * 保存按钮 / 字段明细（按差异删除 → 更新 → 新增）。
 */
async function saveLinkDetails(): Promise<void> {
  for (const formId of linkFormIds.value) {
    const buttonDiff = diffButtons(
      baselineButtons.value[formId] as ButtonDraft[],
      buttons.value[formId] as ButtonDraft[],
    )
    for (const id of buttonDiff.deleted) {
      await deleteButton(id)
    }
    for (const row of buttonDiff.updated) {
      await updateButton(row.id as string, toButtonPayload(row, false))
    }
    for (const row of buttonDiff.created) {
      await createButton(toButtonPayload(row, true))
    }

    const fieldDiff = diffFields(
      baselineFields.value[formId] as FieldDraft[],
      fields.value[formId] as FieldDraft[],
    )
    for (const id of fieldDiff.deleted) {
      await deleteField(id)
    }
    for (const row of fieldDiff.updated) {
      await updateField(row.id as string, toFieldPayload(row, false))
    }
    for (const row of fieldDiff.created) {
      await createField(toFieldPayload(row, true))
    }
  }
}

/**
 * 工具栏单一保存：本体 + 表单挂接 + 按钮 + 字段一次提交（任一步失败即停止并保留草稿）。
 */
async function save(): Promise<void> {
  const error = validate()
  if (error !== undefined) {
    ElMessage.error(error)
    return
  }
  saving.value = true
  const payload = toMenuPayload(form.value)
  try {
    const saved = isNew.value ? await createMenu(payload) : await updateMenu(props.menuId, payload)
    await saveFormLinks(saved.id)
    await saveLinkDetails()
    if (isNew.value) {
      ElMessage.success('菜单已创建')
    } else {
      await load()
      ElMessage.success('菜单已保存')
    }
    emit('saved', saved)
  } catch (caught: unknown) {
    ElMessage.error(caught instanceof Error ? caught.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/**
 * 撤销未保存变更（恢复载入基线；新增态恢复为空草稿）。
 */
function cancel(): void {
  form.value = cloneDraft(baselineForm.value)
  linkFormIds.value = [...originalFormIds.value]
  buttons.value = cloneButtons(baselineButtons.value)
  fields.value = cloneFields(baselineFields.value)
  editing.value = false
  if (isNew.value) {
    setupNew()
  }
}

/**
 * 删除当前菜单（被引用时后端 `40206`；成功后由视图关闭页签）。
 */
async function remove(): Promise<void> {
  if (isNew.value) {
    return
  }
  try {
    await ElMessageBox.confirm('删除菜单后其入口与挂接关系将不可用，确认删除？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteMenu(props.menuId)
    emit('removed')
    ElMessage.success('菜单已删除')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

watch(
  () => props.menuId,
  () => {
    void load()
  },
)

onMounted(() => {
  userLocale.value = currentUserLocale()
  void load()
})

defineExpose({ save, load, remove, validate, isDirty: (): boolean => dirty.value })
</script>

<template>
  <div data-test="menu-record">
    <dict-record-layout v-model="section" :info="sysInfo" :disabled="!editing">
      <template #toolbar>
        <template v-if="editing">
          <el-button type="primary" :loading="saving" data-test="menu-record-save" @click="save">保存</el-button>
          <el-button data-test="menu-record-cancel" @click="cancel">取消</el-button>
        </template>
        <template v-else>
          <el-button type="primary" data-test="menu-record-edit" @click="editing = true">修改</el-button>
          <el-button type="danger" plain data-test="menu-record-delete" @click="remove">删除</el-button>
          <el-button data-test="menu-record-refresh" @click="load">刷新</el-button>
        </template>
        <el-button data-test="menu-record-close" @click="emit('close')">关闭</el-button>
        <span class="menu-record__side">
          <span v-if="loading" class="menu-record__hint" data-test="menu-record-loading">载入中…</span>
          <span v-if="dirty" class="menu-record__dirty" data-test="menu-record-dirty">● 有未保存变更</span>
        </span>
      </template>

      <template #first-row>
        <el-col :span="24">
          <menu-detail-section
            v-model:form="form"
            :parent-options="parentOptions"
            :user-locale="userLocale"
            :editing="editing"
          />
        </el-col>
      </template>

      <template #extra-tabs>
        <el-tab-pane label="挂接配置" name="attach">
          <menu-link-section
            v-model:form-ids="linkFormIds"
            v-model:buttons="buttons"
            v-model:fields="fields"
            :editing="editing"
            :forms="meta.forms"
            :businesses="meta.businesses"
            :permissions="meta.permissions"
            :user-locale="userLocale"
          />
        </el-tab-pane>
      </template>
    </dict-record-layout>
  </div>
</template>

<style scoped>
.menu-record__side {
  margin-left: auto;
}

.menu-record__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.menu-record__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}
</style>
