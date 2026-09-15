<script setup lang="ts">
// 候选审核 Tab：LLM 抽取 → 人工确认 → 发布（方案 6.5 闭环）
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { CandidateEdge, CandidateNode } from '../../types/graph'
import { approveCandidate, listCandidates, rejectCandidate } from '../../api/graph'
import { theme } from '../../styles/theme'

const nodes = ref<CandidateNode[]>([])
const edges = ref<CandidateEdge[]>([])
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    const res = await listCandidates()
    nodes.value = res.nodes
    edges.value = res.edges
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

async function approveEdge(e: CandidateEdge) {
  try {
    await approveCandidate({ kind: 'edge', source: e.source, relation: e.relation, target: e.target })
    ElMessage.success(`已发布：${e.source} --${e.relation}--> ${e.target}`)
    refresh()
  } catch (err) {
    ElMessage.error((err as Error).message)   // 409 被已发布边引用 / 422 缺字段
  }
}

async function rejectEdge(e: CandidateEdge) {
  try {
    await rejectCandidate({ kind: 'edge', source: e.source, relation: e.relation, target: e.target })
    ElMessage.success('已驳回该关系')
    refresh()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function approveNode(n: CandidateNode) {
  try {
    await approveCandidate({ kind: 'node', name: n.name })
    ElMessage.success(`已发布实体：${n.name}`)
    refresh()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function rejectNode(n: CandidateNode) {
  try {
    await rejectCandidate({ kind: 'node', name: n.name })
    ElMessage.success('已驳回该实体')
    refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)     // 409 时显示后端 detail 原文
  }
}

onMounted(refresh)
</script>

<template>
  <div v-loading="loading" class="review-panel">
    <div class="review-head">
      <span>待审核关系 {{ edges.length }} 条 · 待审核实体 {{ nodes.length }} 个</span>
      <el-button size="small" @click="refresh">刷新</el-button>
    </div>

    <el-table :data="edges" size="small" class="review-table">
      <el-table-column label="关系" min-width="320">
        <template #default="{ row }">{{ row.source }} --{{ row.relation }}--> {{ row.target }}</template>
      </el-table-column>
      <el-table-column prop="source_doc" label="来源" width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="approveEdge(row)">发布</el-button>
          <el-button link type="danger" size="small" @click="rejectEdge(row)">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-table :data="nodes" size="small" class="review-table">
      <el-table-column prop="name" label="实体" min-width="160" />
      <el-table-column prop="type" label="类型" width="90" />
      <el-table-column prop="source_doc" label="来源" width="160" show-overflow-tooltip />
      <el-table-column label="操作" width="140">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="approveNode(row)">发布</el-button>
          <el-button link type="danger" size="small" @click="rejectNode(row)">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && !edges.length && !nodes.length" description="暂无待审核候选知识" />
    <p class="review-note">候选知识经人工审核后发布，回答结论保留原文证据</p>
  </div>
</template>

<style scoped>
.review-panel { display: flex; flex-direction: column; gap: 12px; }
.review-head { display: flex; justify-content: space-between; align-items: center; font-size: 13px; color: v-bind(theme.textColorSecondary); }
.review-note { font-size: 12px; color: v-bind(theme.textColorMuted); text-align: right; }
</style>