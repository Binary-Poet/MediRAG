<script setup lang="ts">
// 阶段 2 回答态：回答卡（安全框 / 图谱事实 / 溯源入口 / 证据折叠）+ 溯源弹窗（规格 P0-4 / P0-3）
import { nextTick, ref } from 'vue'
import { askQuestion } from '../../api/chat'
import { theme } from '../../styles/theme'
import type { Reference, Trace } from '../../types/chat'
import TraceDialog from './components/TraceDialog.vue'

interface QA {
  question: string
  answer: string
  references: Reference[]
  graphFacts: { source: string; relation: string; target: string }[]
  trace: Trace | null
}

const messages = ref<QA[]>([])
const input = ref('')
const loading = ref(false)
const listRef = ref<HTMLElement>()

const traceVisible = ref(false)
const currentTrace = ref<Trace | null>(null)

const suggestions = ['四君子汤由哪些中药组成？', '风寒束表与风热犯表有什么区别？', '人参的功效有哪些？']

async function send(q?: string) {
  const question = (q ?? input.value).trim()
  if (!question || loading.value) return
  input.value = ''
  loading.value = true
  messages.value.push({ question, answer: '', references: [], graphFacts: [], trace: null })
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight })

  try {
    const resp = await askQuestion(question)
    messages.value[messages.value.length - 1] = {
      question,
      answer: resp.answer,
      references: resp.references,
      graphFacts: resp.graph_facts,
      trace: resp.trace,
    }
    currentTrace.value = resp.trace
    traceVisible.value = true
  } catch (e) {
    messages.value[messages.value.length - 1].answer = `请求失败：${(e as Error).message}`
  } finally {
    loading.value = false
    await nextTick()
    listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
  }
}

function openTrace(t: Trace | null) {
  currentTrace.value = t
  traceVisible.value = true
}
</script>

<template>
  <div class="chat-page">
    <div v-if="messages.length === 0" class="empty">
      <h3>开始一次可追溯的辨证问答</h3>
      <p>提出关于证候、方剂、中药或经典条文的问题，回答将附带文献证据。</p>
      <div class="suggestions">
        <el-button v-for="s in suggestions" :key="s" plain @click="send(s)">{{ s }}</el-button>
      </div>
    </div>

    <div v-else ref="listRef" class="msg-list">
      <div v-for="(m, i) in messages" :key="i" class="qa-item">
        <div class="q">{{ m.question }}</div>
        <el-card class="a" shadow="never">
          <div class="answer-text">{{ m.answer || '正在生成…' }}</div>

          <!-- 绿色安全提示框（有图谱事实时显示） -->
          <div v-if="m.graphFacts.length" class="safety-box">
            注意：以上组成信息严格依据图谱事实，不包含加减变化或现代制剂衍变；实际临床应用须经中医师辨证后使用，不可自行套方。
          </div>

          <!-- 图谱事实区 -->
          <div v-if="m.graphFacts.length" class="graph-facts">
            <div class="gf-title">图谱依据：</div>
            <div v-for="(f, k) in m.graphFacts" :key="k" class="gf-item">
              【图谱事实{{ k + 1 }}】 {{ f.source }} --{{ f.relation }}--> {{ f.target }}
            </div>
          </div>

          <!-- 检索溯源按钮 -->
          <div class="trace-entry">
            <el-button link type="primary" :disabled="!m.trace" @click="openTrace(m.trace)">
              知识检索与图谱溯源
            </el-button>
          </div>

          <el-collapse v-if="m.references.length" class="refs">
            <el-collapse-item :title="`证据来源 (${m.references.length})`">
              <div v-for="(r, j) in m.references" :key="r.chunk_id" class="ref-item">
                <span class="ref-tag graph">文献</span>
                [{{ j + 1 }}] {{ r.title }} —— {{ r.doc_name }} · {{ r.chapter }} · 序号 {{ r.page_no }}
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-card>
      </div>
    </div>

    <div class="input-bar">
      <el-input
        v-model="input"
        placeholder="输入中医药知识问题，按 Enter 发送"
        :disabled="loading"
        @keyup.enter="send()"
      />
      <el-button type="primary" :loading="loading" @click="send()">发送</el-button>
    </div>
    <p class="disclaimer">本草智问仅提供中医药知识科普，不替代辨证、诊断或个体化处方。如有紧急情况请拨打 120。</p>

    <TraceDialog v-model:visible="traceVisible" :trace="currentTrace" />
  </div>
</template>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  overflow: hidden;
}

.empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #6b7280;
}

.suggestions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
}

.msg-list {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px;
}

.qa-item {
  margin-bottom: 24px;
}

.q {
  display: inline-block;
  background: #2d6a4f;
  color: #fff;
  border-radius: 10px 10px 0 10px;
  padding: 8px 14px;
  margin-bottom: 10px;
  max-width: 70%;
}

.a {
  background: #f8faf9;
  border-color: #e5e7eb;
}

.answer-text {
  white-space: pre-wrap;
  line-height: 1.8;
}

.safety-box {
  margin-top: 12px;
  background: v-bind(theme.safetyBg);
  color: v-bind(theme.safetyText);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.6;
}

.graph-facts {
  margin-top: 12px;
  font-size: 13px;
  color: #374151;
}

.gf-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.gf-item {
  padding: 2px 0;
}

.trace-entry {
  margin-top: 10px;
}

.refs {
  margin-top: 12px;
  border-top: 1px dashed #e5e7eb;
}

.ref-item {
  font-size: 13px;
  color: #374151;
  padding: 2px 0;
}

.ref-tag {
  display: inline-block;
  font-size: 11px;
  border-radius: 4px;
  padding: 1px 6px;
  margin-right: 6px;
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary-dark-2);
}

.input-bar {
  display: flex;
  gap: 10px;
  padding: 14px 20px 6px;
  border-top: 1px solid #e5e7eb;
}

.disclaimer {
  text-align: center;
  font-size: 12px;
  color: #9ca3af;
  margin: 0 0 10px;
}
</style>