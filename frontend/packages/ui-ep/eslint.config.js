import js from '@eslint/js'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { name: 'ui-ep/files-to-lint', files: ['**/*.{ts,mts,tsx,vue}'] },
  { name: 'ui-ep/files-to-ignore', ignores: ['**/coverage/**', '**/node_modules/**'] },
  {
    // 显式锚定 TS 配置根（monorepo 多包各一份配置，工具工作目录不确定时会报「多个候选 TSConfigRootDirs」）
    name: 'ui-ep/tsconfig-root',
    files: ['**/*.{ts,mts,tsx,vue}'],
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    name: 'ui-ep/vue-parser',
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    name: 'ui-ep/vue-no-undef',
    files: ['**/*.vue'],
    rules: { 'no-undef': 'off' },
  },
  {
    name: 'ui-ep/tests',
    files: ['tests/**/*.{ts,mts,tsx}'],
    rules: { 'vue/one-component-per-file': 'off' },
  },
  skipFormatting,
)
