<script setup lang="ts">
// 占位页：阶段 0 只验收"空页面 + 侧边栏"，各页面按阶段逐个替换为真实实现
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="placeholder">
    <el-card>
      <div class="inner">
        <el-icon :size="36" color="#2d6a4f"><DataBoard /></el-icon>
        <h2>{{ route.meta.title }}</h2>
        <p>页面骨架已就绪，按合并方案 <el-tag size="small">{{ route.meta.phase }}</el-tag> 实现真实功能</p>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.placeholder {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

.inner {
  padding: 48px 64px;
  text-align: center;
}

.inner h2 {
  margin: 12px 0 8px;
}

.inner p {
  color: #6b7280;
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
</style>
