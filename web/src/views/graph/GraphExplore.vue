<script setup lang="ts">
// 本草图谱：左实体列表 + 中 ECharts 力导向图 + 右详情；候选审核 Tab（规格 P0-5）
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { init, type ECharts } from 'echarts/core'
import { ElMessage, ElMessageBox } from 'element-plus'
import { theme } from '../../styles/theme'
import { ECHARTS_THEME, regGraph } from '../../utils/echarts'
import type { GraphEntity, GraphLink, GraphNode } from '../../types/graph'
import { getEntityDetail, getNeighbors, reimportGraph, searchEntities } from '../../api/graph'
import CandidateReview from './CandidateReview.vue'

regGraph()

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
let chart: ECharts | undefined
let resizeTimer: number | undefined

const TYPES = ['方剂', '中药', '证候', '症状', '功效', '禁忌']

async function doSearch() {
  try {
    const res = await searchEntities(keyword.value, typeFilter.value)
    entities.value = res.items
  } catch (e) { ElMessage.error((e as Error).message) }
}

async function doReimport() {
  try {
    await ElMessageBox.confirm('将以内置演示数据重新导入图谱（幂等，不覆盖已发布/候选状态）。', '重新导入', { type: 'warning' })
  } catch {
    return // 用户取消
  }
  try {
    const r = await reimportGraph()
    ElMessage.success(`已导入 ${r.imported.nodes} 节点 / ${r.imported.edges} 关系`)
    doSearch()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
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
    chart = init(chartRef.value, ECHARTS_THEME)
    chartReady.value = true
    // 点节点联动左列表与右详情（规格 P0-5 交互验收①）；只注册一次，避免重复叠加
    chart.on('click', (p) => {
      if (p.dataType === 'node' && p.name) focusEntity(p.name)
    })
  }
  chart.setOption({
    // 边的关系名默认不铺在画布上（力导向布局下位置不可控，多边必然互压）；
    // 改为悬停该边时由 tooltip 给出完整三元组 + 就地显示标签，信息不丢且画布干净。
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => (p.dataType === 'edge'
        ? `${p.data.source} —${p.data.relation}→ ${p.data.target}`
        : `${p.name}${p.value ?? ''}`),
    },
    // 6 类图例由右栏详情面板承担（左栏彩点+类型标签也在表达同一信息），画布底部不再重复铺一条，
    // 腾出的高度还给画布；节点标签在节点右侧，右侧留 60px 防止边缘实体名被画布硬裁。
    series: [{
      type: 'graph', layout: 'force', roam: true, draggable: true,
      layoutAnimation: true,
      left: 24, top: 16, right: 60, bottom: 16,
      categories: TYPES.map(t => ({ name: t, itemStyle: { color: TYPE_COLOR[t] } })),
      label: { show: true, fontSize: 11, position: 'right', color: theme.textColorBody },
      force: { repulsion: 900, edgeLength: [120, 200], gravity: 0.08 },
      edgeLabel: {
        show: false, fontSize: 11, color: theme.textColorBody,
        backgroundColor: theme.cardBg, padding: [2, 5], borderRadius: 4,
        formatter: (p: any) => p.data.relation,
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { color: theme.graphEdgeActive, width: 2.4 },
        edgeLabel: { show: true },
      },
      data: nodes.map(n => {
        const category = TYPES.indexOf(n.category)
        return {
          id: n.name, name: n.name,
          category: category >= 0 ? category : 0, symbolSize: n.status === '候选' ? 22 : 30,
          // 候选态描边用告警橙：原 textColorFaint(#9ca3af) 在白底上只有 2.5:1，
          // 「待审核」是需要被注意的语义，弱到看不见就失去了区分作用。
          itemStyle: n.status === '候选'
            ? { borderType: 'dashed', borderWidth: 2, borderColor: theme.graphCandidate }
            : {},
        }
      }),
      links: links.map(l => ({
        source: l.source, target: l.target, relation: l.relation,
        lineStyle: l.status === '候选' ? { type: 'dashed', color: theme.graphCandidate } : {},
      })),
      lineStyle: { color: theme.graphEdge, width: 1.6, curveness: 0.08 },
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
      <el-button link type="primary" @click="doReimport">重新导入基础数据</el-button>
    </div>

    <el-tabs v-model="activeTab" class="graph-tabs">
      <el-tab-pane label="图谱浏览" name="browse">
        <div class="browse-body">
          <aside class="entity-list">
            <div class="list-head">实体结果 <el-tag size="small" type="info">{{ entities.length }}</el-tag></div>
            <div v-for="e in entities" :key="e.name" class="entity-item"
                 :class="{ active: selected?.name === e.name }" @click="focusEntity(e.name)">
              <span class="dot" :style="{ background: TYPE_COLOR[e.type] ?? theme.textColorFaint }" />
              <span class="entity-name">{{ e.name }}</span>
              <el-tag size="small" class="entity-type">{{ e.type }}</el-tag>
            </div>
          </aside>

          <div class="canvas-wrap">
            <div ref="chartRef" class="chart" />
            <!-- 空态插画换成主题色线性图标：el-empty 默认的灰紫插画与墨绿主题不是一套 -->
            <el-empty v-if="!chartReady" class="canvas-empty" description="点击左侧实体查看关系图">
              <template #image>
                <el-icon :size="46" :color="theme.nodeHerb"><Share /></el-icon>
              </template>
            </el-empty>

            <!-- 图例框：浮在图谱底部中央；非悬停时近隐形（仍留 0.12 不透明度让用户感知位置），
                 悬停完全显形；z-index 高于图谱画布，与图谱交叉时覆盖在上层 -->
            <div class="legend-float">
              <span v-for="t in TYPES" :key="t">
                <i :style="{ background: TYPE_COLOR[t] }" />{{ t }}
              </span>
            </div>
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
            </template>
            <el-empty v-else description="选择实体查看详情">
              <template #image>
                <el-icon :size="40" :color="theme.nodeHerb"><Document /></el-icon>
              </template>
            </el-empty>
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
.entity-item:hover { background: v-bind(theme.hoverBg); }
.entity-item.active { background: v-bind(theme.selectedBg); }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.entity-name { flex: 1; }
.entity-type { transform: scale(0.9); }
.canvas-wrap { background: v-bind(theme.cardBg); border: 1px solid v-bind(theme.borderColor); border-radius: v-bind(theme.borderRadius); position: relative; }
.canvas-empty { position: absolute; inset: 0; display: flex; flex-direction: column; justify-content: center; pointer-events: none; }
.chart { width: 100%; height: 640px; }
.detail-head { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; }
.detail-head strong { font-weight: 600; }
.detail-field { margin-bottom: 10px; font-size: 13px; }
.detail-field label { display: block; color: v-bind(theme.textColorSecondary); font-size: 12px; margin-bottom: 2px; }

/* 图谱底部悬浮图例框：始终完全显形；z-index 高于画布，与图谱交叉时覆盖在上层 */
.legend-float {
  position: absolute;
  left: 50%;
  bottom: 12px;
  transform: translateX(-50%);
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 12px;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid v-bind(theme.borderColor);
  border-radius: 999px;
  box-shadow: v-bind(theme.shadowCard);
  font-size: 12px;
  color: v-bind(theme.textColorSecondary);
  z-index: 10;
  pointer-events: auto;
  max-width: 80%;
}
.legend-float span { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
.legend-float i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
</style>
