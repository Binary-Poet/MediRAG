<script setup lang="ts">
// 检索溯源弹窗 —— 规格 P0-4。阶段 3：由 SSE step 事件数组驱动，随事件逐步点亮。
// activeStep 映射：understand→1、retrieve→2、fuse/reflect→3、rerank→4、generate（生成中）→5。
import { computed } from 'vue'
import { theme } from '../../../styles/theme'
import type { StepEvent } from '../../../types/chat'

const props = defineProps<{
  visible: boolean
  steps: StepEvent[]
}>()

const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

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
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="`知识检索与图谱溯源`"
    width="640px"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <!-- 5 步流程条：已完成=绿，当前=橙（M-10），待执行=灰 -->
    <div class="trace-steps">
      <div
        v-for="s in steps"
        :key="s.key"
        class="step"
        :class="{ active: s.key === activeStep, done: s.key < activeStep }"
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
          <div class="num-label">中医药图谱（{{ retrieve?.entity_n ?? 0 }} 命中实体）</div>
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
  </el-dialog>
</template>

<style scoped>
.trace-steps {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 18px;
}
.step {
  flex: 1;
  text-align: center;
  opacity: 0.45;
}
.step.done,
.step.active {
  opacity: 1;
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
  margin-bottom: 12px;
  background: v-bind(theme.autoSectionBg);
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: v-bind(theme.textColorPrimary);
  margin-bottom: 8px;
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
