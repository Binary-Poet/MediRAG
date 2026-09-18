<script setup lang="ts">
// 检索溯源弹窗 —— 规格 P0-4。薄外壳：内容复用 TraceSteps（与 Chat 思考折叠块同源），
// 分区样式在 TraceSteps 一处维护。
import TraceSteps from './TraceSteps.vue'
import type { StepEvent } from '../../../types/chat'

defineProps<{
  visible: boolean
  steps: StepEvent[]
  /** 回答是否仍在流式中：决定流程条最后一步显示「进行中」还是「已完成」 */
  running?: boolean
}>()

const emit = defineEmits<{ (e: 'update:visible', v: boolean): void }>()
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="知识检索与图谱溯源"
    width="640px"
    @update:model-value="(v: boolean) => emit('update:visible', v)"
  >
    <TraceSteps :steps="steps" :running="running" />
  </el-dialog>
</template>
