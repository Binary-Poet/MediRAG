<script setup lang="ts">
// 检索溯源弹窗 —— 规格 P0-4。阶段 2：响应一次返回后渲染全部步骤；阶段 3 换 SSE 逐步点亮。
import { computed } from 'vue'
import type { Trace } from '../../../types/chat'

const props = defineProps<{
  visible: boolean
  trace: Trace | null
}>()

const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()

const steps = [
  { key: 1, label: '问句理解', desc: '实体识别' },
  { key: 2, label: '多路检索', desc: '向量 / 图谱 / 关键词' },
  { key: 3, label: '证据融合', desc: 'RRF 互惠排名融合' },
  { key: 4, label: '相关性排序', desc: 'BGE-reranker 精排' },
  { key: 5, label: '生成回答', desc: 'SSE 流式输出' },
]

// 阶段 2 数据完整返回：全部步骤视为已完成（阶段 3 按 event 推进）
const doneKeys = computed(() => [1, 2, 3, 4, 5])
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="`知识检索与图谱溯源`"
    width="640px"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <!-- 5 步流程条 -->
    <div class="trace-steps">
      <div
        v-for="s in steps"
        :key="s.key"
        class="step"
        :class="{ done: doneKeys.includes(s.key) }"
      >
        <div class="step-dot">{{ s.key }}</div>
        <div class="step-label">{{ s.label }}</div>
      </div>
    </div>

    <template v-if="trace">
      <!-- 步骤 1：原始 vs 改写 -->
      <div class="section">
        <div class="section-title">① 问句理解</div>
        <div class="pair">
          <div class="pair-item">
            <div class="pair-label">原始问题</div>
            <div class="pair-text">{{ trace.understand.raw }}</div>
          </div>
          <div class="pair-item">
            <div class="pair-label">检索查询（改写）</div>
            <div class="pair-text">{{ trace.understand.rewritten }}</div>
          </div>
        </div>
        <div class="entity-line">
          识别实体：
          <el-tag v-for="e in trace.understand.entities" :key="e" size="small" class="tag">{{ e }}</el-tag>
          <span v-if="!trace.understand.entities.length" class="muted">（未识别）</span>
        </div>
      </div>

      <!-- 步骤 2-3：4 数字卡 -->
      <div class="section">
        <div class="section-title">② 多路检索 · ③ 证据融合</div>
        <div class="num-cards">
          <div class="num-card">
            <div class="num">{{ trace.retrieve.vector_n }}</div>
            <div class="num-label">向量检索（语义）</div>
          </div>
          <div class="num-card">
            <div class="num">{{ trace.retrieve.graph_n }}</div>
            <div class="num-label">中医药图谱（{{ trace.retrieve.entity_n }} 命中实体）</div>
          </div>
          <div class="num-card">
            <div class="num">{{ trace.retrieve.keyword_n }}</div>
            <div class="num-label">关键词检索（BM25）</div>
          </div>
          <div class="num-card">
            <div class="num">{{ trace.fuse.candidate_n }}</div>
            <div class="num-label">证据融合（{{ trace.fuse.method }}）</div>
          </div>
        </div>
      </div>

      <!-- 步骤 4：最终证据 + 状态徽章 -->
      <div class="section">
        <div class="section-title">④ 相关性精排</div>
        <div class="final-line">
          <span class="evidence-n">{{ trace.rerank.evidence_n }} 条证据进入回答上下文</span>
          <span class="badge" :class="trace.rerank.evidence_n ? 'ok' : 'empty'">
            {{ trace.rerank.status }}
          </span>
        </div>
      </div>
    </template>
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
.step.done {
  opacity: 1;
}
.step-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #e5e7eb;
  color: #6b7280;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 4px;
  font-size: 13px;
  font-weight: 600;
}
.step.done .step-dot {
  background: #2d6a4f;
  color: #fff;
}
.step-label {
  font-size: 12px;
  color: #1f2937;
}
.section {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
  background: #fafbfa;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
}
.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.pair-item {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 10px;
}
.pair-label {
  font-size: 12px;
  color: #6b7280;
  margin-bottom: 4px;
}
.pair-text {
  font-size: 13px;
  color: #1f2937;
}
.entity-line {
  margin-top: 8px;
  font-size: 13px;
  color: #374151;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.tag {
  margin-right: 0;
}
.muted {
  color: #9ca3af;
}
.num-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.num-card {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  text-align: center;
  padding: 12px 4px;
}
.num {
  font-size: 22px;
  font-weight: 600;
  color: #2d6a4f;
  line-height: 1.2;
}
.num-label {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
  line-height: 1.4;
}
.final-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.evidence-n {
  font-size: 13px;
  color: #1f2937;
}
.badge {
  font-size: 12px;
  border-radius: 999px;
  padding: 3px 12px;
}
.badge.ok {
  background: #dcfce7;
  color: #166534;
}
.badge.empty {
  background: #fef3c7;
  color: #92400e;
}
</style>