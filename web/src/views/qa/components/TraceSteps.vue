<script setup lang="ts">
// 检索溯源内容（无外壳）：5 步流程条 + 各步详情。供 TraceDialog 弹窗与 Chat 思考折叠块共用，
// 样式一处维护。activeStep 映射：understand→1、retrieve→2、fuse/reflect→3、rerank→4、generate→5。
import { computed } from 'vue'
import { theme } from '../../../styles/theme'
import type { StepEvent } from '../../../types/chat'

const props = defineProps<{ steps: StepEvent[]; running?: boolean }>()

const steps = [
  { key: 1, icon: '📝', label: '问句理解', desc: '实体识别' },
  { key: 2, icon: '🔍', label: '多路检索', desc: '向量 / 图谱 / 关键词' },
  { key: 3, icon: '🔄', label: '证据融合', desc: 'RRF 互惠排名融合' },
  { key: 4, icon: '📊', label: '相关性排序', desc: 'BGE-reranker 精排' },
  { key: 5, icon: '✓', label: '生成回答', desc: 'SSE 流式输出' },
]

const stepIndex: Record<string, number> = {
  understand: 1,
  retrieve: 2,
  reflect: 3,
  fuse: 3,
  rerank: 4,
  generate: 5,
  done: 5,
}

/** 当前点亮步：取已到达 step 的最大序号 */
const activeStep = computed(() =>
  props.steps.reduce((acc, ev) => Math.max(acc, stepIndex[ev.step] ?? 0), 0),
)

/** 取某 step 的最后一个事件（多轮时以最新为准） */
function ev(step: string): StepEvent | undefined {
  for (let i = props.steps.length - 1; i >= 0; i--) {
    if (props.steps[i].step === step) return props.steps[i]
  }
  return undefined
}

const understand = computed(() => ev('understand'))
const retrieve = computed(() => ev('retrieve'))
const fuse = computed(() => ev('fuse'))
const rerank = computed(() => ev('rerank'))
const reflect = computed(() => ev('reflect'))

/** 图谱定向路径模板的中文说明（后端 path_template 枚举，未知值原样兜底） */
const TEMPLATE_LABELS: Record<string, string> = {
  symptom_to_formula: '症状 → 证候 → 方剂（多症状共现排序）',
  syndrome_to_formula: '证候 → 方剂（合病/复合证型）',
  formula_mechanism: '方剂 → 组成 → 中药 → 功效（配伍机制链）',
}
function templateLabel(t: string): string {
  return TEMPLATE_LABELS[t] || t
}
</script>

<template>
  <!-- 5 步流程条：已完成=绿，当前=橙（M-10），待执行=灰。
       「当前」只在流程真正运行时点亮：否则回答生成结束后第 5 步会永久停在
       「进行中」的橙色上，看起来像还在跑（而橙色在别处又表示自反思告警）。 -->
  <div class="trace-steps">
    <div
      v-for="s in steps"
      :key="s.key"
      class="step"
      :class="{
        active: s.key === activeStep && running,
        done: s.key < activeStep || (s.key === activeStep && !running),
      }"
    >
      <div class="step-dot">{{ s.icon }}</div>
      <div class="step-label">{{ s.label }}</div>
    </div>
  </div>

  <!-- 步骤 1：原始 vs 改写 -->
  <div v-if="understand" class="section">
    <div class="section-title">① 问句理解</div>
    <div class="pair">
      <div class="pair-item">
        <div class="pair-label">原始问题</div>
        <div class="pair-text">{{ understand.raw }}</div>
      </div>
      <div class="pair-item">
        <div class="pair-label">检索查询（改写）</div>
        <div class="pair-text">{{ understand.rewritten }}</div>
      </div>
    </div>
    <div class="entity-line">
      识别实体：
      <el-tag v-for="e in understand.entities" :key="e" size="small" class="tag">{{ e }}</el-tag>
      <span v-if="!understand.entities?.length" class="muted">（未识别）</span>
    </div>
    <!-- 查询分解：复合意图拆成多个子查询时展示，单查询不显示（避免小题大做） -->
    <div v-if="(understand.sub_queries?.length ?? 0) > 1" class="entity-line">
      查询分解（{{ understand.sub_queries!.length }} 个子查询）：
      <el-tag v-for="(q, i) in understand.sub_queries" :key="i" size="small" class="tag">
        {{ q }}
      </el-tag>
    </div>
  </div>

  <!-- 步骤 2-3：4 数字卡 + 自反思提示 -->
  <div v-if="retrieve || fuse" class="section">
    <div class="section-title">② 多路检索 · ③ 证据融合</div>
    <div class="num-cards">
      <div class="num-card">
        <div class="num">{{ retrieve?.vector_n ?? '—' }}</div>
        <div class="num-label">向量检索（语义）</div>
      </div>
      <div class="num-card">
        <div class="num">{{ retrieve?.graph_n ?? '—' }}</div>
        <!-- 文案缩短：原「中医药图谱（N 命中实体）」在 640px 弹窗的四分栏里必然折行，
             且断点落在词中间（「命中实/体）」），四张卡视觉不齐 -->
        <div class="num-label">图谱（命中 {{ retrieve?.entity_n ?? 0 }} 实体）</div>
      </div>
      <div class="num-card">
        <div class="num">{{ retrieve?.keyword_n ?? '—' }}</div>
        <div class="num-label">关键词检索（BM25）</div>
      </div>
      <div class="num-card">
        <div class="num">{{ fuse?.candidate_n ?? '—' }}</div>
        <div class="num-label">证据融合（{{ fuse?.method ?? '—' }}）</div>
      </div>
    </div>
    <!-- 图谱定向路径模板：解释「图谱这次怎么走的」（无向邻居时不显示） -->
    <div v-if="retrieve?.path_template" class="reflect-line">
      图谱路径模板：{{ templateLabel(retrieve.path_template) }}
      <span v-if="retrieve.graph_dropped_n">，锚定过滤剔除 {{ retrieve.graph_dropped_n }} 条旁支</span>
    </div>
    <!-- 自反思触发时显示一轮「重查」提示（合并方案扩充项） -->
    <div v-if="reflect" class="reflect-line">
      自反思（第 {{ reflect.round ?? 1 }} 轮）：{{ reflect.reason || '检索质量不足' }}，触发重新检索
    </div>
  </div>

  <!-- 步骤 4：最终证据 + 状态徽章 -->
  <div v-if="rerank" class="section">
    <div class="section-title">④ 相关性精排</div>
    <div class="final-line">
      <span class="evidence-n">{{ rerank.evidence_n }} 条证据进入回答上下文</span>
      <span class="badge" :class="rerank.status === '知识库未匹配' ? 'empty' : 'ok'">
        {{ rerank.status }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.trace-steps {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 14px;
}
.step {
  flex: 1;
  text-align: center;
}
/* 待执行步只淡化圆点，标签保持可读：原先整步 0.45 透明，流程全貌反而读不出来 */
.step:not(.done):not(.active) .step-dot {
  opacity: 0.45;
}
.step:not(.done):not(.active) .step-label {
  color: v-bind(theme.textColorMuted);
}
.step-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: v-bind(theme.borderColor);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 4px;
  font-size: 14px;
}
.step.done .step-dot {
  background: v-bind(theme.colorSuccess);
}
.step.active .step-dot {
  background: v-bind(theme.colorWarning);
}
.step-label {
  font-size: 12px;
  color: v-bind(theme.textColorPrimary);
}
.section {
  border: 1px solid v-bind(theme.borderColor);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
  /* 常驻浅底用 autoSectionBg，不用 hoverBg：
     hoverBg 是交互反馈色，当静态底色用会让 hover 无颜色可加深，且满屏偏绿抢内容。 */
  background: v-bind(theme.autoSectionBg);
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: v-bind(theme.textColorPrimary);
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid v-bind(theme.colorPrimary);
  line-height: 1.4;
}
.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.pair-item {
  background: v-bind(theme.cardBg);
  border: 1px solid v-bind(theme.borderColor);
  border-radius: 6px;
  padding: 8px 10px;
}
.pair-label {
  font-size: 12px;
  color: v-bind(theme.textColorSecondary);
  margin-bottom: 4px;
}
.pair-text {
  font-size: 13px;
  color: v-bind(theme.textColorPrimary);
}
.entity-line {
  margin-top: 8px;
  font-size: 13px;
  color: v-bind(theme.textColorBody);
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.tag {
  margin-right: 0;
}
.muted {
  color: v-bind(theme.textColorMuted);
}
.num-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.num-card {
  background: v-bind(theme.cardBg);
  border: 1px solid v-bind(theme.borderColor);
  border-radius: 8px;
  text-align: center;
  padding: 12px 4px;
}
.num {
  font-size: 22px;
  font-weight: 600;
  color: v-bind(theme.colorPrimary);
  line-height: 1.2;
}
.num-label {
  font-size: 12px;
  color: v-bind(theme.textColorSecondary);
  margin-top: 4px;
  line-height: 1.4;
}
.reflect-line {
  margin-top: 10px;
  font-size: 12px;
  border-radius: 6px;
  padding: 6px 10px;
  background: v-bind(theme.warningBg);
  color: v-bind(theme.warningText);
}
.final-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.evidence-n {
  font-size: 13px;
  color: v-bind(theme.textColorPrimary);
}
.badge {
  font-size: 12px;
  border-radius: 999px;
  padding: 3px 12px;
}
.badge.ok {
  background: v-bind(theme.safetyBg);
  color: v-bind(theme.safetyText);
}
.badge.empty {
  background: v-bind(theme.warningBg);
  color: v-bind(theme.warningText);
}
</style>
