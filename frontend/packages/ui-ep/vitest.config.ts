import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    // EP 组件（按需导入）内联处理：其 style/css 依赖 theme-chalk CSS
    server: {
      deps: {
        inline: ['element-plus'],
      },
    },
  },
})
