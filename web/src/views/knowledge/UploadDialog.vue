<script setup lang="ts">
// 上传弹窗：批量上传（多文件），现代上传 UI，知识主题由后端默认归类
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { theme } from '../../styles/theme'
import { authHeaders } from '../../api/http'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'uploaded'): void }>()

const FORMATS = 'PDF / DOC / DOCX / RTF / PPT / PPTX、XLS / XLSX / CSV / TSV、TXT / MD / HTML / JSON / XML / YAML / LOG'
const MAX_MB = 100
const DEFAULT_TOPIC = '内科'

interface FileItem {
  id: number
  file: File
  status: 'idle' | 'uploading' | 'success' | 'failed'
  errorMsg: string
  simTimer: number | null
}

let seq = 0
const files = ref<FileItem[]>([])
// 进度独立存放，扁平响应式对象，保证 setInterval 内赋值能稳定触发 UI 更新
const progressMap = reactive<Record<number, number>>({})
const dragging = ref(false)
const uploading = ref(false)

const pendingCount = computed(() => files.value.filter(f => f.status === 'idle').length)
const successCount = computed(() => files.value.filter(f => f.status === 'success').length)
const canSubmit = computed(() => pendingCount.value > 0 && !uploading.value)

watch(() => props.visible, (v) => { if (v) reset() })

function reset() {
  files.value.forEach(f => f.simTimer && clearInterval(f.simTimer))
  files.value = []
  Object.keys(progressMap).forEach(k => { delete progressMap[Number(k)] })
  uploading.value = false
}

function makeItem(file: File): FileItem {
  const id = ++seq
  progressMap[id] = 0
  return { id, file, status: 'idle', errorMsg: '', simTimer: null }
}

function pick(list: FileList | null) {
  if (!list || !list.length) return
  for (let i = 0; i < list.length; i += 1) {
    const f = list[i]
    if (f.size > MAX_MB * 1024 * 1024) { ElMessage.error(`${f.name} 超过 ${MAX_MB}MB`); continue }
    files.value.push(makeItem(f))
  }
}

function onDrop(e: DragEvent) {
  dragging.value = false
  pick(e.dataTransfer?.files ?? null)
}

function removeFile(id: number) {
  if (uploading.value) return
  const idx = files.value.findIndex(f => f.id === id)
  if (idx >= 0) {
    files.value[idx].simTimer && clearInterval(files.value[idx].simTimer)
    files.value.splice(idx, 1)
    delete progressMap[id]
  }
}

/** 单个文件的模拟进度计时器：兜底 onprogress 不触发（localhost 小文件） */
function startSim(item: FileItem) {
  item.simTimer = window.setInterval(() => {
    const cur = progressMap[item.id]
    if (cur < 92) progressMap[item.id] = Math.min(92, cur + Math.random() * 9)
  }, 120)
}
function stopSim(item: FileItem) {
  if (item.simTimer !== null) { clearInterval(item.simTimer); item.simTimer = null }
}

/** 单文件 XHR 上传，真实进度优先，模拟进度兜底 */
function uploadOne(item: FileItem): Promise<boolean> {
  return new Promise((resolve) => {
    const form = new FormData()
    form.append('file', item.file)
    form.append('topic', DEFAULT_TOPIC)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/documents')
    Object.entries(authHeaders()).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const real = Math.round((e.loaded / e.total) * 100)
        if (real > progressMap[item.id]) progressMap[item.id] = real
      }
    }
    xhr.onload = () => {
      stopSim(item)
      if (xhr.status >= 200 && xhr.status < 300) {
        progressMap[item.id] = 100
        item.status = 'success'
        resolve(true)
      } else {
        let detail = `HTTP ${xhr.status}`
        try { detail = JSON.parse(xhr.responseText).detail ?? detail } catch { /* noop */ }
        item.status = 'failed'
        item.errorMsg = detail
        resolve(false)
      }
    }
    xhr.onerror = () => {
      stopSim(item)
      item.status = 'failed'
      item.errorMsg = '网络错误，请重试'
      resolve(false)
    }
    item.status = 'uploading'
    progressMap[item.id] = 0
    startSim(item)
    xhr.send(form)
  })
}

async function submit() {
  const pendings = files.value.filter(f => f.status === 'idle')
  if (!pendings.length) { ElMessage.warning('没有待上传的文件'); return }
  uploading.value = true
  let okCount = 0
  for (const item of pendings) {
    const ok = await uploadOne(item)
    if (ok) okCount += 1
  }
  uploading.value = false
  if (okCount > 0) {
    await nextTick()
    emit('uploaded')
  }
  if (okCount < pendings.length) {
    ElMessage.error(`${pendings.length - okCount} 个文件上传失败`)
  } else {
    ElMessage.success(`已成功上传 ${okCount} 个文件`)
  }
}

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
</script>

<template>
  <el-dialog :model-value="visible" width="560px" :show-close="true"
             @update:model-value="emit('update:visible', $event)">
    <template #header>
      <div class="dialog-head">
        <span class="dialog-title">上传典籍文献</span>
        <span class="dialog-sub">支持批量上传，选择或拖拽多个文件</span>
      </div>
    </template>

    <!-- 居中虚线框：文件夹图标 + 选择/拖拽文案 + 格式提示 -->
    <div class="drop-zone" :class="{ dragging, active: files.length > 0 }"
         @dragover.prevent="dragging = true"
         @dragleave.prevent="dragging = false"
         @drop.prevent="onDrop"
         @click="($refs.fileInput as HTMLInputElement).click()">
      <div class="drop-icon">
        <el-icon :size="40" :color="theme.colorPrimary"><FolderOpened /></el-icon>
      </div>
      <p class="drop-text">
        <em>选择文件</em> 或将文件拖到此处
      </p>
      <p class="drop-hint">支持格式：{{ FORMATS }}</p>
      <p class="drop-hint">单文件 ≤ {{ MAX_MB }} MB，可多选</p>
    </div>
    <input ref="fileInput" type="file" multiple class="hidden-input"
           @change="pick(($event.target as HTMLInputElement).files)" />

    <!-- 文件列表：每个文件独立卡片，含进度条 + 状态 + 删除 -->
    <div v-if="files.length" class="file-list">
      <div v-for="item in files" :key="item.id" class="file-card" :class="item.status">
        <div class="file-info">
          <span class="file-name">{{ item.file.name }}</span>
          <span class="file-size">{{ humanSize(item.file.size) }}</span>
        </div>
        <div class="file-meta">
          <div class="progress-track">
            <div class="progress-bar" :style="{ width: (progressMap[item.id] || 0) + '%' }" />
          </div>
          <span class="file-status">
            <template v-if="item.status === 'idle'">待上传</template>
            <template v-else-if="item.status === 'uploading'">{{ Math.round(progressMap[item.id] || 0) }}%</template>
            <template v-else-if="item.status === 'success'"><el-icon :size="14"><CircleCheck /></el-icon> 100%</template>
            <template v-else-if="item.status === 'failed'"><el-icon :size="14" color="#c62828"><CircleClose /></el-icon> 失败</template>
          </span>
          <button v-if="item.status !== 'uploading'" class="file-del" type="button"
                  aria-label="移除文件" @click.stop="removeFile(item.id)">
            <el-icon :size="16"><Delete /></el-icon>
          </button>
        </div>
        <p v-if="item.status === 'failed'" class="file-error">{{ item.errorMsg }}</p>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="reset()">取消</el-button>
        <el-button type="primary" :disabled="!canSubmit" :loading="uploading" @click="submit">
          {{ uploading ? `上传中…` : `开始上传${pendingCount ? `（${pendingCount}）` : ''}` }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.dialog-head { display: flex; flex-direction: column; gap: 2px; }
.dialog-title { font-size: 18px; font-weight: 700; color: v-bind(theme.textColorPrimary); }
.dialog-sub { font-size: 13px; color: v-bind(theme.textColorMuted); }

/* 居中虚线上传框：墨绿色虚线 */
.drop-zone {
  border: 2px dashed v-bind(theme.colorPrimary);
  border-radius: 14px;
  padding: 36px 20px;
  text-align: center;
  cursor: pointer;
  background: v-bind(theme.cardBg);
  transition: border-color 0.2s, background 0.2s;
}
.drop-zone:hover { background: v-bind(theme.hoverBg); }
.drop-zone.dragging { border-color: v-bind(theme.colorSuccess); background: v-bind(theme.hoverBg); }
.drop-zone.active { border-color: v-bind(theme.colorSuccess); background: v-bind(theme.safetyBgSoft); }
.drop-icon { margin-bottom: 12px; }
.drop-text {
  margin: 4px 0; font-size: 14px; color: v-bind(theme.textColorSecondary);
  display: inline-flex; align-items: center; gap: 6px;
}
.drop-text em { color: v-bind(theme.colorPrimary); font-style: normal; font-weight: 600; text-decoration: underline; text-underline-offset: 3px; }
.drop-hint { margin: 2px 0; font-size: 12px; color: v-bind(theme.textColorMuted); }

.hidden-input { display: none; }

/* 文件列表 */
.file-list { margin-top: 16px; display: flex; flex-direction: column; gap: 10px; max-height: 280px; overflow-y: auto; }

/* 文件卡片：文件名 + 大小 + 进度条 + 状态 + 删除 */
.file-card {
  padding: 12px 14px;
  background: v-bind(theme.autoSectionBg);
  border: 1px solid v-bind(theme.borderColor);
  border-radius: 10px;
}
.file-card.success { border-color: v-bind(theme.colorSuccess); background: v-bind(theme.safetyBgSoft); }
.file-card.failed { border-color: v-bind(theme.colorError); background: #fff5f5; }
.file-info { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
.file-name { font-size: 14px; font-weight: 600; color: v-bind(theme.textColorPrimary); }
.file-size { font-size: 12px; color: v-bind(theme.textColorMuted); }
.file-meta { display: flex; align-items: center; gap: 10px; }
.progress-track {
  flex: 1; height: 6px; border-radius: 3px;
  background: rgba(0, 0, 0, 0.08); overflow: hidden;
}
.progress-bar {
  height: 100%; width: 0; border-radius: 3px;
  background: #2d6a4f; transition: width 0.2s ease;
}
.file-card.success .progress-bar { background: #52b788; width: 100%; }
.file-card.failed .progress-bar { background: #c62828; }
.file-status { font-size: 12px; color: v-bind(theme.textColorSecondary); min-width: 60px; text-align: right; display: inline-flex; align-items: center; gap: 3px; justify-content: flex-end; }
.file-card.success .file-status { color: v-bind(theme.safetyText); font-weight: 600; }
.file-card.failed .file-status { color: v-bind(theme.colorError); }
.file-del {
  flex: none; border: none; background: transparent; cursor: pointer;
  color: v-bind(theme.textColorMuted); padding: 2px; border-radius: 4px;
  display: inline-flex; align-items: center;
}
.file-del:hover { color: v-bind(theme.colorError); background: rgba(198, 40, 40, 0.08); }
.file-error { margin: 8px 0 0; font-size: 12px; color: v-bind(theme.colorError); }

.dialog-footer { display: flex; justify-content: flex-end; gap: 10px; }
</style>
