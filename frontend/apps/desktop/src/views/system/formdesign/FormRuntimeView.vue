<script setup lang="ts">
// 表单运行时页（10_02）：按生效布局渲染表单（新增 / 编辑 / 查看）+ 列表页查询区消费 + 明细列消费。
// 本页是「布局 → 渲染器 → 查询区 → 明细列」整条链路的验收载体与产品接入样板：真实业务页按同一形状接入（归阶段十五）。
import type { FilterField, FormRenderMode, LayoutEffective } from '@bms/core'
import { formQueryFields, normalizeLayout } from '@bms/core'
import type { ToolbarAction, ToolbarActionOverride } from '@bms/core'
import { FormRenderer, FormToolbar, PageContainer, QueryFilter } from '@bms/ui_ep'
import type { QueryFilterSearchPayload } from '@bms/ui_ep'
import { ElMessage } from 'element-plus'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getEffectiveLayout, toEffectiveLayout, validateForm } from '@/api/formDesign'
import { usePageHelpContext } from '@/composables/usePageHelpContext'
import { useMenuMetaStore } from '@/stores/menuMeta'

defineOptions({ name: 'SystemFormRuntime' })

/** 三态选项。 */
const MODES: { value: FormRenderMode; label: string }[] = [
  { value: 'create', label: '新增' },
  { value: 'edit', label: '编辑' },
  { value: 'view', label: '查看' },
]

const router = useRouter()
const meta = useMenuMetaStore()

/** 页面帮助上下文（无锚点时不显示帮助入口）。 */
const { help: pageHelp, fetcher: helpFetcher } = usePageHelpContext()

/** 业务码清单（表单选择器）。 */
const businesses = computed(() => meta.businesses)
/** 选中表单（业务码）。 */
const formCode = ref('')
/** 三态。 */
const mode = ref<FormRenderMode>('create')
/** 记录主键（编辑 / 查看）。 */
const recordId = ref('')
/** 生效布局（渲染器输入）。 */
const effective = ref<LayoutEffective | undefined>(undefined)
/** 记录数据（受控）。 */
const model = ref<Record<string, unknown>>({})
/** 载入中。 */
const loading = ref(false)
/** 最近一次查询参数（列表页查询区消费证据）。 */
const lastParams = ref<Record<string, unknown> | undefined>(undefined)

/** 渲染器实例（校验与提交编排）。 */
const rendererRef = ref<InstanceType<typeof FormRenderer> | null>(null)

/** 是否只读（查看态）。 */
const readonly = computed(() => mode.value === 'view')
/** 查询区字段声明（布局查询区 → 既有查询筛选件）。 */
const queryFields = computed<FilterField[]>(() =>
  effective.value === undefined
    ? []
    : formQueryFields({
        layout: effective.value.layout,
        fields: effective.value.fields,
        optionSets: effective.value.optionSets,
      }),
)
/** 明细列（布局明细区；列宽与列序消费）。 */
const detailColumns = computed(() => normalizeLayout(effective.value?.layout).detail?.columns ?? [])
/** 字段名映射（明细列标题与查询参数预览用）。 */
const fieldLabels = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const field of effective.value?.fields ?? []) {
    map[field.key] = field.label
  }
  return map
})
/** 生效来源文案。 */
const sourceText = computed(() => {
  const source = effective.value?.source ?? 'empty'
  return { role: '角色视图', tenant: '租户覆盖', platform: '平台默认', empty: '空布局回退' }[source]
})

/** 工具栏覆盖（保留编辑 / 提交 / 重置 / 重新载入 / 关闭，隐藏删除）。 */
const toolbarOverrides: ToolbarActionOverride[] = [
  { key: 'edit', label: '编辑', order: 10 },
  { key: 'save', label: '提交', order: 20 },
  { key: 'cancel', label: '重置', order: 30 },
  { key: 'delete', hidden: true },
  { key: 'refresh', label: '重新载入', order: 40 },
  { key: 'close', label: '关闭', order: 50 },
]
/** 工具栏扩展动作（校验自测）。 */
const toolbarActions: ToolbarAction[] = [
  { key: 'validate', label: '校验自测', group: 'right', order: 60, testId: 'form-runtime-validate' },
]

/**
 * 载入生效布局。
 */
async function load(): Promise<void> {
  if (formCode.value === '') {
    return
  }
  loading.value = true
  try {
    const response = await getEffectiveLayout(formCode.value)
    effective.value = toEffectiveLayout(response)
    lastParams.value = undefined
    model.value = {}
  } catch (error: unknown) {
    effective.value = undefined
    ElMessage.error(error instanceof Error ? error.message : '生效布局加载失败')
  } finally {
    loading.value = false
  }
}

/**
 * 切换表单（重载生效布局）。
 *
 * @param next 业务码。
 */
function onFormChange(next: string): void {
  if (next === formCode.value) {
    return
  }
  formCode.value = next
  void load()
}

/**
 * 切换三态（编辑 / 查看需记录主键）。
 *
 * @param next 三态。
 */
function onModeChange(next: string | number | boolean | undefined): void {
  const target = next as FormRenderMode
  if (target !== 'create' && recordId.value === '') {
    ElMessage.warning('编辑 / 查看态需先填写记录主键')
    return
  }
  mode.value = target
}

/**
 * 查询区搜索（消费结果：参数与折叠口径由既有筛选件产出）。
 *
 * @param payload 查询载荷。
 */
function onSearch(payload: QueryFilterSearchPayload): void {
  lastParams.value = payload.params
}

/**
 * 提交（本页未接业务写接口，仅提示事件已上抛）。
 *
 * @param _value 提交值。
 */
function onSubmit(_value: Record<string, unknown>): void {
  void _value
  ElMessage.warning('本页未接入业务提交接口：真实业务页注入 jobs.submit 后即写库（样板页只做布局消费）')
}

/**
 * 工具栏动作。
 *
 * @param key 动作键。
 */
async function onToolbarAction(key: string): Promise<void> {
  if (key === 'refresh') {
    await load()
    return
  }
  if (key === 'close') {
    void router.push('/')
    return
  }
  if (key === 'edit') {
    onModeChange('edit')
    return
  }
  if (key === 'cancel') {
    rendererRef.value?.reset()
    model.value = {}
    return
  }
  if (key === 'save') {
    rendererRef.value?.submit()
    return
  }
  if (key === 'validate') {
    await runValidate()
  }
}

/**
 * 校验自测（与业务接口同源的动态校验端点）。
 */
async function runValidate(): Promise<void> {
  if (formCode.value === '') {
    return
  }
  try {
    const result = await validateForm(formCode.value, model.value)
    if (result.valid) {
      ElMessage.success('校验通过')
      return
    }
    const first = result.errors?.[0]
    ElMessage.error(
      first === undefined ? '校验未通过' : `校验未通过：${fieldLabels.value[first.field_key] ?? first.field_key}（${first.rule}）`,
    )
  } catch (error: unknown) {
    ElMessage.error(error instanceof Error ? error.message : '校验请求失败')
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
  formCode.value = defaultFormCode()
  await nextTick()
  await load()
})
</script>

<template>
  <page-container
    title="表单运行时"
    description="按生效布局渲染表单（新增 / 编辑 / 查看），并消费列表页查询区与明细列配置"
  >
    <form-toolbar
      :overrides="toolbarOverrides"
      :actions="toolbarActions"
      :editing="!readonly"
      :loading="loading"
      :help="pageHelp"
      :help-fetcher="helpFetcher"
      data-test="form-runtime-toolbar"
      @action="onToolbarAction"
    />

    <div class="form-runtime__picker">
      <span class="form-runtime__label">表单</span>
      <el-select
        :model-value="formCode"
        class="form-runtime__select"
        placeholder="选择业务码"
        filterable
        data-test="form-runtime-form"
        @update:model-value="onFormChange"
      >
        <el-option
          v-for="item in businesses"
          :key="item.code"
          :label="`${item.code} · ${item.name}`"
          :value="item.code"
        />
      </el-select>
      <span class="form-runtime__label">三态</span>
      <el-radio-group :model-value="mode" data-test="form-runtime-mode" @update:model-value="onModeChange">
        <el-radio-button v-for="item in MODES" :key="item.value" :value="item.value">{{ item.label }}</el-radio-button>
      </el-radio-group>
      <span class="form-runtime__label">记录主键</span>
      <el-input v-model="recordId" class="form-runtime__input" placeholder="编辑 / 查看时填写" data-test="form-runtime-record" />
     <span v-if="loading" class="form-runtime__hint" data-test="form-runtime-loading">载入中…</span>
    </div>

    <p v-if="effective !== undefined" class="form-runtime__source" data-test="form-runtime-source">
      生效来源：{{ sourceText }}{{ effective.fallback ? '（未配置布局，按字段默认栅格渲染）' : ''
      }}{{ effective.readonly ? ' · 渲染路径只读' : '' }}
    </p>
    <p v-if="mode !== 'create' && recordId === ''" class="form-runtime__hint" data-test="form-runtime-record-hint">
      编辑 / 查看态需先填写记录主键；本页未接入记录读接口，数据为空属预期
    </p>

    <section class="form-runtime__section">
      <h4 class="form-runtime__section-title">表单渲染</h4>
      <form-renderer
        v-if="effective !== undefined"
        ref="rendererRef"
        :ready="true"
        :form-code="formCode"
        :mode="mode"
        :meta="effective"
        :model-value="model"
        :record-id="recordId === '' ? undefined : recordId"
        data-test="form-runtime-renderer"
        @update:model-value="(value: Record<string, unknown>) => (model = value)"
        @submit="onSubmit"
        @failed="(payload: { message: string }) => ElMessage.error(payload.message)"
      />
      <p v-else class="form-runtime__hint" data-test="form-runtime-empty">暂无可用布局（先选择业务码或到表单定制页配置布局）</p>
    </section>

    <section class="form-runtime__section">
      <h4 class="form-runtime__section-title">列表页查询区</h4>
      <query-filter
        v-if="queryFields.length > 0"
        :ready="true"
        :fields="queryFields"
        :loading="loading"
        data-test="form-runtime-query"
        @search="onSearch"
      />
      <p v-else class="form-runtime__hint" data-test="form-runtime-query-empty">
        该表单未配置查询区字段（在表单定制的「查询区」勾选字段后生效）
      </p>
      <p v-if="lastParams !== undefined" class="form-runtime__params" data-test="form-runtime-params">
        查询参数：{{ JSON.stringify(lastParams) }}
      </p>
    </section>

    <section class="form-runtime__section">
      <h4 class="form-runtime__section-title">明细区列</h4>
      <el-table
        v-if="detailColumns.length > 0"
        :data="[]"
        border
        data-test="form-runtime-detail-table"
      >
        <el-table-column
          v-for="column in detailColumns"
          :key="column.key"
          :label="fieldLabels[column.key] ?? column.key"
          :width="column.width"
          :min-width="column.width === undefined ? 120 : undefined"
        />
        <template #empty>
          <span data-test="form-runtime-detail-empty">明细列已按布局生成（无明细数据）</span>
        </template>
      </el-table>
      <p v-else class="form-runtime__hint" data-test="form-runtime-detail-none">
        该表单未配置明细区列（仅主从模块需要）
      </p>
    </section>
  </page-container>
</template>

<style scoped>
.form-runtime__picker {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.form-runtime__label {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.form-runtime__select {
  width: 220px;
}

.form-runtime__input {
  width: 180px;
}

.form-runtime__source,
.form-runtime__hint,
.form-runtime__params {
  margin: 0 0 var(--bms-space-2);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.form-runtime__params {
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-xs);
}

.form-runtime__section {
  margin-top: var(--bms-space-4);
}

.form-runtime__section-title {
  margin: 0 0 var(--bms-space-2);
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
}
</style>
