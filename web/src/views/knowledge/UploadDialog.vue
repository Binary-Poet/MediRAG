<script setup lang="ts">
// 上传弹窗：拖拽区 + 支持格式清单 + 知识主题必选（规格 P0-6 逐字）
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { TOPICS } from '../../types/knowledge'
import { uploadDocument } from '../../api/documents'
import { theme } from '../../styles/theme'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'uploaded'): void }>()

const FORMATS = 'PDF/DOC/DOCX/RTF/PPT/PPTX、XLS/XLSX/CSV/TSV、TXT/MD/HTML/JSON/XML/YAML/LOG'
const MAX_MB = 100

const file = ref<File | null>(null)
const topic = ref('')
const dragging = ref(false)
const uploading = ref(false)
const topicError = ref(false)

const canSubmit = computed(() => !!file.value && !!topic.value && !uploading.value)

watch(() => props.visible, (v) => {
  if (v) { file.value = null; topic.value = ''; topicError.value = false }
})

function pick(f: File | undefined) {
  if (!f) return
  if (f.size > MAX_MB * 1024 * 1024) { ElMessage.error(`单文件不超过 ${MAX_MB}MB`); return }
  file.value = f
}

function onDrop(e: DragEvent) {
  dragging.value = false
  pick(e.dataTransfer?.files?.[0])
}

async function submit() {
  if (!file.value) { ElMessage.warning('请选择文件'); return }
  if (!topic.value) { topicError.value = true; ElMessage.warning('请选择知识主题'); return }
  uploading.value = true
  try {
    await uploadDocument(file.value, topic.value)
    ElMessage.success('已提交入库，处理中…')
    emit('uploaded')
    emit('update:visible', false)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="visible" title="上传典籍文献" width="560px"
             @update:model-value="emit('update:visible', $event)">
    <div class="drop-zone" :class="{ dragging }"
         @dragover.prevent="dragging = true"
         @dragleave.prevent="dragging = false"
         @drop.prevent="onDrop"
         @click="($refs.fileInput as HTMLInputElement).click()">
      <el-icon :size="28" :color="theme.colorPrimary"><UploadFilled /></el-icon>
      <p>将文件拖到此处，或 <em>点击选择</em></p>
      <p class="hint">支持格式：{{ FORMATS }}；单文件 ≤ {{ MAX_MB }}MB</p>
      <p v-if="file" class="picked">{{ file.name }}（{{ (file.size / 1024).toFixed(1) }} KB）</p>
    </div>
    <input ref="fileInput" type="file" class="hidden-input" @change="pick(($event.target as HTMLInputElement).files?.[0])" />

    <div class="topic-block">
      <div class="topic-label">知识主题 <span class="required">*</span></div>
      <el-radio-group v-model="topic" class="topic-group">
        <el-radio-button v-for="t in TOPICS" :key="t" :value="t">{{ t }}</el-radio-button>
      </el-radio-group>
      <p v-if="topicError" class="topic-error">知识主题为必选项</p>
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)">取消</el-button>
      <el-button type="primary" :disabled="!canSubmit" :loading="uploading" @click="submit">开始上传</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.drop-zone {
  border: 1.5px dashed v-bind(theme.colorSuccess); border-radius: v-bind(theme.borderRadius); padding: 28px 16px;
  text-align: center; cursor: pointer; background: v-bind(theme.autoSectionBg);
}
.drop-zone.dragging { border-color: v-bind(theme.colorPrimary); background: v-bind(theme.hoverBg); }
.drop-zone p { margin: 6px 0; font-size: 13px; color: v-bind(theme.textColorSecondary); }
.drop-zone em { color: v-bind(theme.colorPrimary); font-style: normal; }
.drop-zone .hint { font-size: 12px; color: v-bind(theme.textColorMuted); }
.picked { color: v-bind(theme.textColorPrimary) !important; font-weight: 600; }
.hidden-input { display: none; }
.topic-block { margin-top: 18px; }
.topic-label { font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.required { color: v-bind(theme.colorError); }
.topic-error { color: v-bind(theme.colorError); font-size: 12px; margin-top: 6px; }
</style>