<script setup lang="ts">
// 阶段 1 最简对话页：发送 → 回答 + 引用列表
// 阶段 3 替换为完整辨证问答页（会话列表/溯源弹窗/SSE），结构届时按《前端还原规格》重做
import { nextTick, ref } from 'vue'
import { askQuestion } from '../../api/chat'
import type { Reference } from '../../types/chat'

interface QA {
  question: string
  answer: string
  references: Reference[]
}

const messages = ref<QA[]>([])
const input = ref('')
const loading = ref(false)
const listRef = ref<HTMLElement>()

const suggestions = ['四君子汤由哪些中药组成？', '风寒束表与风热犯表有什么区别？', '人参的功效有哪些？']

async function send(q?: string) {
  const question = (q ?? input.value).trim()
  if (!question || loading.value) return
  input.value = ''
  loading.value = true
  messages.value.push({ question, answer: '', references: [] })
  await nextTick()
  listRef.value?.scrollTo({ top: listRef.value.scrollHeight })

  try {
    const resp = await askQuestion(question)
    messages.value[messages.value.length - 1] = {
      question,
      answer: resp.answer,
      references: resp.references,
    }
  } catch (e) {
    messages.value[messages.value.length - 1].answer = `请求失败：${(e as Error).message}`
  } finally {
    loading.value = false
    await nextTick()
    listRef.value?.scrollTo({ top: listRef.value.scrollHeight })
  }
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
          <el-collapse v-if="m.references.length" class="refs">
            <el-collapse-item :title="`证据来源 (${m.references.length})`">
              <div v-for="(r, j) in m.references" :key="r.chunk_id" class="ref-item">
                [{{ j + 1 }}] {{ r.title }} —— {{ r.doc_name }} · {{ r.chapter }} · 序号 {{ r.page_no }}
                <span class="score">相似度 {{ r.score.toFixed(3) }}</span>
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

.refs {
  margin-top: 12px;
  border-top: 1px dashed #e5e7eb;
}

.ref-item {
  font-size: 13px;
  color: #374151;
  padding: 2px 0;
}

.score {
  color: #9ca3af;
  font-size: 12px;
  margin-left: 8px;
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
