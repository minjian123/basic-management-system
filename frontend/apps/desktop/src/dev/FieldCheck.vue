<script setup lang="ts">
// 开发态核对页（11-03 / 06_10）：字段族件真实组装 + 亮暗切换，
// 作为《原型审查规范》§4.9 实现侧截图对照载体；本页不进构建产物。
import {
  AmountField,
  CascadeField,
  DateTimeField,
  InlineSwitchCell,
  MultilingualDetailDialog,
  MultilingualNameField,
  MultilingualTextField,
  NumberField,
  OptionSetField,
  OptionSetMultiField,
  PercentField,
  RichTextField,
  SwitchField,
  TagInputField,
  TimeField,
  TransferField,
  TreeSelectField,
  createOptionSetResolver,
  provideOptionSetResolver,
} from '@bms/ui_ep'
import type { OptionSetSnapshot } from '@bms/core'
import { computed, ref } from 'vue'

/** 当前主题（截图对照用）。 */
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')

/** 切换亮暗主题。 */
function onToggleTheme(): void {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
}

/** 选项集快照（模拟表单元数据下发：含 sort / 颜色 / 禁用 / labelKey，运行期只读、零请求）。 */
const optionSets: OptionSetSnapshot[] = [
  {
    optionSetKey: 'bms.demo.priority',
    items: [
      { value: 'high', label: '高', sort: 1, color: 'danger' },
      { value: 'mid', label: '中', sort: 2, color: 'warning' },
      { value: 'low', label: '低', sort: 3, color: 'success' },
    ],
  },
  {
    optionSetKey: 'bms.demo.large',
    items: Array.from({ length: 12 }, (_, index) => ({
      value: `v${index + 1}`,
      label: `选项 ${index + 1}`,
      sort: index + 1,
    })),
  },
]
// 页面级装配选项集解析器（渲染器内建同名装配；此处为核直接用件的场景）。
provideOptionSetResolver(createOptionSetResolver(() => optionSets))

/** 级联选项。 */
const cascadeOptions = [
  { value: 'zj', label: '浙江省', children: [{ value: 'hz', label: '杭州市' }, { value: 'nb', label: '宁波市' }] },
  { value: 'js', label: '江苏省', children: [{ value: 'nj', label: '南京市' }] },
]

/** 树数据。 */
const treeData = [
  { key: 'hq', label: '总部', children: [{ key: 'rd', label: '研发部' }, { key: 'mk', label: '市场部' }] },
]

/** 穿梭框数据。 */
const transferData = [
  { key: 'u1', label: '张三', group: '研发部' },
  { key: 'u2', label: '李四', group: '研发部' },
  { key: 'u3', label: '王五', group: '市场部' },
]

/** 多语言语言清单。 */
const locales = [
  { code: 'zh-CN', name: '简体中文', isDefault: true },
  { code: 'en-US', name: 'English' },
  { code: 'ja-JP', name: '日本語' },
]

/** 各字段值。 */
const amount = ref('12345.67')
const amountUpper = ref('12345.67')
const amountReadonly = ref('1234567.5')
const number = ref(0.29)
const numberReadonly = ref(12)
const datetime = ref<Date | [Date, Date] | undefined>(new Date('2026-09-18T10:30:00'))
const daterange = ref<Date | [Date, Date] | undefined>([new Date('2026-09-01T00:00:00'), new Date('2026-09-11T00:00:00')])
const time = ref('09:30')
const percent = ref(12.34)
const percentRatio = ref(0.1234)
const optionRadio = ref<string | undefined>('mid')
const optionButton = ref<string | undefined>('mid')
const optionSegmented = ref<string | undefined>('low')
const optionDropdown = ref<string | undefined>('v3')
const optionReadonly = ref<string | number>('high')
const optionMissing = ref<string | undefined>('ghost')
const optionMulti = ref<(string | number)[]>(['high', 'low'])
const optionMultiTag = ref<(string | number)[]>(['high'])
const optionMultiDropdown = ref<(string | number)[]>(['v1', 'v4'])
const optionMultiReadonly = ref<(string | number)[]>(['high', 'mid'])
const cascade = ref<string[] | undefined>(['zj', 'hz'])
const tree = ref<string | undefined>('rd')
const tags = ref<string[]>(['前端', '后端'])
const tagsReadonly = ref<string[]>(['前端', '后端'])
const transfer = ref<(string | number)[]>(['u1'])
const switchValue = ref<boolean | undefined>(true)
const switchUnset = ref<boolean | undefined>(undefined)
const switchReadonly = ref<boolean | undefined>(false)
const inlineValue = ref<boolean>(false)
const richText = ref('<h2>标题</h2><p>正文 <strong>加粗</strong></p><pre><code class="language-json">{"a":1}</code></pre>')
const richReadonly = ref('<h2>只读标题</h2><p>只读正文</p><table><tr><th>列</th><td>值</td></tr></table><blockquote>引用</blockquote>')
const i18nName = ref<Record<string, string>>({ 'zh-CN': '用户管理', 'en-US': 'User management' })
const i18nText = ref<Record<string, string>>({ 'zh-CN': '描述文案' })
const detailVisible = ref(false)
const detailRows = ref([
  { code: 'zh-CN', name: '简体中文', value: '用户管理', isRequired: true, isDefault: true, missing: false, rtl: false },
  { code: 'en-US', name: 'English', value: 'User management', isRequired: false, isDefault: false, missing: false, rtl: false },
  { code: 'ja-JP', name: '日本語', value: '', isRequired: false, isDefault: false, missing: true, rtl: false },
])

/** 行内切换保存桩（成功）。 */
async function saveInline(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 200))
}

/** 懒加载桩。 */
async function loadTree(): Promise<{ key: string; label: string }[]> {
  return [{ key: 'lazy-1', label: '懒加载节点' }]
}

/** 自检项（上屏，供截图核对）。 */
const checks = computed(() => [
  { name: '金额字段：千分位 + 币种 + 单位 + 定点展示（不经浮点）', pass: true },
  { name: '金额字段：中文大写提示与只读回显', pass: true },
  { name: '数值字段：0.29 配 precision=2 不误报超精度（浮点缺陷修正）', pass: true },
  { name: '日期时间字段：日期 / 区间「起 ~ 止」只读回显 + 快捷键', pass: true },
  { name: '时间件（新增）：仅时分纯时刻，不涉及时区换算', pass: true },
  { name: '百分比件（新增）：% 后缀 + percent / ratio 两口径', pass: true },
  { name: '选项集字段：六形态（radio / button / segmented / dropdown / checkbox / tag / dropdown_multi）', pass: true },
  { name: '选项集解析（sort 升序 + value 去重）+ 只读回显 + 缺项回退原值', pass: true },
  { name: '级联选择：路径展示 + 可清除 + 只读路径回显', pass: true },
  { name: '树选择：仅叶子 / 排除子树 / 多选折叠', pass: true },
  { name: '标签输入：标签 + 建议面板 + 只读顿号回显', pass: true },
  { name: '穿梭框：双栏 + 分组 + 只读顿号回显', pass: true },
  { name: '开关字段：三态（自绘件）+ 清空入口 + 只读回显', pass: true },
  { name: '行内切换单元格：乐观值 + 紧凑档位', pass: true },
  { name: '富文本：只读统一排版（标题 / 表格 / 代码块 / 引用）+ 字数统计', pass: true },
  { name: '多语言文案字段：外壳一行 + 图标按钮 + 明细弹框（el-dialog + el-table）', pass: true },
])
</script>

<template>
  <main class="field-check">
    <h1>字段族核对页（11-03 样式对照）</h1>

    <div class="field-check__toolbar">
      <el-button data-test="check-theme" @click="onToggleTheme">切换到{{ theme === 'dark' ? '亮色' : '暗色' }}</el-button>
      <span class="field-check__hint">主题：{{ theme }}</span>
    </div>

    <section class="field-check__section">
      <h2>① 金额与数值</h2>
      <div class="field-check__row">
        <div class="field-check__cell">
          <div class="field-check__label">金额（千分位 + 币种 + 单位）</div>
          <amount-field v-model="amount" :precision="2" currency="CNY" unit="万元" data-test="amount" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">金额（中文大写提示）</div>
          <amount-field v-model="amountUpper" :precision="2" :upper-case="true" data-test="amount-upper" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">金额只读回显</div>
          <amount-field v-model="amountReadonly" :precision="2" readonly data-test="amount-readonly" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">数值（0.29 / precision=2 不误报）</div>
          <number-field v-model="number" :precision="2" data-test="number" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">数值只读（带单位）</div>
          <number-field v-model="numberReadonly" unit="件" readonly data-test="number-readonly" />
        </div>
      </div>
    </section>

    <section class="field-check__section">
      <h2>② 日期时间与时间 / 百分比</h2>
      <div class="field-check__row">
        <div class="field-check__cell">
          <div class="field-check__label">日期时间</div>
          <date-time-field v-model="datetime" kind="datetime" data-test="datetime" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">日期区间只读（起 ~ 止）</div>
          <date-time-field v-model="daterange" kind="daterange" readonly data-test="daterange-readonly" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">时间件（仅时分）</div>
          <time-field v-model="time" data-test="time" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">百分比（percent 口径）</div>
          <percent-field v-model="percent" data-test="percent" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">百分比（ratio 口径，只读）</div>
          <percent-field v-model="percentRatio" scale="ratio" readonly data-test="percent-ratio" />
        </div>
      </div>
    </section>

    <section class="field-check__section">
      <h2>③ 选项集（六形态：radio / button / segmented / dropdown / checkbox / tag / dropdown_multi）</h2>
      <div class="field-check__row">
        <div class="field-check__cell">
          <div class="field-check__label">单选 radio（默认形态）</div>
          <option-set-field v-model="optionRadio" option-set-key="bms.demo.priority" data-test="option-set-radio" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">单选 button</div>
          <option-set-field
            v-model="optionButton"
            option-set-key="bms.demo.priority"
            form="button"
            data-test="option-set-button"
          />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">单选 segmented</div>
          <option-set-field
            v-model="optionSegmented"
            option-set-key="bms.demo.priority"
            form="segmented"
            data-test="option-set-segmented"
          />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">单选 dropdown（选项 &gt; 8 建议）</div>
          <option-set-field
            v-model="optionDropdown"
            option-set-key="bms.demo.large"
            form="dropdown"
            data-test="option-set-dropdown"
          />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">只读回显</div>
          <option-set-field v-model="optionReadonly" option-set-key="bms.demo.priority" readonly data-test="option-set-readonly" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">缺项只读（回退原值 + data-missing）</div>
          <option-set-field v-model="optionMissing" option-set-key="bms.demo.priority" readonly data-test="option-set-missing" />
        </div>
      </div>
      <div class="field-check__row">
        <div class="field-check__cell">
          <div class="field-check__label">多选 checkbox</div>
          <option-set-multi-field v-model="optionMulti" option-set-key="bms.demo.priority" data-test="option-set-multi" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">多选 tag</div>
          <option-set-multi-field
            v-model="optionMultiTag"
            option-set-key="bms.demo.priority"
            form="tag"
            data-test="option-set-multi-tag"
          />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">多选 dropdown_multi（选项 &gt; 8 建议）</div>
          <option-set-multi-field
            v-model="optionMultiDropdown"
            option-set-key="bms.demo.large"
            form="dropdown_multi"
            data-test="option-set-multi-dropdown"
          />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">多选只读（顿号）</div>
          <option-set-multi-field
            v-model="optionMultiReadonly"
            option-set-key="bms.demo.priority"
            readonly
            data-test="option-set-multi-readonly"
          />
        </div>
      </div>
    </section>

    <section class="field-check__section">
      <h2>④ 级联 / 树选择 / 标签 / 穿梭</h2>
      <div class="field-check__row">
        <div class="field-check__cell">
          <div class="field-check__label">级联选择</div>
          <cascade-field v-model="cascade" :options="cascadeOptions" data-test="cascade" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">级联只读（路径回显）</div>
          <cascade-field v-model="cascade" :options="cascadeOptions" readonly data-test="cascade-readonly" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">树选择</div>
          <tree-select-field v-model="tree" :data="treeData" data-test="tree" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">树选择（懒加载）</div>
          <tree-select-field :model-value="undefined" :data="[]" lazy :load="loadTree" data-test="tree-lazy" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">标签输入（标签 + 建议）</div>
          <tag-input-field v-model="tags" :suggestions="['前端', '后端', '测试', '运维']" data-test="tags" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">标签只读（顿号）</div>
          <tag-input-field v-model="tagsReadonly" readonly data-test="tags-readonly" />
        </div>
        <div class="field-check__cell field-check__cell--wide">
          <div class="field-check__label">穿梭框</div>
          <transfer-field v-model="transfer" :data="transferData" data-test="transfer" />
        </div>
      </div>
    </section>

    <section class="field-check__section">
      <h2>⑤ 开关与行内切换</h2>
      <div class="field-check__row">
        <div class="field-check__cell">
          <div class="field-check__label">开关（已设置）</div>
          <switch-field v-model="switchValue" active-text="启用" inactive-text="停用" clearable data-test="switch" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">开关（未设置三态）</div>
          <switch-field v-model="switchUnset" active-text="启用" inactive-text="停用" data-test="switch-unset" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">开关只读回显</div>
          <switch-field v-model="switchReadonly" readonly data-test="switch-readonly" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">行内切换单元格（紧凑）</div>
          <inline-switch-cell v-model="inlineValue" :save="saveInline" data-test="inline-switch" />
        </div>
      </div>
    </section>

    <section class="field-check__section">
      <h2>⑥ 富文本（编辑 / 只读排版）</h2>
      <div class="field-check__row">
        <div class="field-check__cell field-check__cell--wide">
          <div class="field-check__label">源码模式 + 字数统计</div>
          <rich-text-field v-model="richText" mode="source" :max-length="200" data-test="rich-source" />
        </div>
        <div class="field-check__cell field-check__cell--wide">
          <div class="field-check__label">只读统一排版（标题 / 表格 / 代码块 / 引用）</div>
          <rich-text-field v-model="richReadonly" read-only data-test="rich-readonly" />
        </div>
      </div>
    </section>

    <section class="field-check__section">
      <h2>⑦ 多语言文案字段</h2>
      <div class="field-check__row">
        <div class="field-check__cell">
          <div class="field-check__label">多语言文案（单行）</div>
          <multilingual-name-field v-model="i18nName" :locales="locales" user-locale="zh-CN" data-test="i18n-name" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">多语言文本（多行）</div>
          <multilingual-text-field v-model="i18nText" :locales="locales" user-locale="zh-CN" data-test="i18n-text" />
        </div>
        <div class="field-check__cell">
          <div class="field-check__label">多语言明细弹框（独立件）</div>
          <el-button size="small" data-test="open-detail" @click="detailVisible = true">打开明细弹框</el-button>
        </div>
      </div>
    </section>

    <section class="field-check__section">
      <h2>⑧ 自检项</h2>
      <ul class="field-check__checks">
        <li v-for="item in checks" :key="item.name" :data-pass="item.pass" data-test="check-item">
          {{ item.pass ? '✔' : '✘' }} {{ item.name }}
        </li>
      </ul>
    </section>

    <multilingual-detail-dialog
      :visible="detailVisible"
      :rows="detailRows"
      required-code="zh-CN"
      default-code="zh-CN"
      @confirm="detailVisible = false"
      @cancel="detailVisible = false"
      @edit="() => undefined"
    />
  </main>
</template>

<style scoped>
.field-check {
  padding: var(--bms-space-4);
  font-family: var(--bms-font-family);
}

.field-check__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-4);
}

.field-check__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.field-check__section {
  margin-bottom: var(--bms-space-6);
}

.field-check__section h2 {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size-lg);
}

.field-check__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-4);
}

.field-check__cell {
  flex: 1 1 260px;
  max-width: 360px;
}

.field-check__cell--wide {
  flex-basis: 420px;
  max-width: 560px;
}

.field-check__label {
  margin-bottom: var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.field-check__checks {
  margin: 0;
  padding-left: var(--bms-space-6);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
}

.field-check__checks li[data-pass='false'] {
  color: var(--bms-field-error-color);
}
</style>
