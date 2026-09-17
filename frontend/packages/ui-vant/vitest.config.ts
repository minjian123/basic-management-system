import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
    // Vant 组件（ESM 直出）内联处理：其样式模块与运行时同源
    server: {
      deps: {
        inline: ['vant'],
      },
    },
  },
})
