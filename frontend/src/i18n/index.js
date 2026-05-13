import { createI18n } from 'vue-i18n'
import zh from '../locales/zh.json'
import en from '../locales/en.json'

const stored = localStorage.getItem('phial.locale')
const browser = (navigator.language || 'zh').toLowerCase().startsWith('zh') ? 'zh' : 'en'

export default createI18n({
  legacy: false,
  locale: stored || browser,
  fallbackLocale: 'en',
  messages: { zh, en }
})
