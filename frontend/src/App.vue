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

    // '/api' 경로는 vite.config.ts의 프록시를 통해 FastAPI로 전달됩니다.
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
        <p class="hero-sub">아래 버튼 중 하나를 눌러 이동하세요.</p>
        <div class="grid">
          <article class="card">
            <h2 class="card-title">RAG 관련 질의</h2>
            <button class="btn" type="button" @click="currentView = 'rag'">이동 →</button>
          </article>
          <article class="card">
            <h2 class="card-title">요청 이력관리</h2>
            <button class="btn" type="button" @click="currentView = 'history'">이동 →</button>
          </article>
        </div>
      </section>
    </div>
  </main>

  <main v-else-if="currentView === 'rag'" class="detail-page">
    <section class="detail-card">
      <h1>RAG 관련 질의 페이지</h1>
      <div class="rag-form">
        <label for="imageFile">이미지 파일 (선택)</label>
        <input id="imageFile" type="file" @change="onImageChange" />
        <label for="audioFile">음성 파일</label>
        <input id="audioFile" type="file" @change="onAudioChange" />
        <button class="btn" :disabled="ragLoading" @click="sendRagRequest">전송</button>
        <p v-if="ragMessage">{{ ragMessage }}</p>
      </div>
      <button @click="currentView = 'menu'">돌아가기</button>
    </section>
  </main>
</template>

<style scoped>
/* CSS 스타일 생략 (기존 App.vue와 동일) */
</style>
