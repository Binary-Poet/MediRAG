<script setup lang="ts">
// 推理配置（规格 P1）：保存即写后端，下一次问答请求生效
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getConfig, saveConfig, type InferenceConfig } from '../../api/config'
import { theme } from '../../styles/theme'

const DEFAULTS: InferenceConfig = {
  semantic_k: 20, keyword_k: 20, fuse_candidate: 25, final_evidence: 5,
  rrf_k: 60, model: 'deepseek-chat', answer_temp: 0.3, query_temp: 0.1,
}
const original = reactive<InferenceConfig>({ ...DEFAULTS })
const form = reactive<InferenceConfig>({ ...DEFAULTS })
const saving = ref(false)

const mixFields = [
  { key: 'semantic_k', label: '语义召回数', min: 1, max: 100 },
  { key: 'keyword_k', label: '关键词召回数', min: 1, max: 100 },
  { key: 'fuse_candidate', label: '融合候选数', min: 1, max: 100 },
  { key: 'final_evidence', label: '最终证据数', min: 1, max: 100 },
  { key: 'rrf_k', label: '融合平衡系数', min: 1, max: 200 },
] as const

onMounted(async () => {
  try {
    const c = await getConfig()
    Object.assign(original, c); Object.assign(form, c)
  } catch (e) { ElMessage.error((e as Error).message) }
})

function resetOne(key: keyof InferenceConfig) {
  // 单项重置（规格：均带默认值与「重置」）
  ;(form as Record<string, unknown>)[key] = DEFAULTS[key as never]
}

async function save() {
  // el-input-number 清空失焦会写回 null，若直接提交会被后端 422 拒绝；
  // 在前端先拦截，避免发出无效请求。
  if ((Object.values(form) as unknown[]).some((v) => v === null || v === undefined || v === '')) {
    ElMessage.error('请填写完整配置')
    return
  }
  saving.value = true
  try {
    const saved = await saveConfig({ ...form })
    Object.assign(original, saved)
    ElMessage.success('已保存，下一次问答请求生效')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally { saving.value = false }
}

function restoreAll() {
  Object.assign(form, DEFAULTS)
}
</script>

<template>
  <div class="inference-page">
    <div class="page-head"><h2>推理配置</h2></div>

    <el-card class="card" shadow="never">
      <div class="card-title">混合检索组</div>
      <div class="rows">
        <div v-for="f in mixFields" :key="f.key" class="row">
          <span class="row-label">{{ f.label }}</span>
          <el-input-number
            v-model="form[f.key]"
            class="stepper"
            :min="f.min"
            :max="f.max"
            :step="1"
            controls-position="right"
          />
          <el-button
            link
            type="primary"
            size="small"
            :disabled="form[f.key] === DEFAULTS[f.key]"
            :title="`重置为默认 ${DEFAULTS[f.key]}`"
            @click="resetOne(f.key)"
          >重置</el-button>
        </div>
      </div>
    </el-card>

    <el-card class="card" shadow="never">
      <div class="card-title">生成模型组</div>
      <div class="rows">
        <div class="row">
          <span class="row-label">对话模型</span>
          <el-select v-model="form.model" class="model-select">
            <el-option label="deepseek-chat" value="deepseek-chat" />
            <el-option label="qwen-plus" value="qwen-plus" />
          </el-select>
        </div>
        <div class="row">
          <span class="row-label">回答灵活度</span>
          <el-slider
            v-model="form.answer_temp"
            class="slider"
            :min="0"
            :max="2"
            :step="0.05"
            show-input
          />
        </div>
        <div class="row">
          <span class="row-label">问句理解灵活度</span>
          <el-slider
            v-model="form.query_temp"
            class="slider"
            :min="0"
            :max="2"
            :step="0.05"
            show-input
          />
        </div>
      </div>
    </el-card>

    <div class="actions">
      <el-button type="primary" :loading="saving" @click="save">保存本组</el-button>
      <el-button link type="primary" @click="restoreAll">恢复全部默认</el-button>
    </div>
    <p class="hint">变更保存后将立即应用于新的问答请求</p>
  </div>
</template>

<style scoped>
.inference-page { background: v-bind(theme.pageBg); display: flex; flex-direction: column; gap: 14px; }
.page-head h2 { margin: 0; font-size: 18px; font-weight: 600; color: v-bind(theme.textColorPrimary); }
.card { background: v-bind(theme.cardBg); border-radius: v-bind(theme.borderRadius); }
.card-title { font-size: 14px; font-weight: 600; color: v-bind(theme.textColorPrimary); margin-bottom: 12px; }
.rows { display: flex; flex-direction: column; gap: 14px; }
.row { display: flex; align-items: center; gap: 12px; }
.row-label { flex: none; width: 120px; font-size: 13px; color: v-bind(theme.textColorSecondary); }
.stepper { width: 160px; }
.model-select { width: 200px; }
.slider { width: 380px; }
.actions { display: flex; align-items: center; gap: 12px; }
.hint { margin: 0; font-size: 12px; color: v-bind(theme.textColorMuted); }
</style>
