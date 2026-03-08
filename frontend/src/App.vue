<script setup lang="ts">
import { ref } from 'vue'
import HistoryView from './HistoryView.vue'
import LoginView from './LoginView.vue'
import MenuView from './MenuView.vue'
import RagView from './RagView.vue'

const LOGIN_API_URL = 'http://localhost:8081/auth/login'
const ACCESS_TOKEN_STORAGE_KEY = 'accessToken'
const TOKEN_TYPE_STORAGE_KEY = 'tokenType'
const EXPIRES_IN_STORAGE_KEY = 'expiresInSeconds'

type LoginResponse = {
  accessToken: string
  tokenType: string
  expiresInSeconds: number
}

type ViewType = 'login' | 'menu' | 'rag' | 'history'

const currentView = ref<ViewType>('login')
const message = ref('')
const ragMessage = ref('')
const incidentId = ref<string | null>(null)
const loginLoading = ref(false)
const ragLoading = ref(false)

const onSubmit = async (credentials: { id: string; pw: string }) => {
  if (!credentials.id || !credentials.pw) {
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
        username: credentials.id,
        password: credentials.pw,
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
  message.value = ''
  ragMessage.value = ''
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  localStorage.removeItem(TOKEN_TYPE_STORAGE_KEY)
  localStorage.removeItem(EXPIRES_IN_STORAGE_KEY)
  currentView.value = 'login'
}

type MenuTarget = 'dashboard' | 'rag' | 'history' | 'analytics' | 'settings'

const navigateTo = (view: MenuTarget | Exclude<ViewType, 'login'>) => {
  ragMessage.value = ''
  if (view === 'rag' || view === 'history') {
    currentView.value = view
    return
  }

  currentView.value = 'menu'
}

const sendRagRequest = async (files: { imageFile: File | null; audioFile: File | null }) => {
  if (!files.audioFile) {
    ragMessage.value = '음성 파일은 필수입니다.'
    return
  }

  ragLoading.value = true
  ragMessage.value = ''

  const formData = new FormData()
  formData.append('audio', files.audioFile)
  if (files.imageFile) {
    formData.append('image', files.imageFile)
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

    const data = await response.json()
    ragMessage.value = `[분석 결과]\n${data.explanation}\n\n[조치 절차]\n${data.action_plan?.steps?.join('\n') || '없음'}`
    incidentId.value = data.incident_id || null
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.'
    ragMessage.value = `요청 중 오류가 발생했습니다: ${errorMessage}`
    incidentId.value = null
  } finally {
    ragLoading.value = false
  }
}
</script>

<template>
  <LoginView v-if="currentView === 'login'" :login-loading="loginLoading" :message="message" @submit="onSubmit" />

  <MenuView v-else-if="currentView === 'menu'" @navigate="navigateTo" @logout="onLogout" />

  <RagView
    v-else-if="currentView === 'rag'"
    :rag-loading="ragLoading"
    :rag-message="ragMessage"
    :incident-id="incidentId"
    @submit="sendRagRequest"
    @back="navigateTo('menu')"
    @logout="onLogout"
  />

  <HistoryView v-else @back="navigateTo('menu')" @logout="onLogout" />
</template>
