<script setup lang="ts">
import { ref } from 'vue'

const LOGIN_API_URL = 'http://localhost:8081/auth/login'
const ACCESS_TOKEN_STORAGE_KEY = 'accessToken'
const TOKEN_TYPE_STORAGE_KEY = 'tokenType'
const EXPIRES_IN_STORAGE_KEY = 'expiresInSeconds'

type LoginResponse = {
  accessToken: string
  tokenType: string
  expiresInSeconds: number
}

const userId = ref('')
const userPw = ref('')
const message = ref('')
const currentView = ref<'login' | 'menu' | 'rag' | 'history'>('login')
const selectedImage = ref<File | null>(null)
const selectedAudio = ref<File | null>(null)
const ragLoading = ref(false)
const ragMessage = ref('')
const loginLoading = ref(false)

const onSubmit = async () => {
  if (!userId.value || !userPw.value) {
    message.value = 'id와 pw를 모두 입력해주세요.'
    return
  }

  loginLoading.value = true
  message.value = ''

  try {
    const response = await fetch(LOGIN_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        username: userId.value,
        password: userPw.value,
      }),
    })

    if (!response.ok) {
      throw new Error(`로그인 실패 (${response.status})`)
    }

    const payload = (await response.json()) as Partial<LoginResponse>
    if (
      typeof payload.accessToken !== 'string' ||
      typeof payload.tokenType !== 'string' ||
      typeof payload.expiresInSeconds !== 'number'
    ) {
      throw new Error('로그인 응답 형식이 올바르지 않습니다.')
    }

    localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, payload.accessToken)
    localStorage.setItem(TOKEN_TYPE_STORAGE_KEY, payload.tokenType)
    localStorage.setItem(EXPIRES_IN_STORAGE_KEY, String(payload.expiresInSeconds))
    currentView.value = 'menu'
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.'
    message.value = `로그인 요청 중 오류가 발생했습니다: ${errorMessage}`
  } finally {
    loginLoading.value = false
  }
}

const onLogout = () => {
  userId.value = ''
  userPw.value = ''
  message.value = ''
  selectedImage.value = null
  selectedAudio.value = null
  ragMessage.value = ''
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  localStorage.removeItem(TOKEN_TYPE_STORAGE_KEY)
  localStorage.removeItem(EXPIRES_IN_STORAGE_KEY)
  currentView.value = 'login'
}

const onImageChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  selectedImage.value = target.files?.[0] ?? null
}

const onAudioChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  selectedAudio.value = target.files?.[0] ?? null
}

const sendRagRequest = async () => {
  if (!selectedAudio.value) {
    ragMessage.value = '음성 파일은 필수입니다.'
    return
  }

  ragLoading.value = true
  ragMessage.value = ''

  const formData = new FormData()
  formData.append('audio', selectedAudio.value)
  if (selectedImage.value) {
    formData.append('image', selectedImage.value)
  }

  try {
    const accessToken = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
    const tokenType = localStorage.getItem(TOKEN_TYPE_STORAGE_KEY) ?? 'Bearer'
    if (!accessToken) {
      ragMessage.value = '로그인이 필요합니다. 다시 로그인해주세요.'
      return
    }

    const response = await fetch('/api/rag/query', {
      method: 'POST',
      headers: {
        Authorization: `${tokenType} ${accessToken}`,
      },
      body: formData,
    })

    if (!response.ok) {
      throw new Error(`요청 실패 (${response.status})`)
    }

    ragMessage.value = 'RAG 요청을 성공적으로 전송했습니다.'
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.'
    ragMessage.value = `요청 중 오류가 발생했습니다: ${errorMessage}`
  } finally {
    ragLoading.value = false
  }
}
</script>

<template>
  <main v-if="currentView === 'login'" class="login-page">
    <section class="login-card">
      <h1>로그인</h1>

      <form @submit.prevent="onSubmit">
        <label for="id">id</label>
        <input id="id" v-model="userId" type="text" placeholder="id를 입력하세요" />

        <label for="pw">pw</label>
        <input id="pw" v-model="userPw" type="password" placeholder="pw를 입력하세요" />

        <button type="submit" :disabled="loginLoading">
          {{ loginLoading ? '로그인 중...' : '로그인' }}
        </button>
      </form>

      <p v-if="message" class="message">{{ message }}</p>
    </section>
  </main>

  <main v-else-if="currentView === 'menu'" class="menu-page">
    <div class="shell">
      <header class="menu-header">
        <div class="brand">
          <div class="brand-icon">S</div>
          <div>
            <div class="brand-title">Service Menu</div>
            <div class="brand-sub">로그인 이후 사용할 기능을 선택하세요.</div>
          </div>
        </div>
        <button class="logout-btn" type="button" @click="onLogout">로그아웃</button>
      </header>

      <section>
        <h1 class="hero-title">원하는 작업 페이지로 이동</h1>
        <p class="hero-sub">
          아래 버튼 중 하나를 눌러 이동하세요. 첫 번째는 RAG 질의, 두 번째는 요청 이력관리 페이지입니다.
        </p>

        <div class="grid">
          <article class="card">
            <div>
              <div class="card-label">RAG</div>
              <h2 class="card-title">RAG 관련 질의</h2>
              <p class="card-desc">문서 기반 검색과 생성형 응답이 필요한 질의를 수행하는 페이지로 이동합니다.</p>
            </div>
            <button class="btn" type="button" @click="currentView = 'rag'">RAG 질의 페이지 이동 →</button>
          </article>

          <article class="card">
            <div>
              <div class="card-label">HISTORY</div>
              <h2 class="card-title">요청 이력관리</h2>
              <p class="card-desc">사용자 요청 내역을 확인하고 관리할 수 있는 페이지로 이동합니다.</p>
            </div>
            <button class="btn" type="button" @click="currentView = 'history'">요청 이력관리 페이지 이동 →</button>
          </article>
        </div>
      </section>
    </div>
  </main>

  <main v-else-if="currentView === 'rag'" class="detail-page">
    <section class="detail-card">
      <h1>RAG 관련 질의 페이지</h1>
      <p>이미지 파일(선택)과 음성 파일(필수)을 업로드해 RAG 요청을 전송할 수 있습니다.</p>

      <div class="rag-form">
        <label class="file-label" for="imageFile">이미지 파일 (선택)</label>
        <input id="imageFile" class="file-input" type="file" accept="image/*" @change="onImageChange" />

        <label class="file-label" for="audioFile">음성 파일</label>
        <input id="audioFile" class="file-input" type="file" accept="audio/*" @change="onAudioChange" />

        <button class="btn rag-submit-btn" type="button" :disabled="ragLoading" @click="sendRagRequest">
          {{ ragLoading ? '요청 전송 중...' : '요청 보내기' }}
        </button>

        <p v-if="ragMessage" class="rag-message">{{ ragMessage }}</p>
      </div>

      <div class="detail-actions">
        <button class="link-btn" type="button" @click="currentView = 'menu'">← 메뉴로 돌아가기</button>
        <button class="link-btn logout-link" type="button" @click="onLogout">로그아웃</button>
      </div>
    </section>
  </main>

  <main v-else class="detail-page">
    <section class="detail-card">
      <h1>요청 이력관리 페이지</h1>
      <p>여기에 요청 로그 조회/필터링/삭제 기능을 확장해서 붙이면 됩니다.</p>
      <div class="detail-actions">
        <button class="link-btn" type="button" @click="currentView = 'menu'">← 메뉴로 돌아가기</button>
        <button class="link-btn logout-link" type="button" @click="onLogout">로그아웃</button>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: #f4f6f8;
}

.login-card {
  width: 100%;
  max-width: 360px;
  padding: 24px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.08);
}

h1 {
  margin: 0 0 20px;
  text-align: center;
}

form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

label {
  font-size: 14px;
  font-weight: 600;
}

input {
  padding: 10px;
  border: 1px solid #d4d9df;
  border-radius: 8px;
}

button {
  margin-top: 12px;
  padding: 10px;
  border: none;
  border-radius: 8px;
  background: #1f6feb;
  color: #fff;
  cursor: pointer;
}

button:hover {
  background: #1a5fcc;
}

.message {
  margin-top: 14px;
  font-size: 14px;
  color: #1f6feb;
}

.menu-page {
  min-height: 100vh;
  padding: 32px 16px;
  background: radial-gradient(circle at top, #e0edff 0, #f3f4f6 45%);
}

.shell {
  width: 100%;
  max-width: 860px;
  margin: 0 auto;
  background: #fff;
  border-radius: 24px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.12);
  padding: 32px 28px 28px;
}

.menu-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 16px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-icon {
  width: 32px;
  height: 32px;
  border-radius: 12px;
  background: linear-gradient(135deg, #2563eb, #4f46e5);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 18px;
  font-weight: 700;
}

.brand-title {
  font-weight: 650;
  letter-spacing: 0.03em;
  font-size: 18px;
}

.brand-sub {
  font-size: 12px;
  color: #6b7280;
}

.hero-title {
  font-size: 28px;
  font-weight: 700;
  margin: 4px 0 6px;
}

.hero-sub {
  font-size: 14px;
  color: #6b7280;
  max-width: 620px;
}

.grid {
  margin-top: 24px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
}

.card {
  flex: 1 1 300px;
  border-radius: 16px;
  border: 1px solid #e5e7eb;
  padding: 18px 16px 18px;
  background: #f9fafb;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  transition: transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease, background 0.12s ease;
}

.card:hover {
  transform: translateY(-3px);
  box-shadow: 0 18px 35px rgba(15, 23, 42, 0.12);
  border-color: #cbd5f5;
  background: #fff;
}

.card-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: #2563eb;
  margin-bottom: 6px;
  font-weight: 600;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 4px;
}

.card-desc {
  font-size: 13px;
  color: #6b7280;
  margin-bottom: 14px;
  min-height: 64px;
}

.logout-btn {
  margin: 0;
  padding: 8px 14px;
  border-radius: 999px;
  border: 1px solid #dbe3f2;
  background: #fff;
  color: #1f6feb;
  font-size: 13px;
  font-weight: 600;
}

.logout-btn:hover {
  background: #eff3ff;
}

.detail-page {
  margin: 0;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: #f4f6f8;
  color: #111827;
}

.detail-card {
  width: 100%;
  max-width: 560px;
  padding: 24px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.12);
}

.detail-card h1 {
  margin: 0 0 12px;
}

.detail-card p {
  margin: 0 0 20px;
  color: #6b7280;
}

.rag-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.file-label {
  font-size: 14px;
  font-weight: 600;
}

.file-input {
  margin-bottom: 8px;
}

.rag-submit-btn {
  margin-top: 4px;
}

.rag-message {
  margin: 8px 0 0;
  font-size: 14px;
  color: #1f6feb;
}

.link-btn {
  border: none;
  background: transparent;
  color: #2563eb;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
}

.detail-actions {
  display: flex;
  gap: 12px;
}

.logout-link {
  color: #dc2626;
}

@media (max-width: 640px) {
  .shell {
    border-radius: 18px;
    padding: 20px 18px 18px;
  }

  .hero-title {
    font-size: 22px;
  }
}
</style>
