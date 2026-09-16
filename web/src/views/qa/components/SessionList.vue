<script setup lang="ts">
// 左侧「问答会话」列表（规格 P0-2）：区块标题+统计 / + 新对话 / 全部·已收藏筛选 / 会话项。
// 数据取自 session store；选中、新建、删除后的复位交由父组件处理（父组件负责加载消息）。
import { computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useSessionStore } from '../../../stores/session'
import { relativeTime } from '../../../utils/time'
import { theme } from '../../../styles/theme'
import type { SessionSummary } from '../../../types/chat'

const emit = defineEmits<{ create: []; select: [id: string]; deleted: [id: string] }>()
const store = useSessionStore()

const tabs = computed(() => [
  { key: false, label: `全部 ${store.total}` },
  { key: true, label: `已收藏 ${store.favoriteTotal}` },
])

async function switchTab(favoriteOnly: boolean) {
  store.favoriteOnly = favoriteOnly
  try {
    await store.refresh()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function toggleFavorite(s: SessionSummary) {
  try {
    await store.toggleFavorite(s)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/** 删除：二次确认（不可恢复） */
async function remove(s: SessionSummary) {
  try {
    await ElMessageBox.confirm(`确定删除会话「${s.title}」？该操作不可恢复。`, '删除确认',
                               { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
  } catch {
    return // 用户取消
  }
  try {
    await store.remove(s.session_id)
    emit('deleted', s.session_id)
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

function onCommand(cmd: string, s: SessionSummary) {
  if (cmd === 'fav') return toggleFavorite(s)
  if (cmd === 'del') return remove(s)
  return undefined
}

onMounted(() => {
  store.refresh().catch(() => {})   // 列表拉取失败不阻断问答主链路
})
</script>

<template>
  <aside class="session-list">
    <div class="sl-head">
      <div class="sl-head-text">
        <div class="sl-title">问答会话</div>
        <div class="sl-stat">{{ store.total }} 个历史会话 · {{ store.favoriteTotal }} 个收藏</div>
      </div>
      <el-button type="primary" size="small" @click="emit('create')">+ 新对话</el-button>
    </div>

    <div class="sl-tabs">
      <button
        v-for="t in tabs"
        :key="String(t.key)"
        class="sl-tab"
        :class="{ on: store.favoriteOnly === t.key }"
        type="button"
        @click="switchTab(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <div class="sl-items">
      <div
        v-for="s in store.sessions"
        :key="s.session_id"
        class="sl-item"
        :class="{ on: store.activeId === s.session_id }"
        @click="emit('select', s.session_id)"
      >
        <span class="sl-item-icon" aria-hidden="true" />
        <div class="sl-item-main">
          <div class="sl-item-title">{{ s.title }}</div>
          <div class="sl-item-meta">{{ relativeTime(s.updated_at) }} · {{ s.message_count }}条</div>
        </div>
        <button
          class="sl-star"
          :class="{ on: s.favorite }"
          type="button"
          :title="s.favorite ? '取消收藏' : '收藏'"
          @click.stop="toggleFavorite(s)"
        >
          {{ s.favorite ? '★' : '☆' }}
        </button>
        <el-dropdown trigger="click" @command="(c: string) => onCommand(c, s)">
          <button class="sl-more" type="button" title="更多操作" @click.stop>⋯</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="fav">{{ s.favorite ? '取消收藏' : '收藏' }}</el-dropdown-item>
              <el-dropdown-item command="del" divided>删除</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>

      <div v-if="!store.sessions.length" class="sl-empty">
        {{ store.favoriteOnly ? '暂无收藏的会话' : '暂无历史会话' }}
      </div>
    </div>
  </aside>
</template>

<style scoped>
.session-list {
  width: 280px;
  flex: none;
  display: flex;
  flex-direction: column;
  background: v-bind(theme.cardBg);
  border: 1px solid v-bind(theme.borderColor);
  border-radius: v-bind(theme.borderRadius);
  overflow: hidden;
}

.sl-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 14px 10px;
}

.sl-head-text {
  flex: 1;
  min-width: 0;
}

.sl-title {
  font-size: 15px;
  font-weight: 600;
  color: v-bind(theme.textColorPrimary);
}

.sl-stat {
  font-size: 12px;
  color: v-bind(theme.textColorMuted);
  margin-top: 2px;
}

.sl-tabs {
  display: flex;
  gap: 6px;
  padding: 10px;
  margin: 0 0 10px;
  border-radius: 0;
  background: v-bind(theme.pageBg);
}

.sl-tab {
  flex: 1;
  font-size: 13px;
  font-family: inherit;
  padding: 6px 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: v-bind(theme.textColorSecondary);
  cursor: pointer;
}

.sl-tab.on {
  background: v-bind(theme.cardBg);
  color: v-bind(theme.colorPrimary);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}

.sl-items {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 12px;
}

.sl-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  cursor: pointer;
  margin-bottom: 6px;
}

.sl-item:hover {
  background: v-bind(theme.hoverBg);
}

.sl-item.on {
  border-color: v-bind(theme.colorPrimary);
  background: v-bind(theme.hoverBg);
}

/* 前置对话气泡图标（规格 P0-2 会话项）：圆环 + 圆内三点 + 左下小尾巴，纯 CSS，无图标库依赖。
   直径按参考截图比例定：截图里图标宽 / 标题中文字高 ≈ 1.2，本组件标题 13px（墨迹约 12px），
   故取 16px；描边仍 1.5px（截图线条很细，缩到 1px 会发虚）。 */
.sl-item-icon {
  flex: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 1.5px solid v-bind(theme.borderColor);
  position: relative;
}

.sl-item-icon::before {
  /* 气泡内的三枚省略点：一枚实心点 + 两枚 box-shadow 副本，避免三个 DOM 节点。
     2px 点 / 3px 间距：再小（1px 点）在 1x 下会糊成一团，故以此为止。 */
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 2px;
  height: 2px;
  margin: -1px 0 0 -4px;
  border-radius: 50%;
  background: v-bind(theme.borderColor);
  box-shadow: 3px 0 0 v-bind(theme.borderColor), 6px 0 0 v-bind(theme.borderColor);
}

.sl-item-icon::after {
  /* 气泡尾巴：只画两条边、透明填充，任何背景色（含 hover/选中态）下都不会露色块 */
  content: '';
  position: absolute;
  left: 1px;
  bottom: -1.5px;
  width: 4px;
  height: 4px;
  border-left: 1.5px solid v-bind(theme.borderColor);
  border-bottom: 1.5px solid v-bind(theme.borderColor);
  transform: rotate(-45deg);
}

.sl-item-main {
  flex: 1;
  min-width: 0;
}

.sl-item-title {
  font-size: 13px;
  color: v-bind(theme.textColorBody);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sl-item-meta {
  font-size: 12px;
  color: v-bind(theme.textColorMuted);
  margin-top: 3px;
}

.sl-star,
.sl-more {
  flex: none;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  line-height: 1;
  padding: 4px;
  color: v-bind(theme.textColorMuted);
}

.sl-star.on {
  color: v-bind(theme.colorWarning);
}

.sl-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 13px;
  color: v-bind(theme.textColorMuted);
}
</style>
