import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

import App from './App.vue'
import router from './router'
import { theme } from './styles/theme'
import './styles/fonts.css'
import './styles/element-overrides.css'

// 字体栈由 theme.ts 注入根元素 CSS 变量：全局样式与 Element Plus 变量统一引用，
// 避免在 CSS 里重复写死字面量（设计 token 唯一真源仍是 theme.ts）。
document.documentElement.style.setProperty('--font-display', theme.fontDisplay)
document.documentElement.style.setProperty('--font-sans', theme.fontSans)

const app = createApp(App)

// 全局注册 Element Plus 图标（线性图标风格，见前端还原规格）
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
