import js from '@eslint/js'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { name: 'module/files-to-lint', files: ['**/*.{ts,mts,tsx,vue}'] },
  {
    name: 'module/files-to-ignore',
    ignores: ['**/dist/**', '**/dist-standalone/**', '**/coverage/**', '**/node_modules/**', '**/.mf/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    name: 'module/vue-parser',
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    name: 'module/vue-no-undef',
    files: ['**/*.vue'],
    rules: { 'no-undef': 'off' },
  },
  {
    name: 'module/node-scripts',
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: { console: 'readonly', URL: 'readonly', process: 'readonly' } },
  },
  skipFormatting,
)
