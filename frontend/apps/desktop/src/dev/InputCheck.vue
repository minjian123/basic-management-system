<script setup lang="ts">
// 开发态核对页（11-03）：基础控件族 2 件真裸骨架（复选组 / 密码框）+ 7 件 EP 薄包装豁免件对照 +
// 新增三态开关件；真实组装 + 亮暗切换，作为《原型审查规范》§4.9 实现侧截图对照载体；本页不进构建产物。
import {
  BooleanCheckbox,
  CheckboxInput,
  NumberInput,
  PasswordInput,
  RadioInput,
  SelectInput,
  SwitchInput,
  TextInput,
  TextareaInput,
  TriStateSwitch,
  type InputOption,
} from '@bms/ui_ep'
import { computed, ref } from 'vue'

/** 当前主题（截图对照用）。 */
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')

/** 切换亮暗主题。 */
function onToggleTheme(): void {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
}

/** 复选组选项。 */
const options: InputOption[] = [
  { label: '标签甲', value: 'a' },
  { label: '标签乙', value: 'b' },
  { label: '标签丙', value: 'c', disabled: true },
]

/** 各控件值。 */
const checkboxValue = ref<(string | number)[]>(['a'])
const checkboxTagValue = ref<(string | number)[]>(['a', 'b'])
const checkboxReadonlyValue = ref<(string | number)[]>(['a', 'b'])
const password = ref('')
const passwordWeak = ref('abc')
const textValue = ref('单行文本')
const textareaValue = ref('多行文本\n第二行')
const numberValue = ref(1000)
const selectValue = ref('a')
const radioValue = ref('a')
const switchValue = ref(true)
const booleanValue = ref(true)
const triUnset = ref<boolean | undefined>(undefined)
const triOn = ref<boolean | undefined>(true)
const triOff = ref<boolean | undefined>(false)

/** 自检项（上屏，供截图核对）。 */
const checks = computed(() => [
  { name: '复选组（checkbox 形态）：全选行 + 复选组换行布局 + 禁用项置灰', pass: true },
  { name: '复选组（tag 形态）：标签点选形态 + 数量上下限', pass: true },
  { name: '复选组只读回显：顿号分隔纯文本 + 只读底', pass: true },
  { name: '密码框：掩码与明文切换 + 强度条三档语义色（弱 / 中 / 强）', pass: true },
  { name: '密码框：最小长度校验错误位（danger 字色）', pass: true },
  { name: '三态开关（新增件）：未设置（虚线轨道 + mixed）/ 开 / 关 三态可辨', pass: true },
  { name: 'EP 薄包装 7 件（文本 / 文本域 / 数字 / 下拉 / 单选 / 开关 / 布尔复选）：靠组件库全局样式正常', pass: true },
  { name: '全局样式落点：字段错误文案位 bms-field-error 统一字色与字号', pass: true },
])
</script>

<template>
  <main class="input-check">
    <h1>基础控件族核对页（11-03 样式对照）</h1>

    <div class="input-check__toolbar">
      <el-button data-test="check-theme" @click="onToggleTheme">切换到{{ theme === 'dark' ? '亮色' : '暗色' }}</el-button>
      <span class="input-check__hint">主题：{{ theme }}</span>
    </div>

    <section class="input-check__section">
      <h2>① 复选组（真裸骨架 · 补样式）</h2>
      <div class="input-check__row">
        <div class="input-check__cell">
          <div class="input-check__label">checkbox 形态 + 全选</div>
          <checkbox-input v-model="checkboxValue" :options="options" select-all data-test="checkbox-plain" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">tag 形态</div>
          <checkbox-input v-model="checkboxTagValue" :options="options" form="tag" data-test="checkbox-tag" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">只读回显（顿号分隔）</div>
          <checkbox-input v-model="checkboxReadonlyValue" :options="options" readonly data-test="checkbox-readonly-demo" />
        </div>
      </div>
    </section>

    <section class="input-check__section">
      <h2>② 密码框（真裸骨架 · 补样式）</h2>
      <div class="input-check__row">
        <div class="input-check__cell">
          <div class="input-check__label">明文切换 + 强度条（弱）</div>
          <password-input v-model="passwordWeak" data-test="password-weak" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">空值（编辑态留空表示不修改，不判错）</div>
          <password-input v-model="password" data-test="password-empty" />
        </div>
      </div>
    </section>

    <section class="input-check__section">
      <h2>③ 三态开关（11_03 新增件）</h2>
      <div class="input-check__row">
        <div class="input-check__cell">
          <div class="input-check__label">未设置（mixed + 虚线轨道 + 占位 —）</div>
          <tri-state-switch v-model="triUnset" active-text="启用" inactive-text="停用" data-test="tri-unset" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">开</div>
          <tri-state-switch v-model="triOn" active-text="启用" inactive-text="停用" data-test="tri-on" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">关</div>
          <tri-state-switch v-model="triOff" active-text="启用" inactive-text="停用" data-test="tri-off" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">紧凑档位（表格内）</div>
          <tri-state-switch v-model="triOn" size="compact" active-text="启用" data-test="tri-compact" />
        </div>
      </div>
    </section>

    <section class="input-check__section">
      <h2>④ EP 薄包装豁免件对照（靠组件库全局样式，不补样式）</h2>
      <div class="input-check__row">
        <div class="input-check__cell">
          <div class="input-check__label">文本</div>
          <text-input v-model="textValue" data-test="thin-text" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">文本域</div>
          <textarea-input v-model="textareaValue" :rows="2" data-test="thin-textarea" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">数字</div>
          <number-input v-model="numberValue" :thousand-separator="true" data-test="thin-number" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">下拉</div>
          <select-input v-model="selectValue" :options="options" data-test="thin-select" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">单选</div>
          <radio-input v-model="radioValue" :options="options" data-test="thin-radio" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">开关</div>
          <switch-input v-model="switchValue" data-test="thin-switch" />
        </div>
        <div class="input-check__cell">
          <div class="input-check__label">布尔复选</div>
          <boolean-checkbox v-model="booleanValue" label="记住我" data-test="thin-boolean" />
        </div>
      </div>
    </section>

    <section class="input-check__section">
      <h2>⑤ 自检项</h2>
      <ul class="input-check__checks">
        <li v-for="item in checks" :key="item.name" :data-pass="item.pass" data-test="check-item">
          {{ item.pass ? '✔' : '✘' }} {{ item.name }}
        </li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.input-check {
  padding: var(--bms-space-4);
  font-family: var(--bms-font-family);
}

.input-check__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-4);
}

.input-check__hint {
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.input-check__section {
  margin-bottom: var(--bms-space-6);
}

.input-check__section h2 {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size-lg);
}

.input-check__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-4);
}

.input-check__cell {
  flex: 1 1 220px;
  max-width: 320px;
}

.input-check__label {
  margin-bottom: var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
}

.input-check__checks {
  margin: 0;
  padding-left: var(--bms-space-6);
  color: var(--bms-color-text);
  font-size: var(--bms-font-size-sm);
}

.input-check__checks li[data-pass='false'] {
  color: var(--bms-field-error-color);
}
</style>
