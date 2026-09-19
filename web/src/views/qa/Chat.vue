<script setup lang="ts">
// 阶段 3 回答态：SSE 打字机（token 流式）+ 空态 5 常用问题卡片 + 溯源弹窗随 step 事件逐步点亮
// 规格 P0-2 空态 / P0-3 回答态 / P0-4 溯源弹窗
import { nextTick, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamChat, withdrawRound } from '../../api/chat'
import { authHeaders } from '../../api/http'
import { theme } from '../../styles/theme'
import type { GraphFact, Reference, StepEvent } from '../../types/chat'
import SessionList from './components/SessionList.vue'
import { useSessionStore } from '../../stores/session'
import TraceDialog from './components/TraceDialog.vue'
import TraceSteps from './components/TraceSteps.vue'

interface QA {
  question: string
  answer: string
  references: Reference[]
  graphFacts: GraphFact[]
  safety: { type: string; message: string } | null
  trace: StepEvent[]
  thinkingExpanded: boolean
  thinkingInteracted?: boolean
  feedback?: boolean
  /** 本轮提问在服务端的 seq：撤回时按它精确定位该轮，缺省（流式中断等）只能撤末轮 */
  userSeq?: number
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
const inputRef = ref<{ focus: () => void }>()
const traceVisible = ref(false)
const currentTrace = ref<StepEvent[]>([])

const sessionStore = useSessionStore()

/** 新建对话：清空问答区并解绑当前会话（首个提问由后端建会话） */
function newSession() {
  if (loading.value) return   // 流式进行中不切换，避免清空消息区后 onDone 把 activeId 设到别的会话
  messages.value = []
  sessionStore.activeId = ''
  currentTrace.value = []
  input.value = ''            // 输入框是当前会话的草稿：换会话即作废
}

/** 打开历史会话：把落库 payload 还原成现有 QA 结构，复用同一套卡片渲染 */
async function openSession(id: string) {
  if (loading.value) return
  // 输入框里可能是上一轮撤回后回填的提问，切到别的会话就该清空，避免误发到新会话
  input.value = ''
  try {
    const msgs = await sessionStore.loadMessages(id)
    const built: QA[] = []
    for (let i = 0; i < msgs.length; i += 1) {
      const m = msgs[i]
      if (m.role !== 'user') continue
      const a = msgs[i + 1]?.role === 'assistant' ? msgs[i + 1] : null
      const trace = [...(a?.payload?.trace ?? [])]
      // 低置信拒答无 LLM 生成：后端把兜底话术同时写进 content 与 safety.message。
      // 实时态靠「无 token → answer 为空」抑制正文，回放必须复刻同一规则，否则同一句话渲染两遍。
      const refused = a?.payload?.safety?.type === 'low_confidence'
      // 实时态在首个 token 时补一步合成步「生成回答」；trace 里没有它，回放要补上，否则第 5 步永远点不亮
      if (!refused && a?.content && trace.length) trace.push({ step: 'generate' })
      built.push(reactive<QA>({
        question: m.content,
        answer: refused ? '' : (a?.content ?? ''),
        references: a?.payload?.references ?? [],
        graphFacts: a?.payload?.graph_facts ?? [],
        safety: a?.payload?.safety ?? null,
        trace,
        thinkingExpanded: false,
        userSeq: m.seq,
      }))
    }
    messages.value = built
    sessionStore.activeId = id
    currentTrace.value = []
    await scrollToBottom()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/** 删除的若是当前会话，问答区复位到空态 */
function onDeleted(id: string) {
  if (sessionStore.activeId === id) newSession()
}

async function scrollToBottom() {
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
}

/** 该条是否处于「思考中」：请求进行中、尚无 token、且是最后一条。
    后端第一个 step 事件要等 understand 节点跑完才发出，此前 trace 为空，
    思考块不能只靠 trace.length 判断，否则这段空窗期只显示正文占位。 */
function isThinking(i: number, m: QA): boolean {
  return loading.value && i === messages.value.length - 1 && !m.answer
}

async function send(q?: string) {
  const question = (q ?? input.value).trim()
  if (!question || loading.value) return
  input.value = ''
  loading.value = true
  // reactive：流式回调闭包直接 mutate 代理对象才能触发视图更新
  //（普通对象 push 进 messages 后，闭包持原始引用 mutate 不触发任何 effect）
  const item = reactive<QA>({ question, answer: '', references: [], graphFacts: [], safety: null, trace: [], thinkingExpanded: true })
  messages.value.push(item)
  currentTrace.value = []
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
        if (!item.answer && !item.thinkingInteracted) {
          // 首个 token：思考完成，自动折叠为「已深度思考」（用户已手动操作过则保留其展开态）
          item.thinkingExpanded = false
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
      onDone: (data) => {
        // 认领会话 id：新会话由后端在本轮创建，前端据此激活并刷新列表
        // 可选链：done 事件 data 为空时后端传出 null，直接取 .message_id 会抛 TypeError
        if (data?.message_id) sessionStore.activeId = data.message_id
        item.userSeq = data?.user_seq   // 本轮 seq，供「撤回」精确定位
        sessionStore.refresh().catch(() => {})   // 列表刷新失败不影响本轮回答
      },
    }, sessionStore.activeId || undefined)
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

/** 撤回图标提示：末轮是「撤回这一轮」，非末轮会把后面的轮次一并回滚 */
function withdrawTip(i: number): string {
  return i === messages.value.length - 1
    ? '撤回本轮提问，放回输入框重新编辑'
    : '撤回本轮及其之后的全部问答，回到该提问之前的状态'
}

/** 撤回：回到「该提问还没问」时的对话状态。
 *
 * 语义是回滚——该轮及其之后的轮次一起撤掉，之前的轮次保留（只挖掉中间一轮会让
 * 后续轮次失去它们本就依赖的上下文）；服务端同步删除，否则重开会话会复活、
 * 且会通过 recent_history 混进后续提问的多轮上下文。撤到没有轮次时连会话一起结束。
 */
async function withdraw(i: number) {
  if (loading.value) return          // 流式进行中不改动，避免 SSE 回调继续写已移除的对象
  const m = messages.value[i]
  if (!m) return

  const sid = sessionStore.activeId
  // userSeq 缺失只可能来自「流式中断、没收到 done」的那一轮，而它必然是末轮；
  // 非末轮又拿不到 seq 时不动服务端，宁可少删也不删错轮。
  if (sid && (m.userSeq !== undefined || i === messages.value.length - 1)) {
    try {
      const r = await withdrawRound(sid, m.userSeq)
      if (r.session_deleted) sessionStore.activeId = ''
      sessionStore.refresh().catch(() => {})   // 列表刷新失败不回滚，问答区已经撤回
    } catch (e) {
      ElMessage.error((e as Error).message)
      return                                  // 服务端失败就不动本地，避免界面与库不一致
    }
  }

  input.value = m.question
  messages.value.splice(i)            // 与后端一致：该轮及其之后一起撤掉
  if (!messages.value.length) sessionStore.activeId = ''
  await nextTick()
  inputRef.value?.focus()
}

/** 有用/无用反馈：先乐观置位并禁用两按钮，提交失败则回退允许重试（规格 P1 反馈入口）。 */
async function sendFeedback(m: QA, useful: boolean) {
  m.feedback = useful
  try {
    const resp = await fetch('/api/feedback', {
      method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ session_id: sessionStore.activeId, useful }),
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
  <div class="chat-wrap">
    <SessionList
      @create="newSession"
      @select="openSession"
      @deleted="onDeleted"
      @cleared="newSession"
    />

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

          <!-- 思考过程折叠块（DeepSeek 风格）：发送即出现（此时流程条全灰），逐步点亮，首个 token 后自动折叠 -->
          <div
            v-if="m.trace.length || isThinking(i, m)"
            class="thinking"
            :class="{ open: m.thinkingExpanded, running: isThinking(i, m) }"
          >
            <div class="thinking-head" @click="m.thinkingInteracted = true; m.thinkingExpanded = !m.thinkingExpanded">
              <span class="thinking-dot" />
              <span class="thinking-title">思考过程</span>
              <span class="thinking-status">
                <span v-if="isThinking(i, m)">思考中…</span>
                <span v-else>已深度思考</span>
              </span>
              <span class="thinking-arrow">{{ m.thinkingExpanded ? '▾' : '▸' }}</span>
            </div>
            <div v-if="m.thinkingExpanded" class="thinking-body">
              <TraceSteps :steps="m.trace" :running="loading && i === messages.length - 1" />
            </div>
          </div>

          <!-- 正文：思考阶段由思考块承担进度指示，此处不出占位；低置信（无生成内容）时也不渲染 -->
          <div
            v-if="m.answer || (m.safety?.type !== 'low_confidence' && !isThinking(i, m))"
            class="answer-text"
          >
            {{ m.answer }}<span
              v-if="loading && i === messages.length - 1 && m.answer"
              class="cursor"
            />
          </div>

          <!-- 绿色安全提示框（有图谱事实时显示） -->
          <div v-if="m.graphFacts.length" class="safety-box">
            注意：以上组成信息严格依据图谱事实，不包含加减变化或现代制剂衍变；实际临床应用须经中医师辨证后使用，不可自行套方。
          </div>

          <!-- 图谱依据：与「证据来源」同款折叠块，默认折叠。
               图谱事实在生成结束后才随 references 事件下发，折叠不会遮挡流式过程；
               不绑 v-model，展开态由 el-collapse 内部维护，回放历史会话同样默认折叠。 -->
          <el-collapse v-if="m.graphFacts.length" class="fold">
            <el-collapse-item :title="`图谱依据 (${m.graphFacts.length})`">
              <div v-for="(f, k) in m.graphFacts" :key="k" class="gf-item">
                【图谱事实{{ k + 1 }}】 {{ f.source }} --{{ f.relation }}--> {{ f.target }}
              </div>
              <div class="gf-src">文献来源：内置中医药教学演示数据（需专业审核）</div>
            </el-collapse-item>
          </el-collapse>

          <el-collapse v-if="m.references.length" class="fold">
            <el-collapse-item :title="`证据来源 (${m.references.length})`">
              <div v-for="(r, j) in m.references" :key="r.chunk_id" class="ref-item">
                <span class="ref-tag graph">文献</span>
                [{{ j + 1 }}] {{ r.title }} —— {{ r.doc_name }} · {{ r.chapter }} · 序号 {{ r.page_no }}
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 检索溯源按钮：置于两个折叠块之下，避免夹在「图谱依据」与「证据来源」中间 -->
          <div class="trace-entry">
            <el-button link type="primary" :disabled="!m.trace.length" @click="openTrace(m.trace)">
              知识检索与图谱溯源
            </el-button>
          </div>

          <!-- 卡片底部操作行：左「反馈」、右「撤回本轮」（规格 P1 反馈入口 + 撤回） -->
          <div v-if="!isThinking(i, m)" class="answer-actions">
            <div v-if="m.answer" class="feedback">
              <span class="fb-label">此回答有帮助吗？</span>
              <el-button link size="small" :type="m.feedback === true ? 'primary' : ''"
                         :disabled="m.feedback !== undefined" @click="sendFeedback(m, true)">有用</el-button>
              <el-button link size="small" :type="m.feedback === false ? 'danger' : ''"
                         :disabled="m.feedback !== undefined" @click="sendFeedback(m, false)">无用</el-button>
            </div>
            <el-tooltip :content="withdrawTip(i)" placement="top">
              <el-button class="withdraw" link :disabled="loading" @click="withdraw(i)">
                <el-icon><RefreshLeft /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
        </el-card>
      </div>
    </div>

    <div class="input-bar">
      <el-input
        ref="inputRef"
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

    <TraceDialog v-model:visible="traceVisible" :steps="currentTrace" :running="loading" />
    </div>
  </div>
</template>

<style scoped>
.chat-wrap {
  display: flex;
  gap: 14px;
  height: 100%;
  align-items: stretch;
}

.chat-page {
  flex: 1;
  min-width: 0;
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
  font-weight: 600;
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
  /* 卡片内「思考过程 → 回答正文 → 注意事项」等相邻区块共用的纵向间距。
     正文原先上边距为 0、下边距 12px，视觉上像被思考块粘住，故两侧取同一值。 */
  --qa-block-gap: 12px;
  background: v-bind(theme.autoSectionBg);
  border-color: v-bind(theme.borderColor);
}

.answer-text {
  margin-top: var(--qa-block-gap);
  white-space: pre-wrap;
  line-height: 1.8;
}

/* 没有思考块时正文就是卡片首个子元素，不该再撑开上间距（否则上 32px、下 20px 不对称） */
.answer-text:first-child {
  margin-top: 0;
}

.thinking {
  margin-top: 10px;
  border: 1px solid v-bind(theme.borderColor);
  border-radius: 8px;
  background: v-bind(theme.autoSectionBg);
  overflow: hidden;
}
.thinking-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}
.thinking-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: v-bind(theme.colorPrimary);
}
.thinking.running .thinking-dot {
  animation: thinking-pulse 1.1s ease-in-out infinite;
}
@keyframes thinking-pulse {
  0%,
  100% {
    opacity: 0.35;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.25);
  }
}
.thinking-title {
  font-size: 13px;
  font-weight: 600;
  color: v-bind(theme.textColorPrimary);
}
.thinking-status {
  font-size: 12px;
  color: v-bind(theme.textColorMuted);
}
.thinking.running .thinking-status {
  color: v-bind(theme.colorPrimary);
}
.thinking-arrow {
  margin-left: auto;
  font-size: 12px;
  color: v-bind(theme.textColorSecondary);
}
.thinking-body {
  border-top: 1px dashed v-bind(theme.borderColor);
  padding: 10px 12px 12px;
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

/* 常规提示（图谱事实说明）：弱底 + 左侧色条。
   原先满饱和的 #dcfce7 满宽色块是整页最重的色块，把回答正文挤成了次要元素；
   这段提示命中图谱事实就会出现、频率极高，弱化后才不抢正文。 */
.safety-box {
  margin-top: var(--qa-block-gap);
  background: v-bind(theme.safetyBgSoft);
  color: v-bind(theme.safetyText);
  border-left: 3px solid v-bind(theme.colorSuccess);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 13px;
  line-height: 1.6;
}

/* 急症拦截 / 低置信拒答：这两类必须抢注意力，保留满饱和底色 */
.safety-box.warn {
  background: v-bind(theme.warningBg);
  color: v-bind(theme.warningText);
  border-left-color: v-bind(theme.colorWarning);
}

.gf-item {
  padding: 2px 0;
  font-size: 13px;
  color: v-bind(theme.textColorBody);
}

.gf-src {
  margin-top: 4px;
  font-size: 13px;
  color: v-bind(theme.textColorMuted);
}

.trace-entry {
  margin-top: 10px;
}

/* 「图谱依据」「证据来源」共用的折叠块外观（默认折叠态由 el-collapse 负责） */
.fold {
  margin-top: 12px;
  border-top: 1px dashed v-bind(theme.borderColor);
}

/* 卡片底部操作行：反馈靠左、撤回图标靠右 */
.answer-actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.answer-actions .feedback {
  margin-top: 0;
  margin-right: auto;
}

.withdraw {
  color: v-bind(theme.textColorMuted);
  font-size: 15px;
  padding: 4px;
}

.withdraw:hover:not(.is-disabled) {
  color: v-bind(theme.colorPrimary);
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
