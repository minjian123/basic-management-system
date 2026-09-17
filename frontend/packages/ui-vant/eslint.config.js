import js from '@eslint/js'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { name: 'pkg/files-to-lint', files: ['**/*.{ts,mts,vue}'] },
  { name: 'pkg/files-to-ignore', ignores: ['**/coverage/**', '**/node_modules/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    name: 'pkg/vue-parser',
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  { name: 'pkg/vue-no-undef', files: ['**/*.vue'], rules: { 'no-undef': 'off' } },
  {
    name: 'pkg/tests',
    files: ['tests/**/*.{ts,mts}', 'testing/**/*.{ts,mts}'],
    rules: { 'vue/one-component-per-file': 'off' },
  },
  skipFormatting,
)
