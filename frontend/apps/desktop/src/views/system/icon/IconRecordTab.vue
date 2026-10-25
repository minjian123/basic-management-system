<script setup lang="ts">
// 自定义图标记录页签：两子页签「详细信息 / 系统信息」。
// 图标键 kebab-case 唯一、创建后不可修改；icon key = custom:{图标键}（后端派生）；
// 上传仅 SVG（类型白名单 + 大小上限），内容清洗由后端兜底，前端预览不执行脚本。
defineOptions({ name: 'IconRecordTab' })

import { DictRecordLayout, MultilingualNameField, type SysInfoData } from '@bms/ui_ep'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onMounted, ref, watch } from 'vue'

import { createIcon, deleteIcon, updateIcon, type IconItem, type IconStatus } from '@/api/icon'
import type { I18nNames } from '@/api/menuMeta'
import { useMenuMetaStore } from '@/stores/menuMeta'

import { ENABLED_LOCALES, currentUserLocale } from '../metaLocale'

const props = defineProps<{
  /** 图标键（新增态为 `new`）。 */
  iconCode: string
}>()

const emit = defineEmits<{
  /** 保存成功。 */
  saved: [item: IconItem]
  /** 删除成功。 */
  removed: []
  /** 脏态同步。 */
  dirty: [dirty: boolean]
  /** 请求关闭。 */
  close: []
}>()

/** 新增态标识。 */
const NEW_KEY = 'new'
/** SVG 大小上限（字节，与后端 `ICON_SVG_MAX_BYTES` 同口径）。 */
const SVG_MAX_BYTES = 100 * 1024
/** 默认分组候选。 */
const DEFAULT_CATEGORIES = ['菜单', '通用', '媒体', '财务', '其他']
/** 新建图标默认分组。 */
const DEFAULT_CATEGORY = '菜单'

const meta = useMenuMetaStore()

/** 当前子页签。 */
const section = ref('detail')
/** 当前登录用户语言。 */
const userLocale = ref(currentUserLocale())
/** 是否新增态。 */
const isNew = computed(() => props.iconCode === NEW_KEY)
/** 是否编辑态。 */
const editing = ref(false)
/** 图标详情。 */
const detail = ref<IconItem | null>(null)
/** 载入中。 */
const loading = ref(false)
/** 保存中。 */
const saving = ref(false)
/** 图标键草稿。 */
const code = ref('')
/** 分组草稿。 */
const category = ref('')
/** 名称草稿。 */
const names = ref<I18nNames>({})
/** 标签草稿（逗号分隔）。 */
const tagsText = ref('')
/** SVG 内容。 */
const svg = ref('')
/** 已上传文件名（展示）。 */
const svgName = ref('')
/** 状态草稿。 */
const status = ref<IconStatus>('active')
/** 载入基线指纹。 */
const baseline = ref('')

/**
 * 解析标签（中英文逗号分隔、去重）。
 *
 * @param text 标签文本。
 * @returns 标签清单。
 */
function parseTags(text: string): string[] {
  return [...new Set(text.split(/[,，]/).map((item) => item.trim()).filter((item) => item !== ''))]
}

/**
 * 草稿指纹。
 *
 * @returns 指纹。
 */
function fingerprint(): string {
  return JSON.stringify({
    code: code.value.trim(),
    category: category.value.trim(),
    status: status.value,
    tags: parseTags(tagsText.value),
    svg: svg.value,
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

/** 分组候选（默认 + 已存在图标分组）。 */
const categoryOptions = computed(() => [...new Set([...DEFAULT_CATEGORIES, ...meta.icons.map((item) => item.category)])])
/** SVG 预览（data URI，`<img>` 内不执行脚本）。 */
const previewSrc = computed(() =>
  svg.value.trim() === '' ? '' : `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg.value)}`,
)
/** 系统信息。 */
const sysInfo = computed<SysInfoData>(() => ({
  id: detail.value?.id ?? '—',
  version: null,
  createdBy: null,
  createdAt: null,
  updatedBy: null,
  updatedAt: null,
  formKey: 'icon',
  formLabel: '自定义图标',
}))

/**
 * 载入图标记录。
 */
async function load(): Promise<void> {
  loading.value = true
  editing.value = false
  try {
    await meta.ensureIcons(true)
    if (isNew.value) {
      detail.value = null
      code.value = ''
      category.value = DEFAULT_CATEGORY
      names.value = {}
      tagsText.value = ''
      svg.value = ''
      svgName.value = ''
      status.value = 'active'
      baseline.value = fingerprint()
      editing.value = true
      return
    }
    const row = meta.icons.find((item) => item.code === props.iconCode)
    if (row === undefined) {
      detail.value = null
      ElMessage.error('图标不存在或已删除')
      return
    }
    detail.value = row
    code.value = row.code
    category.value = row.category
    names.value = { ...row.i18n }
    tagsText.value = row.tags.join(',')
    svg.value = row.svg
    svgName.value = `${row.code}.svg`
    status.value = row.status
    baseline.value = fingerprint()
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '图标详情加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 读取上传的 SVG 文件（仅类型白名单 + 大小上限，内容清洗归后端）。
 *
 * @param uploadFile 上传件（Element Plus `on-change` 载荷）。
 */
async function onFileChange(uploadFile: { raw?: File; name?: string }): Promise<void> {
  const file = uploadFile.raw
  if (file === undefined) {
    return
  }
  const isSvg = file.type === 'image/svg+xml' || (uploadFile.name ?? file.name).toLowerCase().endsWith('.svg')
  if (!isSvg) {
    ElMessage.error('仅支持 SVG 文件')
    return
  }
  if (file.size > SVG_MAX_BYTES) {
    ElMessage.error('SVG 文件超过 100KB 上限')
    return
  }
  try {
    svg.value = await file.text()
    svgName.value = uploadFile.name ?? file.name
  } catch {
    ElMessage.error('SVG 文件读取失败')
  }
}

/**
 * 保存（新增 POST / 编辑 PUT）。
 */
async function save(): Promise<void> {
  const trimmedCode = code.value.trim()
  if (!/^[a-z][a-z0-9-]*$/.test(trimmedCode)) {
    ElMessage.error('图标键须小写字母开头，仅含小写字母 / 数字 / 连字符')
    return
  }
  if (category.value.trim() === '') {
    ElMessage.error('图标分组必填')
    return
  }
  if ((names.value[userLocale.value] ?? '').trim() === '') {
    ElMessage.error(`名称（${userLocale.value}）不能为空`)
    return
  }
  if (svg.value.trim() === '') {
    ElMessage.error('请上传 SVG 图标内容')
    return
  }
  if (new TextEncoder().encode(svg.value).length > SVG_MAX_BYTES) {
    ElMessage.error('SVG 内容超过 100KB 上限')
    return
  }
  saving.value = true
  try {
    const name = (names.value[userLocale.value] as string).trim()
    const tags = parseTags(tagsText.value)
    const saved = isNew.value
      ? await createIcon({
          code: trimmedCode,
          name,
          category: category.value.trim(),
          tags,
          svg: svg.value,
          i18n: names.value,
        })
      : await updateIcon(props.iconCode, {
          name,
          category: category.value.trim(),
          tags,
          svg: svg.value,
          status: status.value,
          i18n: names.value,
        })
    if (isNew.value) {
      ElMessage.success('图标已创建')
    } else {
      await meta.ensureIcons(true)
      const row = meta.icons.find((item) => item.code === props.iconCode)
      if (row !== undefined) {
        detail.value = row
        baseline.value = fingerprint()
      }
      ElMessage.success('图标已保存')
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
    category.value = DEFAULT_CATEGORY
    names.value = {}
    tagsText.value = ''
    svg.value = ''
    svgName.value = ''
    status.value = 'active'
    baseline.value = fingerprint()
    editing.value = true
    return
  }
  if (detail.value !== null) {
    code.value = detail.value.code
    category.value = detail.value.category
    names.value = { ...detail.value.i18n }
    tagsText.value = detail.value.tags.join(',')
    svg.value = detail.value.svg
    svgName.value = `${detail.value.code}.svg`
    status.value = detail.value.status
  }
  baseline.value = fingerprint()
  editing.value = false
}

/**
 * 删除图标（被菜单引用时 `40206`）。
 */
async function remove(): Promise<void> {
  if (isNew.value) {
    return
  }
  try {
    await ElMessageBox.confirm('删除图标后引用处将降级显示，确认删除？', '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteIcon(props.iconCode)
    emit('removed')
    ElMessage.success('图标已删除')
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '删除失败')
  }
}

watch(
  () => props.iconCode,
  () => {
    void load()
  },
)

onMounted(() => {
  userLocale.value = currentUserLocale()
  void load()
})

defineExpose({ save, load, remove, onFileChange })
</script>

<template>
  <div data-test="icon-record">
    <dict-record-layout v-model="section" :info="sysInfo" :disabled="!editing">
      <template #toolbar>
        <template v-if="editing">
          <el-button type="primary" :loading="saving" data-test="icon-record-save" @click="save">保存</el-button>
          <el-button data-test="icon-record-cancel" @click="cancel">取消</el-button>
        </template>
        <template v-else>
          <el-button type="primary" data-test="icon-record-edit" @click="editing = true">修改</el-button>
          <el-button type="danger" plain data-test="icon-record-delete" @click="remove">删除</el-button>
          <el-button data-test="icon-record-refresh" @click="load">刷新</el-button>
        </template>
        <el-button data-test="icon-record-close" @click="emit('close')">关闭</el-button>
        <span class="icon-record__side">
          <span v-if="loading" class="icon-record__hint" data-test="icon-record-loading">载入中…</span>
          <span v-if="dirty" class="icon-record__dirty" data-test="icon-record-dirty">● 有未保存变更</span>
        </span>
      </template>

      <template #first-row>
        <el-col :span="8">
          <el-form-item label="图标键" required>
            <el-input v-model="code" :disabled="!isNew" placeholder="kebab-case，如 receipt" data-test="icon-record-code" />
            <div class="icon-record__hint">icon key = <code>custom:{{ code || '…' }}</code>；创建后不可修改</div>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="名称" required>
            <multilingual-name-field
              :model-value="names"
              :locales="ENABLED_LOCALES"
              :user-locale="userLocale"
              required
              data-test="icon-record-name"
              @change="applyNames"
            />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="状态">
            <el-switch
              :model-value="status === 'active'"
              active-text="启用"
              inactive-text="停用"
              data-test="icon-record-status"
              @update:model-value="(value: boolean) => (status = value ? 'active' : 'disabled')"
            />
            <div class="icon-record__hint">停用后不在选择器候选与渲染清单中出现，已引用处按降级处理</div>
          </el-form-item>
        </el-col>
      </template>

      <template #fields>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="分组">
              <el-select
                v-model="category"
                filterable
                allow-create
                default-first-option
                placeholder="选择或输入分组"
                style="width: 100%"
                data-test="icon-record-category"
              >
                <el-option v-for="item in categoryOptions" :key="item" :label="item" :value="item" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="16">
            <el-form-item label="标签">
              <el-input v-model="tagsText" placeholder="逗号分隔，如 票据,报销" data-test="icon-record-tags" />
              <div class="icon-record__hint">标签用于图标选择器搜索（支持中文别名）</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="图标内容（SVG）">
              <div class="icon-record__svg">
                <div class="icon-record__preview-box">
                  <img
                    v-if="previewSrc !== ''"
                    :src="previewSrc"
                    class="icon-record__preview"
                    alt=""
                    data-test="icon-record-preview"
                  />
                  <span v-else class="icon-record__placeholder" data-test="icon-record-preview-empty">？</span>
                </div>
                <div class="icon-record__upload">
                  <el-upload
                    :auto-upload="false"
                    :show-file-list="false"
                    accept=".svg,image/svg+xml"
                    :disabled="!editing"
                    :on-change="onFileChange"
                    data-test="icon-record-upload"
                  >
                    <el-button :disabled="!editing">上传 SVG</el-button>
                  </el-upload>
                  <span class="icon-record__hint">当前：{{ svgName || '未上传' }}</span>
                  <div class="icon-record__hint">
                    仅 SVG（类型白名单）、大小上限 100KB；内容清洗（移除脚本 / 事件属性 / 外链）由后端兜底
                  </div>
                </div>
              </div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="24">
            <el-form-item label="说明">
              <span class="icon-record__hint">
                平台官方图标（<code>el:</code>）与业务自绘图标（<code>biz:</code>）随代码发布、不落表，本页仅维护租户自定义图标
              </span>
            </el-form-item>
          </el-col>
        </el-row>
      </template>
    </dict-record-layout>
  </div>
</template>

<style scoped>
.icon-record__side {
  margin-left: auto;
}

.icon-record__dirty {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.icon-record__hint {
  margin-top: var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}

.icon-record__svg {
  display: flex;
  gap: var(--bms-space-4);
  align-items: flex-start;
}

.icon-record__preview-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  background: var(--bms-color-fill);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.icon-record__preview {
  width: 48px;
  height: 48px;
}

.icon-record__placeholder {
  font-size: var(--bms-font-size-xl);
  color: var(--bms-color-text-secondary);
}

.icon-record__upload {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
}
</style>
