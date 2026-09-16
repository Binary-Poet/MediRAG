// ECharts 按需引入：运行概览/图谱页共用注册入口（消除全量 import 的 >500kB chunk）
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent, TitleComponent } from 'echarts/components'

export function regBase(): void {
  use([CanvasRenderer, LineChart, PieChart, BarChart,
       GridComponent, LegendComponent, TooltipComponent, TitleComponent])
}