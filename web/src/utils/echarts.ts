// ECharts 按需引入：运行概览/图谱页共用注册入口（消除全量 import 的 >500kB chunk）
import { registerTheme, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, GraphChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, TitleComponent } from 'echarts/components'
import { theme } from '../styles/theme'

// canvas 文字不继承 CSS，必须通过主题把字体交给 ECharts，否则图表文字会是 sans-serif。
// 主题名在 init(dom, ECHARTS_THEME) 处传入。
export const ECHARTS_THEME = 'medirag'

registerTheme(ECHARTS_THEME, {
  textStyle: { fontFamily: theme.fontDisplay },
})

export function regBase(): void {
  use([CanvasRenderer, LineChart, PieChart, BarChart,
       GridComponent, LegendComponent, TooltipComponent, TitleComponent])
}

export function regGraph(): void {
  use([GraphChart, CanvasRenderer, GridComponent, TooltipComponent, LegendComponent, TitleComponent])
}
