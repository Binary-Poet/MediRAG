<script setup lang="ts">
// 阶段 3 回答态：SSE 打字机（token 流式）+ 空态 5 常用问题卡片 + 溯源弹窗随 step 事件逐步点亮
// 规格 P0-2 空态 / P0-3 回答态 / P0-4 溯源弹窗
import { nextTick, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamChat } from '../../api/chat'
import { authHeaders } from '../../api/http'
import { theme } from '../../styles/theme'
import type { GraphFact, Reference, StepEvent } from '../../types/chat'
import TraceDialog from './components/TraceDialog.vue'

interface QA {
  question: string
  answer: string
  references: Reference[]
  graphFacts: GraphFact[]
  safety: { type: string; message: string } | null
  trace: StepEvent[]
  feedback?: boolean
}

const suggestions = [
  '四君子汤由哪些中药组成？',
  '脾气虚常见哪些症状和方剂？',
  '风寒束表与风热犯表有什么区别？',
  '酸枣仁汤的组成、功效和禁忌是什么？',
  '失眠在中医药知识图谱中关联哪些证候？',
]

const featureTags = ['📋 典籍原文引用', '🔗 实体关系溯源', '✓ 知识审核发布']

const messages = ref<QA[]>([])
const input = ref('')
const loading = ref(false)
const listRef = ref<HTMLElement>()
const sessionId = (globalThis.crypto?.randomUUID?.() ?? `s-${Math.random().toString(36).slice(2)}`)
const traceVisible = ref(false)
const currentTrace = ref<StepEvent[]>([])

async function scrollToBottom() {
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
}

async function send(q?: string) {
  const question = (q ?? input.value).trim()
  if (!question || loading.value) return
  input.value = ''
  loading.value = true
  // reactive：流式回调闭包直接 mutate 代理对象才能触发视图更新
  //（普通对象 push 进 messages 后，闭包持原始引用 mutate 不触发任何 effect）
  const item = reactive<QA>({ question, answer: '', references: [], graphFacts: [], safety: null, trace: [] })
  messages.value.push(item)
  currentTrace.value = []
  traceVisible.value = true
  await scrollToBottom()

  try {
    await streamChat(question, {
      onStep: (ev) => {
        item.trace.push(ev)
        currentTrace.value = [...item.trace]
      },
      onToken: (text) => {
        if (!item.answer && item.trace.length) {
          // 首个 token 到达：点亮第 5 步「生成回答」
          item.trace.push({ step: 'generate' })
          currentTrace.value = [...item.trace]
        }
        item.answer += text
        scrollToBottom()
      },
      onReferences: (refs, gfs) => {
        item.references = refs
        item.graphFacts = gfs
        scrollToBottom()
      },
      onSafety: (type, message) => {
        item.safety = { type, message }
      },
      onError: (detail) => {
        // 后端 error 事件：保留已流式内容，仅在尚无输出时给失败话术
        if (!item.answer) item.answer = `请求失败：${detail}`
      },
      onDone: () => {},
    }, sessionId)
  } catch (e) {
    item.answer ||= `请求失败：${(e as Error).message}`
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

function openTrace(t: StepEvent[]) {
  currentTrace.value = t
  traceVisible.value = true
}

/** 有用/无用反馈：先乐观置位并禁用两按钮，提交失败则回退允许重试（规格 P1 反馈入口）。 */
async function sendFeedback(m: QA, useful: boolean) {
  m.feedback = useful
  try {
    const resp = await fetch('/api/feedback', {
      method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ session_id: sessionId, useful }),
    })
    if (!resp.ok) throw new Error(`反馈提交失败（${resp.status}）`)
  } catch (e) {
    m.feedback = undefined
    ElMessage.error((e as Error).message)
  }
}

/** Enter 发送 / Shift+Enter 换行；IME 组合中（isComposing 或 keyCode 229）不触发 */
function onEnter(e: KeyboardEvent) {
  if (e.isComposing || e.keyCode === 229) return
  if (!e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="chat-page">
    <div v-if="messages.length === 0" class="empty">
      <div class="empty-sub">文献与图谱联合检索</div>
      <h3 class="empty-title">开始一次可追溯的辨证问答</h3>
      <p class="empty-desc">
        提出关于证候、方剂、中药或经典条文的问题，回答将尽可能附带原文证据和图谱关系。
      </p>
      <div class="feature-tags">
        <span v-for="t in featureTags" :key="t" class="feature-tag">{{ t }}</span>
      </div>

      <div class="suggestion-block">
        <div class="suggestion-head">
          <span class="suggestion-title">常用问题</span>
          <span class="suggestion-hint">选择一个示例快速开始</span>
        </div>
        <button v-for="s in suggestions" :key="s" class="suggestion-card" @click="send(s)">
          <span>{{ s }}</span>
          <span class="suggestion-arrow">›</span>
        </button>
      </div>
    </div>

    <div v-else ref="listRef" class="msg-list">
      <div v-for="(m, i) in messages" :key="i" class="qa-item">
        <div class="q">{{ m.question }}</div>
        <el-card class="a" shadow="never">
          <!-- 安全事件提示框（急症/低置信度兜底，橙底）——置于回答顶部：
               急症话术/拒答提示优先；低置信时正文为空、仅显示本框 -->
          <div v-if="m.safety && m.safety.type !== 'ok'" class="safety-box warn">
            {{ m.safety.message }}
          </div>

          <!-- 正文：低置信（无生成内容）时不渲染占位，避免与框内话术重复 -->
          <div
            v-if="m.answer || m.safety?.type !== 'low_confidence'"
            class="answer-text"
          >
            {{ m.answer || '正在生成…' }}<span
              v-if="loading && i === messages.length - 1 && m.answer"
              class="cursor"
            />
          </div>

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
            <div class="gf-src">文献来源：内置中医药教学演示数据（需专业审核）</div>
          </div>

          <!-- 检索溯源按钮 -->
          <div class="trace-entry">
            <el-button link type="primary" :disabled="!m.trace.length" @click="openTrace(m.trace)">
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

          <!-- 有用/无用反馈（规格 P1 入口） -->
          <div v-if="m.answer" class="feedback">
            <span class="fb-label">此回答有帮助吗？</span>
            <el-button link size="small" :type="m.feedback === true ? 'primary' : ''"
                       :disabled="m.feedback !== undefined" @click="sendFeedback(m, true)">有用</el-button>
            <el-button link size="small" :type="m.feedback === false ? 'danger' : ''"
                       :disabled="m.feedback !== undefined" @click="sendFeedback(m, false)">无用</el-button>
          </div>
        </el-card>
      </div>
    </div>

    <div class="input-bar">
      <el-input
        v-model="input"
        type="textarea"
        :autosize="{ minRows: 1, maxRows: 4 }"
        resize="none"
        placeholder="输入中医药知识问题，按 Enter 发送 (Shift+Enter 换行)"
        :disabled="loading"
        @keydown.enter="onEnter"
      />
      <el-button type="primary" :loading="loading" @click="send()">发送</el-button>
    </div>
    <p class="disclaimer">本答案仅提供中医药知识科普，不替代辨证、诊断或个体化处方。如有紧急情况请拨打 120。</p>

    <TraceDialog v-model:visible="traceVisible" :steps="currentTrace" />
  </div>
</template>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: v-bind(theme.cardBg);
  border-radius: v-bind(theme.borderRadius);
  border: 1px solid v-bind(theme.borderColor);
  overflow: hidden;
}

.empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: v-bind(theme.textColorSecondary);
  padding: 24px;
  overflow-y: auto;
}

.empty-sub {
  font-size: 13px;
  color: v-bind(theme.colorPrimary);
  font-weight: 600;
  letter-spacing: 1px;
}

.empty-title {
  margin: 8px 0 6px;
  font-size: 22px;
  color: v-bind(theme.textColorPrimary);
}

.empty-desc {
  margin: 0;
  font-size: 14px;
  max-width: 520px;
  text-align: center;
  line-height: 1.7;
}

.feature-tags {
  display: flex;
  gap: 12px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.feature-tag {
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 999px;
  background: v-bind(theme.hoverBg);
  color: v-bind(theme.colorPrimary);
}

.suggestion-block {
  width: min(560px, 100%);
  margin-top: 28px;
}

.suggestion-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 8px;
}

.suggestion-title {
  font-size: 14px;
  font-weight: 600;
  color: v-bind(theme.textColorPrimary);
}

.suggestion-hint {
  font-size: 12px;
  color: v-bind(theme.textColorMuted);
}

.suggestion-card {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: v-bind(theme.autoSectionBg);
  border: 1px solid v-bind(theme.borderColor);
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 8px;
  font-size: 14px;
  color: v-bind(theme.textColorBody);
  cursor: pointer;
  transition: border-color 0.2s;
  font-family: inherit;
}

.suggestion-card:hover {
  border-color: v-bind(theme.colorPrimary);
  color: v-bind(theme.colorPrimary);
}

.suggestion-arrow {
  color: v-bind(theme.colorPrimary);
  font-size: 16px;
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
  background: v-bind(theme.colorPrimary);
  color: v-bind(theme.cardBg);
  border-radius: 10px 10px 0 10px;
  padding: 8px 14px;
  margin-bottom: 10px;
  max-width: 70%;
}

.a {
  background: v-bind(theme.autoSectionBg);
  border-color: v-bind(theme.borderColor);
}

.answer-text {
  white-space: pre-wrap;
  line-height: 1.8;
}

.cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -2px;
  background: v-bind(theme.colorPrimary);
  animation: blink 0.9s step-start infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
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

.safety-box.warn {
  background: v-bind(theme.warningBg);
  color: v-bind(theme.warningText);
}

.graph-facts {
  margin-top: 12px;
  font-size: 13px;
  color: v-bind(theme.textColorBody);
}

.gf-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.gf-item {
  padding: 2px 0;
}

.gf-src {
  margin-top: 4px;
  color: v-bind(theme.textColorMuted);
}

.trace-entry {
  margin-top: 10px;
}

.refs {
  margin-top: 12px;
  border-top: 1px dashed v-bind(theme.borderColor);
}

.feedback {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
}

.fb-label {
  color: v-bind(theme.textColorMuted);
}

.ref-item {
  font-size: 13px;
  color: v-bind(theme.textColorBody);
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
  align-items: flex-end;
  padding: 14px 20px 6px;
  border-top: 1px solid v-bind(theme.borderColor);
}

.disclaimer {
  text-align: center;
  font-size: 12px;
  color: v-bind(theme.textColorMuted);
  margin: 0 0 10px;
}
</style>
