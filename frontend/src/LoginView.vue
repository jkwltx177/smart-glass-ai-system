<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  loginLoading: boolean
  message: string
}>()

const emit = defineEmits<{
  submit: [
    {
      mode: 'login' | 'signup'
      id: string
      pw: string
      companyName?: string
      companyAuthCode?: string
    },
  ]
}>()

const userId = ref('')
const userPw = ref('')
const companyName = ref('')
const companyAuthCode = ref('')
const mode = ref<'login' | 'signup'>('login')

const onSubmit = () => {
  emit('submit', {
    mode: mode.value,
    id: userId.value,
    pw: userPw.value,
    companyName: companyName.value,
    companyAuthCode: companyAuthCode.value,
  })
}
</script>

<template>
  <main class="auth-viewport">
    <div class="glow-overlay"></div>

    <section class="auth-wrapper">
      <header class="auth-header">
        <div class="brand-symbol">SG</div>
        <h1 class="brand-name">Smart Glass <span class="text-accent">Intelligence</span></h1>
      </header>

      <div class="auth-module">
        <div class="module-intro">
          <h2 class="module-title">Platform Access</h2>
          <p class="module-subtitle">
            {{ mode === 'login' ? '서비스 권한 확인을 위해 인증 정보를 입력하십시오.' : '신규 계정 등록을 위해 회사 인증 정보를 입력하십시오.' }}
          </p>
        </div>

        <div class="mode-switch">
          <button type="button" class="mode-btn" :class="{ active: mode === 'login' }" @click="mode = 'login'">Sign In</button>
          <button type="button" class="mode-btn" :class="{ active: mode === 'signup' }" @click="mode = 'signup'">Sign Up</button>
        </div>

        <form class="auth-form" @submit.prevent="onSubmit">
          <div class="form-body">
            
            <div class="input-container">
              <div class="input-field">
                <label for="id">Identity</label>
                <input 
                  id="id" 
                  v-model="userId" 
                  type="text" 
                  placeholder="Username" 
                  required 
                  autocomplete="username"
                />
              </div>

              <div class="input-field">
                <div class="field-header">
                  <label for="pw">Credential</label>
                  <a v-if="mode === 'login'" href="#" class="field-link">Forgot?</a>
                </div>
                <input 
                  id="pw" 
                  v-model="userPw" 
                  type="password" 
                  placeholder="Password" 
                  required 
                  autocomplete="current-password"
                />
              </div>

              <div v-if="mode === 'signup'" class="input-field">
                <label for="company">Company</label>
                <input
                  id="company"
                  v-model="companyName"
                  type="text"
                  placeholder="Company Name"
                  required
                  autocomplete="organization"
                />
              </div>

              <div v-if="mode === 'signup'" class="input-field">
                <label for="company-code">Company Auth Code</label>
                <input
                  id="company-code"
                  v-model="companyAuthCode"
                  type="password"
                  placeholder="Verification Code"
                  required
                />
              </div>
            </div>

            <div class="form-actions">
              <button type="submit" class="submit-btn" :disabled="props.loginLoading">
                <div v-if="props.loginLoading" class="btn-spinner"></div>
                <span>{{ props.loginLoading ? 'Authenticating' : mode === 'login' ? 'Sign In' : 'Create Account' }}</span>
              </button>

              <label class="session-label">
                <input type="checkbox">
                <span class="checkmark"></span>
                Keep Session Active
              </label>
            </div>
          </div>
        </form>

        <transition name="fade">
          <div v-if="props.message" class="error-notice">
            <p class="error-text">{{ props.message }}</p>
          </div>
        </transition>
      </div>

      <footer class="auth-footer">
        <p>&copy; 2026 Smart Glass AI. <span class="divider">|</span> <a href="#">Security Policy</a></p>
      </footer>
    </section>
  </main>
</template>

<style scoped>
/* 뷰포트 및 배경 스타일 */
.auth-viewport {
  min-height: 100vh;
  background-color: #0d1117;
  color: #f0f6fc;
  font-family: 'Inter', -apple-system, sans-serif;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 24px;
  position: relative;
}

.glow-overlay {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  background: radial-gradient(circle at 50% 0%, rgba(59, 130, 246, 0.08) 0%, transparent 70%);
  pointer-events: none;
}

.auth-wrapper {
  width: 100%;
  max-width: 420px;
  z-index: 10;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* 상단 헤더 */
.auth-header {
  text-align: center;
  margin-bottom: 40px;
}

.brand-symbol {
  width: 44px; height: 44px;
  background: #f0f6fc; color: #0d1117;
  font-weight: 800; display: inline-flex;
  align-items: center; justify-content: center;
  border-radius: 6px; margin-bottom: 12px;
}

.brand-name { font-size: 18px; font-weight: 700; margin: 0; }
.text-accent { color: #58a6ff; }

/* 메인 모듈 카드 */
.auth-module {
  width: 100%;
  background: #161b22;
  border: 1px solid #30363d;
  padding: 48px 24px;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.module-intro { text-align: center; margin-bottom: 40px; }
.module-title { font-size: 22px; font-weight: 700; margin-bottom: 8px; color: #f0f6fc; }
.module-subtitle { font-size: 13px; color: #8b949e; }

.mode-switch {
  width: 100%;
  max-width: 320px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 24px;
}

.mode-btn {
  border: 1px solid #30363d;
  background: #0d1117;
  color: #8b949e;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.mode-btn.active {
  border-color: #58a6ff;
  color: #f0f6fc;
  background: rgba(88, 166, 255, 0.18);
}

/* 폼 데이터 영역 */
.auth-form {
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.form-body {
  width: 100%;
  max-width: 320px;
  display: flex;
  flex-direction: column;
  gap: 32px; /* 버튼 영역과 입력 그룹 간의 넉넉한 간격 */
}

/* 입력 필드 그룹: Identity와 Credential 사이의 간격 설정 */
.input-container {
  display: flex;
  flex-direction: column;
  gap: 24px; /* Identity와 Credential 입력칸 사이의 간격 */
}

.input-field { display: flex; flex-direction: column; gap: 10px; } /* 라벨과 입력창 사이 간격 */

.field-header { display: flex; justify-content: space-between; align-items: center; }

label { font-size: 12px; font-weight: 600; color: #c9d1d9; letter-spacing: 0.02em; }

.field-link { font-size: 11px; color: #58a6ff; text-decoration: none; }

input {
  width: 100%;
  padding: 12px 16px;
  background: #0d1117;
  border: 1px solid #30363d;
  border-radius: 6px;
  color: #f0f6fc;
  font-size: 14px;
  box-sizing: border-box; /* 패딩 포함 너비 계산 */
  transition: 0.2s;
}

input:focus { border-color: #58a6ff; outline: none; box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.1); }

/* 실행 버튼 영역 */
.form-actions {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.submit-btn {
  width: 100%;
  padding: 14px;
  background: #f0f6fc; color: #0d1117;
  border: none; border-radius: 6px;
  font-weight: 700; font-size: 14px;
  cursor: pointer; transition: 0.2s;
  display: flex; justify-content: center; align-items: center; gap: 10px;
}

.submit-btn:hover:not(:disabled) { background: #58a6ff; color: #ffffff; }
.submit-btn:disabled { background: #30363d; color: #8b949e; cursor: not-allowed; }

.session-label {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: #8b949e; cursor: pointer;
}

/* 에러 섹션 */
.error-notice {
  margin-top: 24px; width: 100%; max-width: 320px;
  padding: 12px; background: rgba(248, 81, 73, 0.05);
  border: 1px solid rgba(248, 81, 73, 0.15); border-radius: 6px;
}

.error-text { font-size: 12px; color: #f85149; margin: 0; text-align: center; }

/* 푸터 */
.auth-footer {
  margin-top: 32px; text-align: center;
  font-size: 11px; color: #484f58;
}

.divider { margin: 0 8px; opacity: 0.5; }
.auth-footer a { color: #8b949e; text-decoration: none; }

/* 스피너 */
.btn-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(0,0,0,0.1); border-top-color: currentColor;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }
</style>
