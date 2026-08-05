import { createI18n } from 'vue-i18n'

// i18n 占位：后续按阶段规划补充完整语言包
const messages = {
  zh: {
    app: { title: 'BMS 移动端' },
  },
  en: {
    app: { title: 'BMS Mobile' },
  },
}

export const i18n = createI18n({
  legacy: false,
  locale: 'zh',
  fallbackLocale: 'zh',
  messages,
})

export default i18n
