// ECharts 按需引入：运行概览/图谱页共用注册入口（消除全量 import 的 >500kB chunk）
import { registerTheme, use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, GraphChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, TitleComponent } from 'echarts/components'
import { theme } from '../styles/theme'

// canvas 文字不继承 CSS，必须通过主题把字体交给 ECharts，否则图表文字会是 sans-serif。
// 主题名在 init(dom, ECHARTS_THEME) 处传入。
export const ECHARTS_THEME = 'medirag'

// 坐标轴/网格/提示框也必须在这里统一：只设 textStyle.fontFamily 时，这些部件会退到
// ECharts 默认皮肤（轴标签 #6E7079、网格 #E0E6F1 偏蓝灰），与页面主题不是一套色。
registerTheme(ECHARTS_THEME, {
  textStyle: { fontFamily: theme.fontDisplay, color: theme.textColorBody },
  categoryAxis: {
    axisLine: { lineStyle: { color: theme.borderColor } },
    axisTick: { show: false },
    axisLabel: { color: theme.textColorSecondary },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: theme.textColorSecondary },
    splitLine: { lineStyle: { color: theme.borderColor } },
  },
  tooltip: {
    backgroundColor: theme.cardBg,
    borderColor: theme.borderColor,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: theme.textColorBody, fontFamily: theme.fontDisplay },
    extraCssText: `border-radius: 8px; box-shadow: ${theme.shadowCard};`,
  },
  legend: { textStyle: { color: theme.textColorSecondary } },
  title: { textStyle: { color: theme.textColorPrimary } },
})

export function regBase(): void {
  use([CanvasRenderer, LineChart, PieChart, BarChart,
       GridComponent, LegendComponent, TooltipComponent, TitleComponent])
}

export function regGraph(): void {
  use([GraphChart, CanvasRenderer, GridComponent, TooltipComponent, LegendComponent, TitleComponent])
}
