/**
 * 全局设计 Token —— 摘自《前端还原规格.md》第一节（8 张截图提取的唯一真源）。
 * 图表（ECharts）与图谱节点配色统一从这里取，勿在组件内写死色值。
 */
export const theme = {
  // 品牌色
  colorPrimary: '#2d6a4f', // 主品牌绿：主按钮/选中/链接/图表主色
  colorSuccess: '#52b788',
  colorWarning: '#f59e0b',
  colorError: '#c62828', // 禁忌/警示红
  // 侧边栏 & 主区
  sidebarBg: '#1a3220',
  sidebarActiveBg: '#2d6a4f',
  pageBg: '#f5f7f5',
  cardBg: '#ffffff',
  borderRadius: '10px',
  textColorPrimary: '#1f2937',
  textColorSecondary: '#6b7280',
  borderColor: '#e5e7eb',
  hoverBg: '#f0fdf4',
  // 图谱节点语义色
  nodeFormula: '#2d6a4f', // 方剂
  nodeHerb: '#52b788', // 中药
  nodeSyndrome: '#bc6c25', // 证候
  nodeSymptom: '#dda15e', // 症状
  nodeEffect: '#74c69d', // 功效
  nodeContra: '#c62828', // 禁忌
  // 安全提示
  safetyBg: '#dcfce7',
  safetyText: '#166534',
} as const

export type Theme = typeof theme
