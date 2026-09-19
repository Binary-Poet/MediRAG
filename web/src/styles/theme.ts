/**
 * 全局设计 Token —— 摘自《前端还原规格.md》第一节（8 张截图提取的唯一真源）。
 * 图表（ECharts）与图谱节点配色统一从这里取，勿在组件内写死色值。
 *
 * 灰阶分四级（文字层级从强到弱，勿跨级反用）：
 *   primary #1f2937 → body #374151 → secondary #4b5563 → muted #6b7280
 *   faint #9ca3af 仅用于装饰、禁用态与占位符，不承担任何需要阅读的正文/标签
 * —— muted 对白底 4.7:1，是「小字仍可读」的下限（WCAG AA）。
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
  sidebarText: '#ffffff',
  sidebarTextMuted: 'rgba(255, 255, 255, 0.62)',
  sidebarDivider: 'rgba(255, 255, 255, 0.08)',
  pageBg: '#f5f7f5',
  cardBg: '#ffffff',
  borderRadius: '10px',
  shadowCard: '0 6px 20px rgba(26, 50, 32, 0.10)',
  textColorPrimary: '#1f2937',
  textColorSecondary: '#4b5563',
  textColorBody: '#374151',
  textColorMuted: '#6b7280',
  textColorFaint: '#9ca3af',
  borderColor: '#e5e7eb',
  hoverBg: '#f0fdf4',
  autoSectionBg: '#fafbfa', // 溯源弹窗区块底
  selectedBg: '#e6f1ea', // 常驻选中底（列表选中项）：比 hoverBg 深一档，hover 时仍有加深的余地
  // 玻璃面板（登录页）上的表单边框：#e5e7eb 压在浅绿玻璃上对比不足，需加重才看得见输入区
  fieldBorderGlass: 'rgba(45, 106, 79, 0.38)',
  // 登录页玻璃上的卡片描边：白色描边压在近白玻璃上等于不可见，改用低透明主绿
  glassCardBorder: 'rgba(45, 106, 79, 0.20)',
  // 登录页页面底的渐变两端（光斑由 CSS 径向渐变叠加，见 Login.vue）
  loginGradientFrom: '#e8f4ec',
  loginGradientTo: '#dcebe2',
  // 图谱连边（原先用 safetyBg 导致线几乎不可见）
  graphEdge: 'rgba(45, 106, 79, 0.42)',
  graphEdgeActive: '#2d6a4f',
  // 候选节点/边虚线：告警橙弱透明。textColorFaint(#9ca3af) 在白底上仅 2.5:1，
  // 「待审核」是需要被注意的语义，弱到看不见就失去了区分作用。
  graphCandidate: 'rgba(245, 158, 11, 0.6)',
  // 图谱节点语义色
  nodeFormula: '#2d6a4f', // 方剂
  nodeHerb: '#52b788', // 中药
  nodeSyndrome: '#bc6c25', // 证候
  nodeSymptom: '#dda15e', // 症状
  nodeEffect: '#74c69d', // 功效
  nodeContra: '#c62828', // 禁忌
  // 安全提示
  safetyBg: '#dcfce7',
  safetyBgSoft: '#f2fbf5', // 常规提示用弱底：满饱和绿底会盖过回答正文
  safetyText: '#166534',
  // 空态/警告徽章
  warningBg: '#fef3c7',
  warningText: '#92400e',
  // 字体族（拉丁字形自托管，见 styles/fonts.css；中文回落系统字体）
  fontDisplay: "'Source Serif 4', 'Noto Serif SC', 'Songti SC', 'SimSun', Georgia, serif",
  fontSans: "'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif",
} as const

export type Theme = typeof theme
