<script setup lang="ts">
// 登录页 —— 版式参照 docs/原项目前端展示图（部分）的登录截图：
// 页面居中悬浮卡片，左侧品牌区（渐变主色 + 标语 + 短横线要点 + 装饰引号 + 版权），右侧白色表单区
// （小字距标签 + 大标题 + 短下划线 + 仅下边框输入框 + 行内错误 + 全宽按钮 + 虚线分隔的演示账号）。
// 文案沿用本项目自身表述，不照抄参考图原文。提交动作接 POST /api/auth/login。
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { theme } from '../styles/theme'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '', remember: true })
const usernameError = ref('')
const passwordError = ref('')

// 左栏要点：每条以短横线起头，短句陈述系统能力
const highlights = [
  '三路混合检索：向量 + BM25 + 图谱，RRF 融合召回',
  'Cross-Encoder 精排，按证据相关度重排序',
  '实体关系审核发布，候选知识经人工确认入图谱',
  '来源可溯，每条引用均可回查原文与章节',
]

const demoAccounts = [
  { label: '管理员', username: 'admin', password: 'admin123' },
  { label: '知识用户', username: 'user1', password: 'admin123' },
]

function fillAccount(acc: (typeof demoAccounts)[number]) {
  form.username = acc.username
  form.password = acc.password
  usernameError.value = ''
  passwordError.value = ''
}

function validate() {
  usernameError.value = form.username ? '' : '请输入用户名'
  passwordError.value = form.password ? '' : '请输入密码'
  return !usernameError.value && !passwordError.value
}

async function handleLogin() {
  if (!validate()) return
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    ElMessage.success('登录成功')
    router.push('/')
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    loading.value = false
  }
}

// ===== 自助注册 =====
const registerVisible = ref(false)
const registering = ref(false)
const registerError = ref('')
const registerForm = reactive({ username: '', display_name: '', password: '', confirm: '' })

function openRegister() {
  Object.assign(registerForm, { username: '', display_name: '', password: '', confirm: '' })
  registerError.value = ''
  registerVisible.value = true
}

/** 前端先挡明显错误（少一次往返）；后端仍会独立校验一次，前端校验不可信。 */
function submitRegister() {
  const username = registerForm.username.trim()
  if (username.length < 3 || username.length > 20) {
    registerError.value = '用户名需 3–20 个字符'
    return
  }
  if (registerForm.password.length < 6) {
    registerError.value = '密码至少 6 位'
    return
  }
  if (registerForm.password !== registerForm.confirm) {
    registerError.value = '两次输入的密码不一致'
    return
  }
  registerError.value = ''
  void doRegister(username)
}

async function doRegister(username: string) {
  registering.value = true
  try {
    // 后端注册成功即返回 token，前端直接进主页，不再走一次登录
    await auth.register(username, registerForm.password, registerForm.display_name.trim())
    registerVisible.value = false
    ElMessage.success('注册成功，已自动登录')
    router.push('/')
  } catch (e) {
    registerError.value = (e as Error).message
  } finally {
    registering.value = false
  }
}

// ===== 忘记密码 =====
// 系统未接入邮件/短信，没有安全的自助找回路径，故只给出口径明确的说明弹窗；
// 落地点是管理员在「账户管理」里重置密码（/api/users/{id}/password）。
const forgotVisible = ref(false)
</script>

<template>
  <div class="login-page">
    <!-- 漂浮光斑：与 ::before/::after 组成三个异步运动的彩斑 -->
    <div class="blob blob-warm"></div>
    <div class="login-card">
      <!-- 左侧品牌区 -->
      <section class="brand-panel">
        <div class="brand-top">
          <div class="brand-icon">🌿</div>
          <div class="brand-name">本草智问</div>
        </div>

        <div class="brand-tag">INTELLIGENT TCM KNOWLEDGE CONSULTATION</div>

        <h1>中医药知识<br />智能问答平台</h1>

        <p class="panel-desc">
          融合多路向量检索、BM25 全文检索与知识图谱推理，基于典籍文献与企业知识库给出有据可查的专业回答。
        </p>

        <div class="feature-wrap">
          <span class="quote quote-open">“</span>
          <ul class="feature-list">
            <li v-for="item in highlights" :key="item">{{ item }}</li>
          </ul>
          <span class="quote quote-close">”</span>
        </div>

        <div class="copyright">© 2026 本草智问 · 中医药智能问答平台</div>
      </section>

      <!-- 右侧登录表单区 -->
      <section class="form-panel">
        <div class="form-tag">BENCAO RAG PLATFORM</div>
        <h2>欢迎登录</h2>
        <div class="title-bar"></div>

        <el-form label-position="top" @submit.prevent>
          <div class="field">
            <label class="field-label">用户名</label>
            <el-input v-model="form.username" placeholder="请输入用户名" @input="usernameError = ''" @keyup.enter="handleLogin">
              <template #prefix><el-icon><User /></el-icon></template>
            </el-input>
            <div v-if="usernameError" class="field-error">{{ usernameError }}</div>
          </div>

          <div class="field">
            <label class="field-label">密码</label>
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              show-password
              @input="passwordError = ''"
              @keyup.enter="handleLogin"
            >
              <template #prefix><el-icon><Lock /></el-icon></template>
            </el-input>
            <div v-if="passwordError" class="field-error">{{ passwordError }}</div>
          </div>
        </el-form>

        <div class="form-aux">
          <el-checkbox v-model="form.remember">记住我</el-checkbox>
          <el-link type="primary" :underline="false" @click="forgotVisible = true">忘记密码？</el-link>
        </div>

        <el-button type="primary" class="login-btn" :loading="loading" @click="handleLogin">立即登录</el-button>

        <div class="register-tip">
          还没有账号？
          <el-link type="primary" :underline="false" @click="openRegister">立即注册</el-link>
        </div>

        <div class="demo-area">
          <div class="demo-head"><span>演示账号（点按自动填充）</span></div>
          <div
            v-for="acc in demoAccounts"
            :key="acc.username"
            class="demo-card"
            @click="fillAccount(acc)"
          >
            <span class="demo-chip">{{ acc.label }}</span>
            <span class="demo-cred">{{ acc.username }} / {{ acc.password }}</span>
            <el-icon class="demo-icon"><CopyDocument /></el-icon>
          </div>
        </div>
      </section>
    </div>

    <!-- 自助注册：注册成功即自动登录（后端直接返回 token） -->
    <el-dialog
      v-model="registerVisible"
      title="注册账号"
      width="440px"
      class="auth-dialog"
      :close-on-click-modal="false"
    >
      <p class="dialog-hint">
        注册后获得「知识用户」角色，可使用辨证问答与图谱检索；如需更高权限请联系管理员。
      </p>
      <div class="field">
        <label class="field-label">用户名</label>
        <el-input v-model="registerForm.username" placeholder="3–20 个字符" @input="registerError = ''" />
      </div>
      <div class="field">
        <label class="field-label">姓名（选填）</label>
        <el-input v-model="registerForm.display_name" placeholder="不填则使用用户名" />
      </div>
      <div class="field">
        <label class="field-label">密码</label>
        <el-input v-model="registerForm.password" type="password" show-password
                  placeholder="至少 6 位" @input="registerError = ''" />
      </div>
      <div class="field">
        <label class="field-label">确认密码</label>
        <el-input v-model="registerForm.confirm" type="password" show-password
                  placeholder="再次输入密码" @input="registerError = ''"
                  @keyup.enter="submitRegister" />
      </div>
      <div v-if="registerError" class="field-error">{{ registerError }}</div>
      <template #footer>
        <el-button @click="registerVisible = false">取消</el-button>
        <el-button type="primary" :loading="registering" @click="submitRegister">注册并登录</el-button>
      </template>
    </el-dialog>

    <!-- 忘记密码：无邮件/短信通道，不做假的自助流程，只说明唯一可行路径 -->
    <el-dialog v-model="forgotVisible" title="忘记密码" width="440px" class="auth-dialog">
      <p class="dialog-hint">
        本系统未接入邮件或短信服务，<strong>暂不支持自助找回密码</strong>。
      </p>
      <p class="dialog-hint">
        请联系系统管理员，在「账户管理」中为你重置密码；管理员账号见登录页下方的演示账号区。
      </p>
      <template #footer>
        <el-button type="primary" @click="forgotVisible = false">我知道了</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
  /* Claude 风格排版：页面所有文字统一走衬线体族（拉丁 Source Serif 4，中文思源宋体/宋体回落） */
  font-family: v-bind(theme.fontDisplay);
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 24px;
  box-sizing: border-box;
  overflow: hidden;
  /* 渐变底 + 光斑：为毛玻璃提供可模糊的层次（彩斑加浓，透出卡片更明显） */
  background:
    radial-gradient(900px 520px at 12% 18%, rgba(82, 183, 136, 0.5), transparent 60%),
    radial-gradient(820px 560px at 88% 82%, rgba(45, 106, 79, 0.48), transparent 62%),
    radial-gradient(640px 440px at 80% 14%, rgba(116, 198, 157, 0.42), transparent 65%),
    radial-gradient(560px 400px at 20% 88%, rgba(188, 108, 37, 0.14), transparent 68%),
    linear-gradient(150deg, #e8f4ec, v-bind(theme.pageBg) 45%, #dcebe2);
}

.login-page::before,
.login-page::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  pointer-events: none;
  will-change: transform;
}

.login-page::before {
  width: 480px;
  height: 480px;
  left: -140px;
  top: -160px;
  background: rgba(82, 183, 136, 0.5);
  animation: blob-drift-a 12s ease-in-out infinite alternate;
}

.login-page::after {
  width: 540px;
  height: 540px;
  right: -180px;
  bottom: -200px;
  background: rgba(45, 106, 79, 0.45);
  animation: blob-drift-b 15s ease-in-out infinite alternate;
}

/* 第三个光斑：暖色点缀，独立周期异步漂浮 */
.blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  pointer-events: none;
  will-change: transform;
}

.blob-warm {
  width: 380px;
  height: 380px;
  right: 18%;
  top: -150px;
  background: rgba(116, 198, 157, 0.42);
  animation: blob-drift-c 18s ease-in-out infinite alternate;
}

@keyframes blob-drift-a {
  0%   { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(160px, 90px) scale(1.18); }
  100% { transform: translate(300px, 40px) scale(0.92); }
}

@keyframes blob-drift-b {
  0%   { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(-190px, -110px) scale(0.9); }
  100% { transform: translate(-60px, -200px) scale(1.15); }
}

@keyframes blob-drift-c {
  0%   { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(-220px, 190px) scale(1.22); }
  100% { transform: translate(-120px, 320px) scale(0.95); }
}

/* 动效敏感用户（ vestibular 障碍等）关闭漂浮 */
@media (prefers-reduced-motion: reduce) {
  .login-page::before,
  .login-page::after,
  .blob-warm {
    animation: none;
  }
}

/* Element Plus 部分组件不继承外层字体，统一拉回 Claude 字体族 */
.login-page :deep(.el-button),
.login-page :deep(.el-input__inner),
.login-page :deep(.el-checkbox__label),
.login-page :deep(.el-link__inner),
.login-page :deep(.el-message-box),
.login-page :deep(.el-form-item__label) {
  font-family: v-bind(theme.fontDisplay);
}

/* ===== 卡片：iOS 液态玻璃（Liquid Glass） =====
   ① 高透底 + 强模糊/增饱和/微提亮（背景光斑透过呈流动折射）
   ② 渐变折射描边：mask 挖空中心只留一圈，上亮下暗模拟玻璃厚边
   ③ 镜面高光层：左上弧形反光 + 斜向扫光，压在内容之上做表面反光膜 */
.login-card {
  position: relative;
  z-index: 1;
  width: min(1000px, 100%);
  min-height: 660px;
  display: grid;
  grid-template-columns: 1.45fr 1fr;
  border-radius: 24px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.12);
  -webkit-backdrop-filter: blur(46px) saturate(180%) brightness(1.06);
  backdrop-filter: blur(46px) saturate(180%) brightness(1.06);
  box-shadow:
    0 30px 76px rgba(26, 50, 32, 0.28),
    0 4px 16px rgba(26, 50, 32, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.5),
    inset 0 -1px 0 rgba(255, 255, 255, 0.12);
}

/* 折射描边：中心被 mask 挖空，只留 1.5px 渐变边 */
.login-card::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1.5px;
  background: linear-gradient(135deg,
    rgba(255, 255, 255, 0.9) 0%,
    rgba(255, 255, 255, 0.38) 24%,
    rgba(255, 255, 255, 0.10) 50%,
    rgba(255, 255, 255, 0.32) 76%,
    rgba(255, 255, 255, 0.72) 100%);
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask-composite: exclude;
  pointer-events: none;
  z-index: 3;
}

/* 镜面高光：只保留一道很淡的斜向扫光，不做大面积反光（压深色左栏会显假） */
.login-card::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(105deg,
    transparent 40%,
    rgba(255, 255, 255, 0.07) 48%,
    transparent 60%);
  pointer-events: none;
  z-index: 3;
}

/* ===== 左侧品牌区：半透明深绿玻璃 ===== */
.brand-panel {
  position: relative;
  overflow: hidden;
  padding: 48px 44px;
  display: flex;
  flex-direction: column;
  color: #fff;
  background: linear-gradient(160deg, rgba(45, 106, 79, 0.85), rgba(26, 50, 32, 0.78));
  -webkit-backdrop-filter: blur(28px) saturate(1.4);
  backdrop-filter: blur(28px) saturate(1.4);
  border-right: 1px solid rgba(255, 255, 255, 0.18);
}

.brand-panel::after {
  content: '';
  position: absolute;
  width: 320px;
  height: 320px;
  right: -120px;
  bottom: -140px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
}

.brand-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.16);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.brand-name {
  font-family: v-bind(theme.fontDisplay);
  font-size: 25px;
  font-weight: 600;
  letter-spacing: 0.2px;
}

.brand-tag {
  margin-top: 34px;
  font-size: 12px;
  letter-spacing: 2.2px;
  color: rgba(255, 255, 255, 0.7);
}

.brand-panel h1 {
  margin: 16px 0 0;
  font-family: v-bind(theme.fontDisplay);
  font-size: 34px;
  /* 600 命中中文 600 字重子集（真加粗），不会落到浏览器的合成加粗 */
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 0;
}

.panel-desc {
  margin: 18px 0 0;
  max-width: 410px;
  font-size: 14px;
  line-height: 1.85;
  color: rgba(255, 255, 255, 0.78);
}

.feature-wrap {
  position: relative;
  margin-top: 30px;
  padding: 4px 8px;
}

.feature-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.feature-list li {
  position: relative;
  padding-left: 20px;
  font-size: 14px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.88);
}

.feature-list li::before {
  content: '—';
  position: absolute;
  left: 0;
  color: rgba(255, 255, 255, 0.5);
}

.quote {
  position: absolute;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 60px;
  line-height: 1;
  color: rgba(255, 255, 255, 0.22);
  pointer-events: none;
}

.quote-open {
  top: -18px;
  left: -8px;
}

.quote-close {
  right: -4px;
  bottom: -30px;
}

.copyright {
  margin-top: auto;
  padding-top: 24px;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.6);
}

/* ===== 右侧表单区：一层淡磨砂玻璃纱，文字可读 ===== */
/* 右栏：白纱减淡 + 局部加饱和提亮，让背景光斑更「果冻」地透出来 */
.form-panel {
  position: relative;
  padding: 48px 44px;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: linear-gradient(190deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.02));
  -webkit-backdrop-filter: blur(14px) saturate(175%) brightness(1.05);
  backdrop-filter: blur(14px) saturate(175%) brightness(1.05);
}

.form-tag {
  font-size: 12px;
  letter-spacing: 2px;
  color: v-bind(theme.textColorMuted);
}

.form-panel h2 {
  margin: 10px 0 14px;
  font-family: v-bind(theme.fontDisplay);
  font-size: 26px;
  font-weight: 600;
  letter-spacing: 0;
  color: v-bind(theme.textColorPrimary);
}

.title-bar {
  width: 42px;
  height: 3px;
  border-radius: 2px;
  background: v-bind(theme.colorPrimary);
  margin-bottom: 24px;
}

.field {
  margin-bottom: 16px;
}

/* 弹窗正文说明（注册/忘记密码）：弹窗内容被 teleport 到 body，
   字体走全局 --el-font-family（已在 element-overrides.css 设为衬线族） */
.dialog-hint {
  margin: 0 0 14px;
  font-size: 13.5px;
  line-height: 1.75;
  color: v-bind(theme.textColorSecondary);
}

.dialog-hint:last-child {
  margin-bottom: 0;
}

.field-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: v-bind(theme.textColorMuted);
}

.field-error {
  margin-top: 6px;
  font-size: 12.5px;
  color: v-bind(theme.colorError);
}

.field-error::before {
  content: '!';
  display: inline-block;
  width: 12px;
  height: 12px;
  margin-right: 5px;
  border-radius: 50%;
  font-size: 10px;
  line-height: 12px;
  text-align: center;
  color: v-bind(theme.cardBg);
  background: v-bind(theme.colorError);
}

/* 输入框改为「仅下边框」线性样式，贴合参考图 */
:deep(.el-input__wrapper) {
  padding: 2px 0 9px;
  border-radius: 0;
  background: transparent;
  box-shadow: none !important;
  border-bottom: 1px solid v-bind(theme.borderColor);
  transition: border-color 0.2s;
}

:deep(.el-input__wrapper.is-focus),
:deep(.el-input__wrapper:hover) {
  border-bottom-color: v-bind(theme.colorPrimary);
}

:deep(.el-input__prefix) {
  margin-right: 6px;
  color: v-bind(theme.textColorMuted);
}

:deep(.el-input__inner) {
  color: v-bind(theme.textColorPrimary);
}

:deep(.el-input__inner::placeholder) {
  color: v-bind(theme.textColorMuted);
}

.form-aux {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 6px 0 26px;
}

.form-aux :deep(.el-checkbox__label) {
  font-size: 13.5px;
  color: v-bind(theme.textColorSecondary);
}

.form-aux :deep(.el-link__inner) {
  font-size: 13.5px;
  color: v-bind(theme.colorPrimary);
}

.login-btn {
  width: 100%;
  height: 46px;
  font-size: 15px;
  letter-spacing: 4px;
  border-radius: 8px;
}

.register-tip {
  margin-top: 18px;
  text-align: center;
  font-size: 13.5px;
  color: v-bind(theme.textColorSecondary);
}

.register-tip :deep(.el-link__inner) {
  font-size: 13.5px;
  color: v-bind(theme.colorPrimary);
}

.demo-area {
  margin-top: 34px;
}

.demo-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

/* 虚线只画在文字两侧，避免用实心底色遮挡（玻璃面板上会露馅） */
.demo-head::before,
.demo-head::after {
  content: '';
  flex: 1;
  border-top: 1px dashed v-bind(theme.borderColor);
}

.demo-head span {
  font-size: 12px;
  letter-spacing: 1.2px;
  color: v-bind(theme.textColorMuted);
}

.demo-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  margin-bottom: 10px;
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.4);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}

.demo-card:hover {
  border-color: v-bind(theme.colorPrimary);
  background: rgba(255, 255, 255, 0.65);
}

.demo-chip {
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 12.5px;
  color: v-bind(theme.colorPrimary);
  background: rgba(255, 255, 255, 0.65);
}

.demo-cred {
  flex: 1;
  font-size: 13.5px;
  color: v-bind(theme.textColorBody);
}

.demo-icon {
  color: v-bind(theme.textColorMuted);
}

.demo-card:hover .demo-icon {
  color: v-bind(theme.colorPrimary);
}

@media (max-width: 900px) {
  .login-card {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .brand-panel {
    padding: 36px 32px;
  }

  .brand-panel h1 {
    font-size: 26px;
  }

  .copyright {
    padding-top: 20px;
  }

  .form-panel {
    padding: 36px 32px;
  }
}
</style>
