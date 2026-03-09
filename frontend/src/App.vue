<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import HistoryView from './HistoryView.vue'
import LoginView from './LoginView.vue'
import MobileCaptureView from './MobileCaptureView.vue'
import MenuView from './MenuView.vue'
import RagView from './RagView.vue'

const AUTH_BASE_URL = (import.meta.env.VITE_AUTH_BASE_URL as string | undefined)?.trim() || '/auth'
const authUrl = (path: '/login' | '/register') => `${AUTH_BASE_URL.replace(/\/$/, '')}${path}`
const LOGIN_API_URL = authUrl('/login')
const REGISTER_API_URL = authUrl('/register')
const ACCESS_TOKEN_STORAGE_KEY = 'accessToken'
const TOKEN_TYPE_STORAGE_KEY = 'tokenType'
const EXPIRES_IN_STORAGE_KEY = 'expiresInSeconds'

type LoginResponse = {
  accessToken: string
  tokenType: string
  expiresInSeconds: number
}

type ViewType = 'login' | 'menu' | 'rag' | 'history'
type PredictiveSummary = {
  failure_probability: number
  predicted_rul_minutes: number
  anomaly_score: number
} | null

const currentView = ref<ViewType>('login')
const message = ref('')
const ragMessage = ref('')
const incidentId = ref<string | null>(null)
const predictiveSummary = ref<PredictiveSummary>(null)
const loginLoading = ref(false)
const ragLoading = ref(false)
const isMobileCapture = ref(false)
const mobileCode = ref('')
const currentUserName = ref('로그인 사용자')
const currentUserRole = ref('인증 사용자')
const currentUserAvatar = computed(() => {
  const base = String(currentUserName.value || '').trim()
  if (!base) return 'US'
  const only = base.replace(/[^a-zA-Z0-9가-힣]/g, '')
  return (only.slice(0, 2) || 'US').toUpperCase()
})

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

const decodeJwtPayload = (token: string): Record<string, unknown> | null => {
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const b64 = part.replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4)
    const json = atob(padded)
    return JSON.parse(json) as Record<string, unknown>
  } catch {
    return null
  }
}

const toDisplayRole = (rawRole: string): string => {
  const normalized = rawRole.trim().toUpperCase()
  if (!normalized) return '인증 사용자'
  if (normalized === 'ADMIN') return '관리자 권한'
  if (normalized === 'ENTERPRISE_ADMIN') return '엔터프라이즈 관리자'
  if (normalized === 'FIELD_OPERATOR') return '현장 작업자'
  return normalized
}

const syncUserFromToken = (token: string | null) => {
  if (!token) return
  const payload = decodeJwtPayload(token)
  if (!payload) return
  const sub = typeof payload.sub === 'string' ? payload.sub : ''
  const role = typeof payload.role === 'string' ? payload.role : ''
  if (sub) currentUserName.value = sub
  if (role) currentUserRole.value = toDisplayRole(role)
}

type AuthSubmitPayload = {
  mode: 'login' | 'signup'
  id: string
  pw: string
  companyName?: string
  companyAuthCode?: string
}

const onSubmit = async (credentials: AuthSubmitPayload) => {
  const username = String(credentials.id || '').trim()
  const password = String(credentials.pw || '').trim()
  const companyName = String(credentials.companyName || '').trim()
  const companyAuthCode = String(credentials.companyAuthCode || '').trim()

  if (!username || !password) {
    message.value = 'id와 pw를 모두 입력해주세요.'
    return
  }
  if (credentials.mode === 'signup' && (!companyName || !companyAuthCode)) {
    message.value = '회원가입 시 회사명과 인증 코드를 모두 입력해주세요.'
    return
  }

  loginLoading.value = true
  message.value = ''

  try {
    const readErrorDetail = async (response: Response) => {
      try {
        const contentType = response.headers.get('content-type') || ''
        if (contentType.includes('application/json')) {
          const payload = await response.json()
          const detail =
            (typeof payload?.detail === 'string' && payload.detail) ||
            (typeof payload?.message === 'string' && payload.message) ||
            ''
          return detail
        }
        const text = (await response.text()).trim()
        return text
      } catch {
        return ''
      }
    }

    if (credentials.mode === 'signup') {
      const signupResponse = await fetch(REGISTER_API_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          username,
          password,
          companyName,
          companyAuthCode,
        }),
      })

      if (!signupResponse.ok) {
        const detail = await readErrorDetail(signupResponse)
        throw new Error(`회원가입 실패 (${signupResponse.status})${detail ? ` - ${detail}` : ''}`)
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
        username,
        password,
      }),
    })

    if (!response.ok) {
      const detail = await readErrorDetail(response)
      throw new Error(`로그인 실패 (${response.status})${detail ? ` - ${detail}` : ''}`)
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
    currentUserName.value = username
    currentUserRole.value = '인증 사용자'
    syncUserFromToken(payload.accessToken)
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
  predictiveSummary.value = null
  localStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
  localStorage.removeItem(TOKEN_TYPE_STORAGE_KEY)
  localStorage.removeItem(EXPIRES_IN_STORAGE_KEY)
  currentUserName.value = '로그인 사용자'
  currentUserRole.value = '인증 사용자'
  currentView.value = 'login'
}

type MenuTarget = 'dashboard' | 'rag' | 'history' | 'analytics' | 'settings'

const navigateTo = (view: MenuTarget | Exclude<ViewType, 'login'>) => {
  ragMessage.value = ''
  predictiveSummary.value = null
  if (view === 'rag' || view === 'history') {
    currentView.value = view
    nextTick(() => {
      window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
    })
    return
  }

  currentView.value = 'menu'
  nextTick(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' })
  })
}

const onMobileResult = (payload: { incidentId: string; explanation: string; steps: string[] }) => {
  incidentId.value = payload.incidentId
  predictiveSummary.value = null
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
syncUserFromToken(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY))

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
    const failureProbability = Number(data?.predictive_ai?.failure_probability ?? NaN)
    const predictedRul = Number(data?.predictive_ai?.predicted_rul_minutes ?? NaN)
    const anomalyScore = Number(data?.predictive_ai?.anomaly_score ?? NaN)
    predictiveSummary.value =
      Number.isFinite(failureProbability) && Number.isFinite(predictedRul) && Number.isFinite(anomalyScore)
        ? {
            failure_probability: Math.max(0, Math.min(1, failureProbability)),
            predicted_rul_minutes: Math.max(0, predictedRul),
            anomaly_score: Math.max(0, Math.min(1, anomalyScore)),
          }
        : null
    ragMessage.value = cleanSteps.length > 0
      ? `[분석 결과]\n${cleanExplanation}\n\n[조치 절차]\n${cleanSteps.join('\n')}`
      : `[분석 결과]\n${cleanExplanation}`
    incidentId.value = data.incident_id || null
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : '알 수 없는 오류가 발생했습니다.'
    ragMessage.value = `요청 중 오류가 발생했습니다: ${errorMessage}`
    incidentId.value = null
    predictiveSummary.value = null
  } finally {
    ragLoading.value = false
  }
}
</script>

<template>
  <MobileCaptureView v-if="isMobileCapture" :initial-code="mobileCode" />

  <LoginView v-else-if="currentView === 'login'" :login-loading="loginLoading" :message="message" @submit="onSubmit" />

  <MenuView
    v-else-if="currentView === 'menu'"
    :user-name="currentUserName"
    :user-role="currentUserRole"
    :user-avatar="currentUserAvatar"
    @navigate="navigateTo"
    @logout="onLogout"
  />

  <RagView
    v-else-if="currentView === 'rag'"
    :rag-loading="ragLoading"
    :rag-message="ragMessage"
    :incident-id="incidentId"
    :predictive-summary="predictiveSummary"
    @submit="sendRagRequest"
    @mobile-result="onMobileResult"
    @back="navigateTo('menu')"
    @logout="onLogout"
  />

  <HistoryView v-else @back="navigateTo('menu')" @logout="onLogout" />
</template>
