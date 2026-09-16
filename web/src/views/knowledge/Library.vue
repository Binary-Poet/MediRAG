<script setup lang="ts">
// 典籍知识库：统计卡 + 主题筛选 + 文档表格 + 上传（规格 P0-6）
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { DocItem } from '../../types/knowledge'
import { TOPICS } from '../../types/knowledge'
import { humanSize, listDocuments, parseStatus, getDocument, downloadUrl, renameDocument, deleteDocument } from '../../api/documents'
import type { DocDetail } from '../../api/documents'
import { theme } from '../../styles/theme'
import UploadDialog from './UploadDialog.vue'

const docs = ref<DocItem[]>([])
const total = ref(0)
const totalChunks = ref(0)
const filterTopic = ref('')
const showUpload = ref(false)
const detailVisible = ref(false)
const detailDoc = ref<DocDetail | null>(null)
let timer: number | undefined

const filtered = computed(() =>
  filterTopic.value ? docs.value.filter(d => d.topic === filterTopic.value) : docs.value)

const STATUS_TAG: Record<DocItem['status'], 'info' | 'warning' | 'success' | 'danger'> =
  { 上传中: 'info', 处理中: 'warning', 就绪: 'success', 失败: 'danger' }

async function refresh() {
  try {
    const res = await listDocuments()
    docs.value = res.items
    total.value = res.total
    totalChunks.value = res.total_chunks
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function pollPending() {
  const pending = docs.value.filter(d => d.status === '上传中' || d.status === '处理中')
  for (const d of pending) {
    try {
      const st = await parseStatus(d.id)
      const hit = docs.value.find(x => x.id === d.id)
      if (hit) { hit.status = st.status; hit.chunk_count = st.chunk_count }
      if (st.status === '失败') ElMessage.error(`${d.name} 入库失败：${st.error_message}`)
      // 就绪：不做本地累加（避免与 refresh 重复计数），改取后端权威统计
      if (st.status === '就绪') { refresh(); continue }
    } catch { /* 轮询失败静默，下轮重试 */ }
  }
}

async function removeDoc(d: DocItem) {
  try {
    await ElMessageBox.confirm(`确认删除《${d.name}》？其切片将从检索库移除。`, '删除确认', { type: 'warning' })
  } catch {
    return // 用户取消：静默返回，不再冒泡成 console.error
  }
  try {
    await deleteDocument(d.id)
    ElMessage.success('已删除')
    refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function showDetail(d: DocItem) {
  try {
    const res = await getDocument(d.id)
    detailDoc.value = res
    detailVisible.value = true
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

function download(d: DocItem) {
  // 临时 a 标签触发 attachment 下载（后端已设 Content-Disposition filename=原名）
  const a = document.createElement('a')
  a.href = downloadUrl(d.id)
  a.download = d.name
  document.body.appendChild(a)
  a.click()
  a.remove()
}

async function rename(d: DocItem) {
  let value: string
  try {
    const r = await ElMessageBox.prompt('请输入新名称', '重命名', {
      inputValue: d.name,
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    value = r.value.trim()
  } catch {
    return // 用户取消
  }
  // 校验：保留原文件后缀
  const extOf = (n: string) => (n.includes('.') ? n.slice(n.lastIndexOf('.') + 1).toLowerCase() : '')
  if (extOf(value) !== extOf(d.name)) {
    ElMessage.warning(`请保留文件后缀 .${extOf(d.name)}`)
    return
  }
  try {
    await renameDocument(d.id, value)
    ElMessage.success('已重命名')
    refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

onMounted(() => { refresh(); timer = window.setInterval(pollPending, 2000) })
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="library-page">
    <div class="stat-row">
      <el-card shadow="never" class="stat-card">
        <div class="stat-num">{{ total }}</div>
        <div class="stat-label">典籍文献数</div>
      </el-card>
      <el-card shadow="never" class="stat-card">
        <div class="stat-num">{{ totalChunks }}</div>
        <div class="stat-label">知识切片数</div>
      </el-card>
      <div class="stat-actions">
        <el-button type="primary" @click="showUpload = true">
          <el-icon><Upload /></el-icon>&nbsp;上传文献
        </el-button>
      </div>
    </div>

    <el-card shadow="never">
      <div class="filter-row">
        <span class="filter-label">知识主题</span>
        <el-select v-model="filterTopic" placeholder="全部主题" clearable style="width: 160px">
          <el-option v-for="t in TOPICS" :key="t" :label="t" :value="t" />
        </el-select>
      </div>

      <el-table :data="filtered" style="width: 100%">
        <el-table-column prop="name" label="名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ humanSize(row.size) }}</template>
        </el-table-column>
        <el-table-column prop="file_type" label="格式" width="80" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }: { row: DocItem }">
            <el-tag :type="STATUS_TAG[row.status]" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="topic" label="知识主题" width="110" />
        <el-table-column prop="chunk_count" label="切片数" width="90" />
        <el-table-column prop="uploaded_at" label="上传时间" width="150" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="showDetail(row)">详情</el-button>
            <el-button link type="primary" size="small" @click="download(row)">下载</el-button>
            <el-button link type="primary" size="small" @click="rename(row)">重命名</el-button>
            <el-button link type="danger" size="small" @click="removeDoc(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <UploadDialog v-model:visible="showUpload" @uploaded="refresh" />

    <el-dialog v-model="detailVisible" title="文档详情" width="520px">
      <el-descriptions v-if="detailDoc" :column="1" border size="small">
        <el-descriptions-item label="名称">{{ detailDoc.name }}</el-descriptions-item>
        <el-descriptions-item label="知识主题">{{ detailDoc.topic }}</el-descriptions-item>
        <el-descriptions-item label="格式">{{ detailDoc.file_type }}</el-descriptions-item>
        <el-descriptions-item label="大小">{{ humanSize(detailDoc.size) }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="STATUS_TAG[detailDoc.status]" size="small">{{ detailDoc.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="切片数">{{ detailDoc.chunk_count }}</el-descriptions-item>
        <el-descriptions-item label="上传时间">{{ detailDoc.uploaded_at }}</el-descriptions-item>
        <el-descriptions-item label="来源文件">{{ detailDoc.stored_file }}</el-descriptions-item>
        <el-descriptions-item v-if="detailDoc.error_message" label="错误信息">
          {{ detailDoc.error_message }}
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<style scoped>
.library-page { display: flex; flex-direction: column; gap: 16px; }
.stat-row { display: flex; gap: 16px; align-items: center; }
.stat-card { width: 180px; text-align: center; }
.stat-num { font-size: 26px; font-weight: 600; color: v-bind(theme.colorPrimary); }
.stat-label { font-size: 13px; color: v-bind(theme.textColorSecondary); }
.stat-actions { margin-left: auto; }
.filter-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.filter-label { font-size: 13px; color: v-bind(theme.textColorSecondary); }
</style>
