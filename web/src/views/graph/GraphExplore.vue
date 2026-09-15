<script setup lang="ts">
// 本草图谱：左实体列表 + 中 ECharts 力导向图 + 右详情；候选审核 Tab（规格 P0-5）
import { onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { theme } from '../../styles/theme'
import type { GraphEntity, GraphLink, GraphNode } from '../../types/graph'
import { getEntityDetail, getNeighbors, searchEntities } from '../../api/graph'
import CandidateReview from './CandidateReview.vue'

const TYPE_COLOR: Record<string, string> = {
  方剂: theme.nodeFormula, 中药: theme.nodeHerb, 证候: theme.nodeSyndrome,
  症状: theme.nodeSymptom, 功效: theme.nodeEffect, 禁忌: theme.nodeContra,
}

const activeTab = ref('browse')
const keyword = ref('')
const typeFilter = ref('')
const entities = ref<GraphEntity[]>([])
const selected = ref<GraphEntity | null>(null)
const detail = ref<(GraphEntity & { desc: string; source: string }) | null>(null)
const chartRef = ref<HTMLElement>()
const chartReady = ref(false)
let chart: echarts.ECharts | undefined
let resizeTimer: number | undefined

const TYPES = ['方剂', '中药', '证候', '症状', '功效', '禁忌']

async function doSearch() {
  try {
    const res = await searchEntities(keyword.value, typeFilter.value)
    entities.value = res.items
  } catch (e) { ElMessage.error((e as Error).message) }
}

async function focusEntity(name: string) {
  try {
    const res = await getNeighbors(name, 2)
    renderGraph(res.nodes, res.links)
    detail.value = await getEntityDetail(name)
    selected.value = { name, type: detail.value.type, alias: detail.value.alias, status: detail.value.status }
  } catch (e) { ElMessage.error((e as Error).message) }
}

function renderGraph(nodes: GraphNode[], links: GraphLink[]) {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
    chartReady.value = true
    // 点节点联动左列表与右详情（规格 P0-5 交互验收①）；只注册一次，避免重复叠加
    chart.on('click', (p) => {
      if (p.dataType === 'node' && p.name) focusEntity(p.name)
    })
  }
  chart.setOption({
    tooltip: {},
    legend: [{ data: TYPES, bottom: 0, textStyle: { fontSize: 11 } }],
    series: [{
      type: 'graph', layout: 'force', roam: true, draggable: true,
      layoutAnimation: true,
      categories: TYPES.map(t => ({ name: t, itemStyle: { color: TYPE_COLOR[t] } })),
      label: { show: true, fontSize: 10, position: 'right' },
      force: { repulsion: 900, edgeLength: [120, 200], gravity: 0.08 },
      edgeLabel: { show: true, fontSize: 10, formatter: (p: any) => p.data.relation },
      data: nodes.map(n => {
        const category = TYPES.indexOf(n.category)
        return {
          id: n.name, name: n.name,
          category: category >= 0 ? category : 0, symbolSize: n.status === '候选' ? 22 : 30,
          itemStyle: n.status === '候选'
            ? { borderType: 'dashed', borderWidth: 2, borderColor: theme.textColorMuted }
            : {},
        }
      }),
      links: links.map(l => ({
        source: l.source, target: l.target, relation: l.relation,
        lineStyle: l.status === '候选' ? { type: 'dashed', color: theme.textColorMuted } : {},
      })),
      lineStyle: { color: theme.safetyBg, width: 1.5, curveness: 0.08 },
    }],
  })
}

function resizeChart() { chart?.resize() }

watch(activeTab, (v) => { if (v === 'browse') resizeTimer = window.setTimeout(resizeChart, 50) })
onMounted(() => { doSearch(); window.addEventListener('resize', resizeChart) })
onUnmounted(() => {
  window.clearTimeout(resizeTimer)
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
})
</script>

<template>
  <div class="graph-page">
    <div class="toolbar">
      <el-input v-model="keyword" placeholder="搜索中药、方剂、证候或症状" style="width: 260px"
                @keyup.enter="doSearch" />
      <el-select v-model="typeFilter" placeholder="全部实体类型" clearable style="width: 140px">
        <el-option v-for="t in TYPES" :key="t" :label="t" :value="t" />
      </el-select>
      <el-button type="primary" @click="doSearch">查询</el-button>
      <el-button link type="primary">重新导入基础数据</el-button>
    </div>

    <el-tabs v-model="activeTab" class="graph-tabs">
      <el-tab-pane label="图谱浏览" name="browse">
        <div class="browse-body">
          <aside class="entity-list">
            <div class="list-head">实体结果 <el-tag size="small" type="info">{{ entities.length }}</el-tag></div>
            <div v-for="e in entities" :key="e.name" class="entity-item"
                 :class="{ active: selected?.name === e.name }" @click="focusEntity(e.name)">
              <span class="dot" :style="{ background: TYPE_COLOR[e.type] ?? theme.textColorMuted }" />
              <span class="entity-name">{{ e.name }}</span>
              <el-tag size="small" class="entity-type">{{ e.type }}</el-tag>
            </div>
          </aside>

          <div class="canvas-wrap">
            <div ref="chartRef" class="chart" />
            <el-empty v-if="!chartReady" class="canvas-empty" description="点击左侧实体查看关系图" />
          </div>

          <aside class="detail-panel">
            <template v-if="detail">
              <div class="detail-head">
                <span class="dot" :style="{ background: TYPE_COLOR[detail.type] }" />
                <strong>{{ detail.name }}</strong>
                <el-tag size="small">{{ detail.type }}</el-tag>
              </div>
              <div class="detail-field"><label>别名</label><span>{{ detail.alias || '—' }}</span></div>
              <div class="detail-field"><label>说明</label><span>{{ detail.desc || '—' }}</span></div>
              <div class="detail-field"><label>来源</label><span>{{ detail.source || '—' }}</span></div>
              <div class="legend">
                <span v-for="t in TYPES" :key="t">
                  <i :style="{ background: TYPE_COLOR[t] }" />{{ t }}
                </span>
              </div>
            </template>
            <el-empty v-else description="选择实体查看详情" :image-size="60" />
          </aside>
        </div>
      </el-tab-pane>

      <el-tab-pane label="候选审核" name="review" lazy>
        <CandidateReview />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.graph-page { display: flex; flex-direction: column; gap: 12px; }
.toolbar { display: flex; gap: 10px; align-items: center; }
.browse-body { display: grid; grid-template-columns: 240px 1fr 260px; gap: 12px; min-height: 520px; }
.entity-list, .detail-panel { background: v-bind(theme.cardBg); border: 1px solid v-bind(theme.borderColor); border-radius: v-bind(theme.borderRadius); padding: 10px; overflow-y: auto; max-height: 620px; }
.list-head { font-size: 13px; font-weight: 600; margin-bottom: 8px; display: flex; justify-content: space-between; }
.entity-item { display: flex; align-items: center; gap: 6px; padding: 7px 8px; border-radius: 8px; cursor: pointer; font-size: 13px; }
.entity-item:hover, .entity-item.active { background: v-bind(theme.hoverBg); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.entity-name { flex: 1; }
.entity-type { transform: scale(0.9); }
.canvas-wrap { background: v-bind(theme.cardBg); border: 1px solid v-bind(theme.borderColor); border-radius: v-bind(theme.borderRadius); position: relative; }
.canvas-empty { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; pointer-events: none; }
.chart { width: 100%; height: 640px; }
.detail-head { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; }
.detail-field { margin-bottom: 10px; font-size: 13px; }
.detail-field label { display: block; color: v-bind(theme.textColorSecondary); font-size: 12px; margin-bottom: 2px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px; font-size: 12px; color: v-bind(theme.textColorSecondary); margin-top: 16px; }
.legend i { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 3px; }
</style>