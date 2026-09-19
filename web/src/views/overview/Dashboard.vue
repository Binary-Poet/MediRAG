<script setup lang="ts">
// 运行概览：5 卡全读 /api/stats/overview 真实数据（规格 P1）；配色全走 theme token
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getInstanceByDom, init, type ECharts, type EChartsCoreOption } from 'echarts/core'
import { ElMessage } from 'element-plus'
import { ECHARTS_THEME, regBase } from '../../utils/echarts'
import { getOverview } from '../../api/stats'
import type { NamedValue, OverviewData, QualityStats, TrendPoint } from '../../types/stats'
import { theme } from '../../styles/theme'

regBase()

const data = ref<OverviewData | null>(null)
const loading = ref(true)
const trendRef = ref<HTMLElement>()
const roleRef = ref<HTMLElement>()
const topicRef = ref<HTMLElement>()
const statusRef = ref<HTMLElement>()
// 已创建的实例：统一 resize / dispose（参照 GraphExplore.vue 的图表生命周期）
const charts: ECharts[] = []

const days = computed(() => data.value?.trend ?? [])
const roleDist = computed(() => data.value?.role_dist ?? [])
const topicDist = computed(() => data.value?.topic_dist ?? [])
const statusDist = computed(() => data.value?.status_dist ?? [])
const quality = computed<QualityStats>(() => data.value?.quality ?? {
  total: 0, fallback_n: 0, normal_n: 0, useful: 0, useless: 0,
  satisfaction: 0, success_rate: 0,
})

// 统一直方图/环形图 option 生成器（主题绿 + 语义色）
const CYCLIC = [theme.nodeFormula, theme.nodeHerb, theme.nodeSyndrome,
                theme.nodeSymptom, theme.nodeEffect, theme.colorPrimary,
                theme.colorWarning, theme.colorSuccess]

function pieOption(items: NamedValue[], title: string): EChartsCoreOption {
  return {
    title: { text: title, left: 'center', textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie', radius: ['42%', '68%'],
      itemStyle: { borderRadius: 6, borderColor: theme.cardBg, borderWidth: 2 },
      data: items.map((it, i) => ({ ...it, itemStyle: { color: CYCLIC[i % CYCLIC.length] } })),
      label: { show: false },
    }],
  }
}

function lineOption(points: TrendPoint[]): EChartsCoreOption {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: { type: 'category', data: points.map(p => p.date.slice(5)), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'line', smooth: true, symbol: 'circle', symbolSize: 5,
      data: points.map(p => p.count),
      lineStyle: { color: theme.colorPrimary, width: 2 },
      itemStyle: { color: theme.colorPrimary },
      areaStyle: { color: theme.safetyBg },
    }],
  }
}

function barOption(items: NamedValue[]): EChartsCoreOption {
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 28 },
    xAxis: { type: 'category', data: items.map(i => i.name), axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{
      type: 'bar', barMaxWidth: 40,
      data: items.map(i => ({ value: i.value, itemStyle: { color: theme.nodeHerb } })),
    }],
  }
}

/** 建实例或复用已有实例（避免重复 init 报 "already initialized"），再刷新 option */
function draw(el: HTMLElement | undefined, option: EChartsCoreOption) {
  if (!el) return
  let chart = getInstanceByDom(el)
  if (!chart) {
    chart = init(el, ECHARTS_THEME)
    charts.push(chart)
  }
  chart.setOption(option)
  // 首帧容器可能尚无尺寸（布局未稳定/隐藏）；重新测量，避免留下空白画布
  chart.resize()
}

function renderAll() {
  // 卡片标题已由 .card-title 呈现，图表内不再重复标题
  draw(trendRef.value, lineOption(days.value))
  draw(roleRef.value, pieOption(roleDist.value, ''))
  draw(topicRef.value, pieOption(topicDist.value, ''))
  draw(statusRef.value, barOption(statusDist.value))
}

function resizeAll() { charts.forEach(c => c.resize()) }

onMounted(async () => {
  // 先用空数据建实例：接口失败时卡片留白而非白屏
  renderAll()
  window.addEventListener('resize', resizeAll)
  try {
    data.value = await getOverview()
    renderAll()
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeAll)
  charts.forEach(c => c.dispose())
  charts.length = 0
})
</script>

<template>
  <div class="overview-page">
    <div v-loading="loading" class="grid">
      <el-card class="card wide" shadow="never">
        <div class="card-title">问答量趋势<span class="range">近14天</span></div>
        <div ref="trendRef" class="chart" />
      </el-card>
      <el-card class="card" shadow="never">
        <div class="card-title">用户角色分布</div>
        <div ref="roleRef" class="chart" />
      </el-card>
      <el-card class="card" shadow="never">
        <div class="card-title">中医药知识主题分布</div>
        <div ref="topicRef" class="chart" />
      </el-card>
      <el-card class="card" shadow="never">
        <div class="card-title">知识库状态分布</div>
        <div ref="statusRef" class="chart" />
      </el-card>
      <el-card class="card" shadow="never">
        <div class="card-title">检索质量统计</div>
        <div class="quality">
          <div class="metric">
            <span>用户满意度</span>
            <el-progress :percentage="Math.round(quality.satisfaction * 100)" :color="theme.colorPrimary" />
          </div>
          <div class="metric">
            <span>检索完成率</span>
            <el-progress :percentage="Math.round(quality.success_rate * 100)" :color="theme.colorPrimary" />
          </div>
          <div class="metric-row">
            <el-statistic title="有用反馈" :value="quality.useful" />
            <el-statistic title="无用反馈" :value="quality.useless" />
            <el-statistic title="兜底次数" :value="quality.fallback_n" />
            <el-statistic title="正常检索" :value="quality.normal_n" />
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.overview-page { background: v-bind(theme.pageBg); display: flex; flex-direction: column; gap: 14px; }
/* 页面标题由顶栏面包屑承载，页内不再重复 h2（与其他页面统一） */
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.card { background: v-bind(theme.cardBg); border-radius: v-bind(theme.borderRadius); }
.card.wide { grid-column: span 2; }
.card-title { font-size: 14px; font-weight: 600; color: v-bind(theme.textColorPrimary); margin-bottom: 10px; }
/* 不写死 400：中文子集只发布 500/600，写 400 会让中文落到 500、拉丁落到 400，同串两种粗细 */
.card-title .range { font-size: 12px; color: v-bind(theme.textColorMuted); margin-left: 8px; }
.chart { height: 260px; }
.quality { display: flex; flex-direction: column; gap: 16px; padding-top: 6px; }
.metric span { display: block; font-size: 13px; color: v-bind(theme.textColorSecondary); margin-bottom: 6px; }
.metric-row { display: flex; flex-wrap: wrap; gap: 18px; }
</style>
