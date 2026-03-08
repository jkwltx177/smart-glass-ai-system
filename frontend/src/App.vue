<script setup lang="ts">
import { ref } from 'vue'
import HistoryView from './HistoryView.vue'
import LoginView from './LoginView.vue'
import MobileCaptureView from './MobileCaptureView.vue'
import MenuView from './MenuView.vue'
import RagView from './RagView.vue'

const LOGIN_API_URL = 'http://localhost:8081/auth/login'
const REGISTER_API_URL = 'http://localhost:8081/auth/register'
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
const isMobileCapture = ref(false)
const mobileCode = ref('')

const stripMarkdownAsterisks = (text: string): string =>
  String(text ?? '')
    .replace(/\*\*/g, '')
    .replace(/__/g, '')
    .replace(/\* /g, '')

const normalizeActionSteps = (steps: unknown, explanation: string): string[] => {
  if (!Array.isArray(steps)) return []
  const placeholder = '상세 조치 내용은 아래 분석 결과를 확인하세요.'
  const cleaned = steps
    .map((s) => stripMarkdownAsterisks(String(s ?? '')).trim())
    .filter((s) => !!s)
    .filter((s) => s !== placeholder)
    .filter((s) => !explanation.includes(s))
  return Array.from(new Set(cleaned))
}

type AuthSubmitPayload = {
  mode: 'login' | 'signup'
  id: string
  pw: string
  companyName?: string
  companyAuthCode?: string
}

const onSubmit = async (credentials: AuthSubmitPayload) => {
  if (!credentials.id || !credentials.pw) {
    message.value = 'id와 pw를 모두 입력해주세요.'
    return
  }
  if (credentials.mode === 'signup' && (!credentials.companyName || !credentials.companyAuthCode)) {
    message.value = '회원가입 시 회사명과 인증 코드를 모두 입력해주세요.'
    return
  }

  loginLoading.value = true
  message.value = ''

  try {
    if (credentials.mode === 'signup') {
      const signupResponse = await fetch(REGISTER_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username: credentials.id,
          password: credentials.pw,
          companyName: credentials.companyName,
          companyAuthCode: credentials.companyAuthCode,
        }),
      })

      if (!signupResponse.ok) {
        throw new Error(`회원가입 실패 (${signupResponse.status})`)
      }

      message.value = '회원가입이 완료되었습니다. 같은 계정으로 로그인하세요.'
      return
    }

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
    message.value = `인증 요청 중 오류가 발생했습니다: ${errorMessage}`
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

const onMobileResult = (payload: { incidentId: string; explanation: string; steps: string[] }) => {
  incidentId.value = payload.incidentId
  const cleanExplanation = stripMarkdownAsterisks(payload.explanation ?? '')
  const cleanSteps = normalizeActionSteps(payload.steps, cleanExplanation)
  ragMessage.value = cleanSteps.length > 0
    ? `[분석 결과]\n${cleanExplanation}\n\n[조치 절차]\n${cleanSteps.join('\n')}`
    : `[분석 결과]\n${cleanExplanation}`
}

const initMode = () => {
  const params = new URLSearchParams(window.location.search)
  const mobile = params.get('mobile')
  const code = params.get('code')
  if (mobile === '1') {
    isMobileCapture.value = true
    mobileCode.value = code || ''
  }
}
initMode()

const sendRagRequest = async (files: { imageFile: File | null; audioFile: File | null; equipmentId: string }) => {
  if (!files.audioFile) {
    ragMessage.value = '음성 파일은 필수입니다.'
    return
  }

  ragLoading.value = true
  ragMessage.value = ''

  const formData = new FormData()
  formData.append('audio', files.audioFile)
  formData.append('equipment_id', files.equipmentId || 'DEV-MAF-01')
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
    const cleanExplanation = stripMarkdownAsterisks(data.explanation ?? '')
    const cleanSteps = normalizeActionSteps(data.action_plan?.steps, cleanExplanation)
    ragMessage.value = cleanSteps.length > 0
      ? `[분석 결과]\n${cleanExplanation}\n\n[조치 절차]\n${cleanSteps.join('\n')}`
      : `[분석 결과]\n${cleanExplanation}`
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
  <MobileCaptureView v-if="isMobileCapture" :initial-code="mobileCode" />

  <LoginView v-else-if="currentView === 'login'" :login-loading="loginLoading" :message="message" @submit="onSubmit" />

  <MenuView v-else-if="currentView === 'menu'" @navigate="navigateTo" @logout="onLogout" />

  <RagView
    v-else-if="currentView === 'rag'"
    :rag-loading="ragLoading"
    :rag-message="ragMessage"
    :incident-id="incidentId"
    @submit="sendRagRequest"
    @mobile-result="onMobileResult"
    @back="navigateTo('menu')"
    @logout="onLogout"
  />

  <HistoryView v-else @back="navigateTo('menu')" @logout="onLogout" />
</template>
