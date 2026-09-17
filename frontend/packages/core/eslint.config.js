import js from '@eslint/js'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { name: 'core/files-to-lint', files: ['**/*.{ts,mts}'] },
  { name: 'core/files-to-ignore', ignores: ['**/coverage/**', '**/node_modules/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  skipFormatting,
)
