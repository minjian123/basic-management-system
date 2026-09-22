<script setup lang="ts">
// 示例数据表单页：新建 / 编辑分态（按路由 `:id` 判定），含必填与范围校验。
import { NumberInput, PageContainer, RadioInput, SectionContainer, SelectInput, TextInput, TextareaInput } from '@bms/ui-ep'
import type { InputOptions } from '@bms/ui-ep'
import { ElButton, ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useSampleI18n } from '../composables/useSampleI18n'
import {
  SAMPLE_CATEGORIES,
  SAMPLE_PRIORITIES,
  SAMPLE_STATUSES,
  type SampleCategory,
  type SampleInput,
  type SamplePriority,
  type SampleStatus,
} from '../domain'
import { sampleService } from '../services/sample-service'

defineOptions({ name: 'SampleForm' })

const route = useRoute()
const router = useRouter()
const { t } = useSampleI18n()

/** 表单模型。 */
interface FormState {
  name: string
  category: SampleCategory
  priority: SamplePriority
  amount: number | undefined
  owner: string
  status: SampleStatus
  remark: string
}

const id = computed(() => (route.params.id === undefined ? undefined : String(route.params.id)))
const isEdit = computed(() => id.value !== undefined)

const form = reactive<FormState>({
  name: '',
  category: 'software',
  priority: 'normal',
  amount: 0,
  owner: '',
  status: 'draft',
  remark: '',
})

const errors = reactive<{ name: string; amount: string; owner: string }>({ name: '', amount: '', owner: '' })
const loading = ref(false)
const saving = ref(false)

/** 分类选项。 */
const categoryOptions = computed<InputOptions>(() =>
  SAMPLE_CATEGORIES.map((item) => ({ label: t(item.labelKey), value: item.value })),
)
/** 优先级选项。 */
const priorityOptions = computed<InputOptions>(() =>
  SAMPLE_PRIORITIES.map((item) => ({ label: t(item.labelKey), value: item.value })),
)
/** 状态选项。 */
const statusOptions = computed<InputOptions>(() => SAMPLE_STATUSES.map((item) => ({ label: t(item.labelKey), value: item.value })))

/** 编辑态加载记录。 */
async function load(): Promise<void> {
  if (id.value === undefined) {
    return
  }
  loading.value = true
  try {
    const record = await sampleService.get(id.value)
    form.name = record.name
    form.category = record.category
    form.priority = record.priority
    form.amount = record.amount
    form.owner = record.owner
    form.status = record.status
    form.remark = record.remark
  } catch {
    ElMessage.error(t('sample.detail.notFound'))
    void router.push({ name: 'SampleList' })
  } finally {
    loading.value = false
  }
}

/** 校验表单。 */
function validate(): boolean {
  errors.name = form.name.trim() === '' ? t('sample.form.required') : ''
  errors.owner = form.owner.trim() === '' ? t('sample.form.required') : ''
  const amount = form.amount ?? 0
  errors.amount = amount < 0 || amount > 1_000_000 ? t('sample.form.amountRange') : ''
  return errors.name === '' && errors.owner === '' && errors.amount === ''
}

/** 组装入参。 */
function payload(): SampleInput {
  return {
    name: form.name.trim(),
    category: form.category,
    priority: form.priority,
    amount: form.amount ?? 0,
    owner: form.owner.trim(),
    status: form.status,
    remark: form.remark.trim(),
  }
}

/** 提交（新建 / 更新后跳详情）。 */
async function submit(): Promise<void> {
  if (!validate()) {
    return
  }
  saving.value = true
  try {
    const saved = id.value === undefined ? await sampleService.create(payload()) : await sampleService.update(id.value, payload())
    ElMessage.success(t('sample.form.saved'))
    void router.push({ name: 'SampleDetail', params: { id: saved.id } })
  } catch {
    ElMessage.error(t('sample.form.saveFailed'))
  } finally {
    saving.value = false
  }
}

/** 取消返回。 */
function cancel(): void {
  if (id.value === undefined) {
    void router.push({ name: 'SampleList' })
  } else {
    void router.push({ name: 'SampleDetail', params: { id: id.value } })
  }
}

onMounted(load)
</script>

<template>
  <page-container :title="isEdit ? t('sample.form.editTitle') : t('sample.form.createTitle')" show-back @back="cancel">
    <section-container>
      <form class="sample-form" data-test="sample-form" @submit.prevent="submit">
        <div class="sample-form__field">
          <label class="sample-form__label" for="sample-name">{{ t('sample.form.name') }}</label>
          <text-input v-model="form.name" placeholder="" data-test="sample-form-name" />
          <p v-if="errors.name !== ''" class="sample-form__error" data-test="sample-form-name-error">{{ errors.name }}</p>
        </div>
        <div class="sample-form__field">
          <label class="sample-form__label">{{ t('sample.form.category') }}</label>
          <select-input v-model="form.category" :options="categoryOptions" data-test="sample-form-category" />
        </div>
        <div class="sample-form__field">
          <label class="sample-form__label">{{ t('sample.form.priority') }}</label>
          <radio-input v-model="form.priority" form="button" :options="priorityOptions" data-test="sample-form-priority" />
        </div>
        <div class="sample-form__field">
          <label class="sample-form__label">{{ t('sample.form.amount') }}</label>
          <number-input v-model="form.amount" :min="0" :max="1000000" :precision="2" data-test="sample-form-amount" />
          <p v-if="errors.amount !== ''" class="sample-form__error" data-test="sample-form-amount-error">{{ errors.amount }}</p>
        </div>
        <div class="sample-form__field">
          <label class="sample-form__label">{{ t('sample.form.owner') }}</label>
          <text-input v-model="form.owner" data-test="sample-form-owner" />
          <p v-if="errors.owner !== ''" class="sample-form__error" data-test="sample-form-owner-error">{{ errors.owner }}</p>
        </div>
        <div class="sample-form__field">
          <label class="sample-form__label">{{ t('sample.form.status') }}</label>
          <select-input v-model="form.status" :options="statusOptions" data-test="sample-form-status" />
        </div>
        <div class="sample-form__field sample-form__field--full">
          <label class="sample-form__label">{{ t('sample.form.remark') }}</label>
          <textarea-input v-model="form.remark" :rows="3" :maxlength="200" show-word-limit data-test="sample-form-remark" />
        </div>
        <div class="sample-form__actions">
          <el-button type="primary" native-type="submit" :loading="saving" data-test="sample-form-submit">
            {{ t('sample.form.submit') }}
          </el-button>
          <el-button data-test="sample-form-cancel" @click="cancel">{{ t('sample.form.cancel') }}</el-button>
        </div>
      </form>
    </section-container>
  </page-container>
</template>

<style scoped>
.sample-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.sample-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sample-form__field--full {
  grid-column: 1 / -1;
}
.sample-form__label {
  color: var(--bms-color-text-secondary);
  font-size: 13px;
}
.sample-form__error {
  margin: 0;
  color: var(--bms-color-danger);
  font-size: 12px;
}
.sample-form__actions {
  grid-column: 1 / -1;
  display: flex;
  gap: 8px;
}
</style>
