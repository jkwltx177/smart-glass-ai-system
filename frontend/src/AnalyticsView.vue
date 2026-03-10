<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Overview = {
  incident_count?: number
  events_last_24h?: number
  critical_events_last_24h?: number
  fallback_events_last_24h?: number
  avg_incident_latency_seconds?: number
  latest_prediction?: {
    model_name?: string | null
    model_version?: string | null
  }
}

type DriftEvent = {
  category?: string
  metric?: string
  severity?: string
  recent_mean?: number
  baseline_mean?: number
  delta_ratio?: number
  recent_rmse?: number
  baseline_rmse?: number
  threshold?: number
  recent_failure_probability?: number
  baseline_failure_probability?: number
  recent_24h_count?: number
  baseline_daily_count?: number
}

type DriftPayload = {
  drift_detected?: boolean
  retrain_recommended?: boolean
  generated_at?: string
  events?: DriftEvent[]
}

type RetrainJobItem = {
  job_id: string
  model_target: string
  status: string
  trigger_reason?: string
  period_months?: number
  created_at?: string | null
  completed_at?: string | null
  payload?: Record<string, unknown>
}

type DeploymentState = {
  status?: string
  current?: Record<string, unknown> | null
  previous?: Record<string, unknown> | null
  history?: Array<Record<string, unknown>>
}

type AlertsSummary = {
  HIGH?: number
  CRITICAL?: number
  MEDIUM?: number
  LOW?: number
  INFO?: number
}

const emit = defineEmits<{ back: [] }>()

const ACCESS_TOKEN_STORAGE_KEY = 'accessToken'
const TOKEN_TYPE_STORAGE_KEY = 'tokenType'
const AUTO_REFRESH_SECONDS = 30

const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const pollStamp = ref('')
const controlBusy = ref(false)
const releaseBusy = ref(false)
const pdfBusy = ref(false)
const controlMessage = ref('')
const activeTab = ref<'drift' | 'retrain' | 'release'>('drift')
const selectedCandidateJobId = ref('')

const overview = ref<Overview | null>(null)
const drift = ref<DriftPayload>({})
const alertsSummary = ref<AlertsSummary>({})
const retrainJobs = ref<RetrainJobItem[]>([])
const deployment = ref<DeploymentState>({ status: 'ok', current: null, previous: null, history: [] })

const retrainPeriodMonths = ref(3)
const retrainTriggerReason = ref('manual')
const retrainCycleLimit = ref(3)

let refreshTimer: number | null = null

const hasAuthToken = () => !!localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)

const authHeaders = (): Record<string, string> => {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  const tokenType = localStorage.getItem(TOKEN_TYPE_STORAGE_KEY) || 'Bearer'
  if (!accessToken) throw new Error('로그인 토큰이 없습니다. 다시 로그인해주세요.')
  return { Authorization: `${tokenType} ${accessToken}` }
}

const formatDate = (value?: unknown) => {
  const text = String(value ?? '').trim()
  if (!text) return '-'
  const dt = new Date(text)
  if (Number.isNaN(dt.getTime())) return text
  return dt.toLocaleString()
}

const toPct = (value: unknown, digits = 1) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return '-'
  return `${(n * 100).toFixed(digits)}%`
}

const statusClass = (status?: string | null) => {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'failed' || normalized === 'critical') return 'bad'
  if (normalized === 'queued' || normalized === 'running' || normalized === 'medium') return 'warn'
  return 'ok'
}

const severityClass = (severity?: string | null) => {
  const normalized = String(severity || '').toUpperCase()
  if (normalized === 'HIGH' || normalized === 'CRITICAL') return 'bad'
  if (normalized === 'MEDIUM') return 'warn'
  return 'ok'
}

const activeModelLabel = computed(() => {
  const latest = overview.value?.latest_prediction
  return [String(latest?.model_name || '').trim(), String(latest?.model_version || '').trim()].filter(Boolean).join(' ') || 'lightgbm'
})

const driftDetected = computed(() => !!drift.value?.drift_detected)
const retrainRecommended = computed(() => !!drift.value?.retrain_recommended)
const driftEvents = computed(() => (Array.isArray(drift.value?.events) ? drift.value.events : []))

const gateInfo = (job: RetrainJobItem) => {
  const payload = (job.payload || {}) as Record<string, unknown>
  const metrics = payload.metrics as Record<string, unknown> | undefined
  const passed =
    typeof payload.gate_passed === 'boolean'
      ? payload.gate_passed
      : String(job.status || '').toLowerCase() === 'completed'
        ? true
        : null

  const gateValue =
    typeof payload.gate_value === 'number'
      ? payload.gate_value
      : typeof metrics?.valid_rmse_failure === 'number'
        ? Number(metrics.valid_rmse_failure)
        : null

  const gateThreshold =
    typeof payload.gate_threshold === 'number'
      ? payload.gate_threshold
      : typeof metrics?.rmse_threshold === 'number'
        ? Number(metrics.rmse_threshold)
        : null

  const deployStatus = String(payload.deployment_status || '').toLowerCase()
  const reason = String(payload.reason || payload.error || '').trim()
  return { passed, gateValue, gateThreshold, deployStatus, reason }
}

const queuedJobCount = computed(() => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'queued').length)
const runningJobCount = computed(() => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'running').length)
const failedJobCount = computed(() => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'failed').length)
const completedJobCount = computed(() => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'completed').length)

const alertHighCount = computed(() => Number(alertsSummary.value.HIGH || 0) + Number(alertsSummary.value.CRITICAL || 0))
const alertMediumCount = computed(() => Number(alertsSummary.value.MEDIUM || 0))
const alertLowCount = computed(() => Number(alertsSummary.value.LOW || 0) + Number(alertsSummary.value.INFO || 0))

const deployCurrent = computed(() => (deployment.value.current && typeof deployment.value.current === 'object' ? deployment.value.current : null))
const deployPrevious = computed(() => (deployment.value.previous && typeof deployment.value.previous === 'object' ? deployment.value.previous : null))
const deploymentHistory = computed(() => (Array.isArray(deployment.value.history) ? deployment.value.history.slice(0, 8) : []))

const candidateJobs = computed(() => {
  return retrainJobs.value.filter((job) => {
    const status = String(job.status || '').toLowerCase()
    const gate = gateInfo(job)
    if (status !== 'completed') return false
    if (gate.passed === false) return false
    if (gate.deployStatus === 'deployed') return false
    return true
  })
})

const stageCards = computed(() => {
  const current = deployCurrent.value
  const hasCandidate = candidateJobs.value.length > 0
  return [
    { label: 'Drift Detection', state: driftDetected.value ? 'active' : 'idle', text: driftDetected.value ? '감지됨' : '정상' },
    { label: 'Retrain Queue', state: queuedJobCount.value + runningJobCount.value > 0 ? 'active' : 'idle', text: `${queuedJobCount.value} queued / ${runningJobCount.value} running` },
    { label: 'Candidate Ready', state: hasCandidate ? 'active' : 'idle', text: hasCandidate ? `${candidateJobs.value.length}개 준비` : '없음' },
    { label: 'Production Deploy', state: current ? 'active' : 'idle', text: current ? String(current.model_version || '-') : '미배포' },
    { label: 'Rollback Safety', state: deployPrevious.value ? 'active' : 'idle', text: deployPrevious.value ? '이전 버전 보관' : '이전 버전 없음' },
  ]
})

const driftCards = computed(() => {
  return driftEvents.value.slice(0, 8).map((evt) => {
    const category = String(evt.category || 'unknown')
    const metric = String(evt.metric || '-')
    if (category === 'data_drift') {
      return {
        title: 'Data Shift',
        subtitle: metric,
        primary: `변화율 ${toPct(evt.delta_ratio)}`,
        secondary: `최근 ${Number(evt.recent_mean || 0).toFixed(2)} / 기준 ${Number(evt.baseline_mean || 0).toFixed(2)}`,
        severity: String(evt.severity || 'MEDIUM'),
      }
    }
    if (category === 'performance_drift') {
      return {
        title: 'RMSE Drift',
        subtitle: 'failure_probability',
        primary: `RMSE ${toPct(evt.recent_rmse, 2)}`,
        secondary: `기준 ${toPct(evt.baseline_rmse, 2)} · 임계 ${toPct(evt.threshold, 2)}`,
        severity: String(evt.severity || 'MEDIUM'),
      }
    }
    if (category === 'model_drift') {
      return {
        title: 'Prediction Shift',
        subtitle: metric,
        primary: `실패확률 ${toPct(evt.recent_failure_probability)} / ${toPct(evt.baseline_failure_probability)}`,
        secondary: '예측 분포 이동 감지',
        severity: String(evt.severity || 'MEDIUM'),
      }
    }
    if (category === 'service_drift') {
      return {
        title: 'Service Drift',
        subtitle: 'fallback_rate',
        primary: `24h ${Number(evt.recent_24h_count || 0)}건`,
        secondary: `기준 일평균 ${Number(evt.baseline_daily_count || 0).toFixed(2)}건`,
        severity: String(evt.severity || 'MEDIUM'),
      }
    }
    return {
      title: 'Drift Event',
      subtitle: `${category} · ${metric}`,
      primary: '이상 패턴 감지',
      secondary: '상세는 PDF 리포트 참고',
      severity: String(evt.severity || 'LOW'),
    }
  })
})

const apiGet = async (url: string, useAuth = false) => {
  const headers: Record<string, string> = {}
  if (useAuth) Object.assign(headers, authHeaders())
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`${url} 요청 실패 (${res.status})`)
  return res.json()
}

const runDriftCycle = async (silent = true) => {
  if (!hasAuthToken()) return
  try {
    const res = await fetch('/api/aiops/runtime/drift-cycle', { method: 'POST', headers: authHeaders() })
    if (!silent && !res.ok) throw new Error(`드리프트 사이클 실행 실패 (${res.status})`)
  } catch (err) {
    if (!silent) controlMessage.value = err instanceof Error ? err.message : '드리프트 사이클 실행 실패'
  }
}

const refreshRetrainJobs = async () => {
  if (!hasAuthToken()) {
    retrainJobs.value = []
    return
  }
  const data = await apiGet('/api/aiops/retrain/jobs?limit=30', true)
  retrainJobs.value = Array.isArray(data?.items) ? data.items : []
}

const refreshDeployment = async () => {
  if (!hasAuthToken()) {
    deployment.value = { status: 'ok', current: null, previous: null, history: [] }
    return
  }
  const data = await apiGet('/api/aiops/deployment', true)
  deployment.value = {
    status: String(data?.status || 'ok'),
    current: data?.current ?? null,
    previous: data?.previous ?? null,
    history: Array.isArray(data?.history) ? data.history : [],
  }
}

const refreshAll = async (silent = false) => {
  if (silent) refreshing.value = true
  else loading.value = true
  error.value = ''

  try {
    await runDriftCycle(true)

    const [overviewRes, driftRes, alertsRes] = await Promise.all([
      fetch('/api/aiops/overview'),
      fetch('/api/aiops/drift'),
      fetch('/api/aiops/alerts?limit=1'),
    ])
    if (!overviewRes.ok || !driftRes.ok || !alertsRes.ok) {
      throw new Error(`AIOps 데이터 조회 실패 (${overviewRes.status}/${driftRes.status}/${alertsRes.status})`)
    }

    overview.value = await overviewRes.json()
    drift.value = await driftRes.json()
    const alertsData = await alertsRes.json()
    alertsSummary.value = alertsData?.severity_summary && typeof alertsData.severity_summary === 'object' ? alertsData.severity_summary : {}

    await Promise.all([refreshRetrainJobs(), refreshDeployment()])
    if (!selectedCandidateJobId.value && candidateJobs.value.length > 0) {
      const firstCandidate = candidateJobs.value[0]
      if (firstCandidate) {
        selectedCandidateJobId.value = String(firstCandidate.job_id)
      }
    }
    pollStamp.value = new Date().toLocaleTimeString()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'AIOps 데이터를 불러오지 못했습니다.'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

const requestRetrain = async () => {
  controlBusy.value = true
  controlMessage.value = ''
  try {
    const payload = {
      period_months: Math.max(1, Math.min(24, Number(retrainPeriodMonths.value || 1))),
      model_target: 'prediction',
      trigger_reason: String(retrainTriggerReason.value || 'manual').slice(0, 255),
    }
    const res = await fetch('/api/aiops/retrain', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
    })
    if (!res.ok) throw new Error(`재학습 요청 실패 (${res.status})`)
    const data = await res.json()
    controlMessage.value = `재학습 요청 등록: ${String(data?.job_id || '-')}`
    await refreshAll(true)
  } catch (err) {
    controlMessage.value = err instanceof Error ? err.message : '재학습 요청 실패'
  } finally {
    controlBusy.value = false
  }
}

const runRetrainCycle = async () => {
  controlBusy.value = true
  controlMessage.value = ''
  try {
    const limit = Math.max(1, Math.min(10, Number(retrainCycleLimit.value || 1)))
    const res = await fetch(`/api/aiops/runtime/retrain-cycle?limit=${limit}`, {
      method: 'POST',
      headers: authHeaders(),
    })
    if (!res.ok) throw new Error(`재학습 사이클 실행 실패 (${res.status})`)
    const data = await res.json()
    controlMessage.value = `사이클 완료: ${Number(data?.processed_jobs || 0)}건`
    await refreshAll(true)
  } catch (err) {
    controlMessage.value = err instanceof Error ? err.message : '재학습 사이클 실행 실패'
  } finally {
    controlBusy.value = false
  }
}

const promoteCandidate = async () => {
  if (!selectedCandidateJobId.value) {
    controlMessage.value = '배포할 후보 모델을 선택하세요.'
    return
  }
  releaseBusy.value = true
  controlMessage.value = ''
  try {
    const res = await fetch(`/api/aiops/deployment/promote?job_id=${encodeURIComponent(selectedCandidateJobId.value)}`, {
      method: 'POST',
      headers: authHeaders(),
    })
    if (!res.ok) throw new Error(`배포 실패 (${res.status})`)
    controlMessage.value = '후보 모델을 프로덕션으로 배포했습니다.'
    await refreshAll(true)
  } catch (err) {
    controlMessage.value = err instanceof Error ? err.message : '배포 실패'
  } finally {
    releaseBusy.value = false
  }
}

const rollbackDeployment = async () => {
  releaseBusy.value = true
  controlMessage.value = ''
  try {
    const res = await fetch('/api/aiops/deployment/rollback', {
      method: 'POST',
      headers: authHeaders(),
    })
    if (!res.ok) throw new Error(`롤백 실패 (${res.status})`)
    controlMessage.value = '이전 모델로 롤백을 완료했습니다.'
    await refreshAll(true)
  } catch (err) {
    controlMessage.value = err instanceof Error ? err.message : '롤백 실패'
  } finally {
    releaseBusy.value = false
  }
}

const runDriftCycleNow = async () => {
  controlBusy.value = true
  controlMessage.value = ''
  try {
    await runDriftCycle(false)
    controlMessage.value = '드리프트 점검 사이클을 실행했습니다.'
    await refreshAll(true)
  } finally {
    controlBusy.value = false
  }
}

const generatePdfReport = async () => {
  if (!hasAuthToken()) {
    controlMessage.value = 'PDF 출력은 로그인 후 가능합니다.'
    return
  }
  pdfBusy.value = true
  controlMessage.value = ''
  try {
    const res = await fetch('/api/aiops/report', { method: 'POST', headers: authHeaders() })
    if (!res.ok) throw new Error(`PDF 생성 실패 (${res.status})`)
    const data = await res.json()
    const reportUrl = String(data?.report_url || '').trim()
    if (!reportUrl) throw new Error('PDF URL이 비어 있습니다.')
    window.open(reportUrl, '_blank')
    controlMessage.value = 'AIOps PDF 리포트를 생성했습니다.'
  } catch (err) {
    controlMessage.value = err instanceof Error ? err.message : 'PDF 생성 실패'
  } finally {
    pdfBusy.value = false
  }
}

onMounted(() => {
  refreshAll()
  refreshTimer = window.setInterval(() => refreshAll(true), AUTO_REFRESH_SECONDS * 1000)
})

onUnmounted(() => {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
})
</script>

<template>
  <main class="enterprise-viewport">
    <div class="background-overlay"></div>

    <section class="console-wrapper">
      <nav class="utility-bar">
        <button class="nav-action-btn" @click="emit('back')">Back to Dashboard</button>
        <div class="system-meta">
          <span class="connection-status">AIOps Release Console</span>
          <button class="report-btn" :disabled="pdfBusy" @click="generatePdfReport">{{ pdfBusy ? 'Generating...' : 'Export PDF' }}</button>
          <button class="report-btn" :disabled="refreshing" @click="refreshAll(true)">{{ refreshing ? 'Sync...' : 'Refresh' }}</button>
        </div>
      </nav>

      <div class="analysis-module">
        <header class="module-header">
          <div class="indicator-tag">AIOps Runtime v3.0</div>
          <h1 class="module-title">Drift to Deploy Pipeline</h1>
          <p class="module-description">드리프트 감지 후 재학습 후보를 만들고, 배포/롤백을 운영자가 통제하는 릴리즈 흐름입니다.</p>
          <div class="hero-meta">
            <span>모델 {{ activeModelLabel }}</span>
            <span :class="driftDetected ? 'bad' : 'ok'">{{ driftDetected ? '드리프트 감지' : '정상' }}</span>
            <span>동기화 {{ pollStamp || '-' }}</span>
          </div>
        </header>

        <div v-if="loading" class="state-panel">불러오는 중...</div>
        <div v-else-if="error" class="state-panel error">{{ error }}</div>

        <template v-else>
          <section class="pipeline-strip">
            <article v-for="item in stageCards" :key="item.label" class="pipeline-item" :class="item.state === 'active' ? 'active' : ''">
              <span>{{ item.label }}</span>
              <strong>{{ item.text }}</strong>
            </article>
          </section>

          <section class="kpi-grid">
            <article class="kpi-card">
              <span>운영 이벤트 (24h)</span>
              <strong>{{ Number(overview?.events_last_24h || 0) }}</strong>
              <small>critical {{ Number(overview?.critical_events_last_24h || 0) }}</small>
            </article>
            <article class="kpi-card">
              <span>평균 처리 지연</span>
              <strong>{{ Number(overview?.avg_incident_latency_seconds || 0).toFixed(1) }}s</strong>
              <small>fallback {{ Number(overview?.fallback_events_last_24h || 0) }}</small>
            </article>
            <article class="kpi-card">
              <span>재학습 큐</span>
              <strong>{{ queuedJobCount }} / {{ runningJobCount }}</strong>
              <small>queued / running</small>
            </article>
            <article class="kpi-card">
              <span>Alert 수준</span>
              <strong>{{ alertHighCount }} / {{ alertMediumCount }} / {{ alertLowCount }}</strong>
              <small>high / med / low</small>
            </article>
          </section>

          <section class="tab-switcher">
            <button :class="['tab-btn', activeTab === 'drift' ? 'active' : '']" @click="activeTab = 'drift'">모델 드리프트</button>
            <button :class="['tab-btn', activeTab === 'retrain' ? 'active' : '']" @click="activeTab = 'retrain'">재학습</button>
            <button :class="['tab-btn', activeTab === 'release' ? 'active' : '']" @click="activeTab = 'release'">배포 · 롤백</button>
          </section>

          <section v-if="activeTab === 'drift'" class="content-grid">
            <article class="content-card">
              <h2>Drift 상태</h2>
              <div class="state-line"><span>감지 여부</span><strong :class="driftDetected ? 'bad' : 'ok'">{{ driftDetected ? '감지됨' : '정상' }}</strong></div>
              <div class="state-line"><span>재학습 권고</span><strong :class="retrainRecommended ? 'warn' : 'ok'">{{ retrainRecommended ? '권고됨' : '없음' }}</strong></div>
              <div class="state-line"><span>이벤트 수</span><strong>{{ driftEvents.length }}건</strong></div>
              <div class="state-line"><span>생성 시각</span><strong>{{ formatDate(drift.generated_at || null) }}</strong></div>
              <div class="button-row"><button :disabled="controlBusy || !hasAuthToken()" @click="runDriftCycleNow">드리프트 점검 실행</button></div>
            </article>

            <article class="content-card wide">
              <h2>Drift 이벤트 요약</h2>
              <div v-if="driftCards.length === 0" class="empty">감지된 이벤트가 없습니다.</div>
              <div v-else class="drift-card-grid">
                <div v-for="(card, idx) in driftCards" :key="`${card.title}-${idx}`" class="drift-card">
                  <div class="drift-head"><strong>{{ card.title }}</strong><span :class="severityClass(card.severity)">{{ card.severity }}</span></div>
                  <p class="drift-sub">{{ card.subtitle }}</p>
                  <p class="drift-primary">{{ card.primary }}</p>
                  <p class="drift-secondary">{{ card.secondary }}</p>
                </div>
              </div>
            </article>
          </section>

          <section v-else-if="activeTab === 'retrain'" class="content-grid">
            <article class="content-card">
              <h2>재학습 제어</h2>
              <div class="control-grid">
                <label><span>Period (months)</span><input v-model.number="retrainPeriodMonths" type="number" min="1" max="24" /></label>
                <label><span>Cycle Limit</span><input v-model.number="retrainCycleLimit" type="number" min="1" max="10" /></label>
                <label class="wide-input"><span>Trigger Reason</span><input v-model="retrainTriggerReason" type="text" maxlength="255" /></label>
              </div>
              <div class="button-row">
                <button class="primary" :disabled="controlBusy" @click="requestRetrain">재학습 요청</button>
                <button :disabled="controlBusy" @click="runRetrainCycle">사이클 실행</button>
              </div>
              <p v-if="controlMessage" class="control-message">{{ controlMessage }}</p>
            </article>

            <article class="content-card wide">
              <h2>최근 재학습 작업</h2>
              <div v-if="retrainJobs.length === 0" class="empty">표시할 작업이 없습니다.</div>
              <ul v-else class="job-list">
                <li v-for="job in retrainJobs.slice(0, 10)" :key="job.job_id" class="job-item">
                  <div class="job-row"><strong>{{ job.job_id }}</strong><span :class="statusClass(job.status)">{{ job.status }}</span><span>{{ formatDate(job.created_at) }}</span></div>
                  <div class="job-row sub"><span>trigger: {{ String(job.trigger_reason || '-') }}</span><span>period: {{ Number(job.period_months || 0) }}m</span><span :class="statusClass(gateInfo(job).deployStatus || 'idle')">deploy: {{ gateInfo(job).deployStatus || 'pending' }}</span></div>
                  <div class="job-row sub"><span>gate: <strong :class="gateInfo(job).passed === false ? 'bad' : gateInfo(job).passed === true ? 'ok' : 'warn'">{{ gateInfo(job).passed === false ? 'blocked' : gateInfo(job).passed === true ? 'passed' : 'pending' }}</strong></span><span>RMSE: {{ toPct(gateInfo(job).gateValue, 2) }}</span><span>Threshold: {{ toPct(gateInfo(job).gateThreshold, 2) }}</span></div>
                  <p v-if="gateInfo(job).reason" class="job-reason">사유: {{ gateInfo(job).reason }}</p>
                </li>
              </ul>
            </article>
          </section>

          <section v-else class="release-grid">
            <article class="content-card">
              <h2>프로덕션 배포</h2>
              <label>
                <span>후보 모델 선택 (게이트 통과)</span>
                <select v-model="selectedCandidateJobId">
                  <option value="">선택하세요</option>
                  <option v-for="job in candidateJobs" :key="job.job_id" :value="job.job_id">{{ job.job_id }} · {{ String(job.trigger_reason || '-') }} · {{ formatDate(job.completed_at || job.created_at) }}</option>
                </select>
              </label>
              <div class="button-row">
                <button class="primary" :disabled="releaseBusy || !selectedCandidateJobId" @click="promoteCandidate">프로덕션 배포</button>
              </div>
              <p class="hint">배포 시 현재 모델 스냅샷이 자동 보관되어 롤백에 사용됩니다.</p>
            </article>

            <article class="content-card">
              <h2>롤백</h2>
              <div class="state-line"><span>현재 배포 버전</span><strong>{{ String(deployCurrent?.model_version || '-') }}</strong></div>
              <div class="state-line"><span>이전 배포 버전</span><strong>{{ String(deployPrevious?.model_version || '-') }}</strong></div>
              <div class="button-row"><button :disabled="releaseBusy || !deployPrevious" @click="rollbackDeployment">이전 버전으로 롤백</button></div>
              <p class="hint">롤백은 최근 배포 직전 스냅샷 기준으로 복구됩니다.</p>
            </article>

            <article class="content-card wide full-row">
              <h2>배포 이력</h2>
              <div v-if="deploymentHistory.length === 0" class="empty">표시할 이력이 없습니다.</div>
              <ul v-else class="history-list">
                <li v-for="(item, idx) in deploymentHistory" :key="idx" class="history-item">
                  <span>{{ formatDate(item.deployed_at || item.rolled_back_at || item.created_at) }}</span>
                  <strong>{{ String(item.model_version || item.event || '-') }}</strong>
                  <span>{{ String(item.deployed_by || item.requested_by || '-') }}</span>
                </li>
              </ul>
            </article>
          </section>

          <p v-if="controlMessage" class="control-message global-msg">{{ controlMessage }}</p>
        </template>
      </div>
    </section>
  </main>
</template>

<style scoped>
.enterprise-viewport {
  position: relative;
  min-height: 100vh;
  background: radial-gradient(circle at 15% 10%, #1f3f55 0%, #0d1824 40%, #090f18 100%);
  color: #ecf4ff;
  overflow: hidden;
  font-family: 'IBM Plex Sans', 'Pretendard', sans-serif;
}

.background-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, rgba(16, 185, 129, 0.07), rgba(56, 189, 248, 0.05));
  pointer-events: none;
}

.console-wrapper {
  position: relative;
  width: min(1160px, calc(100% - 36px));
  margin: 0 auto;
  padding: 28px 0 40px;
}

.utility-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.nav-action-btn,
.report-btn,
button,
select {
  border: 1px solid rgba(148, 163, 184, 0.25);
  background: rgba(7, 15, 24, 0.76);
  color: #e7f1ff;
  border-radius: 10px;
  padding: 10px 14px;
  cursor: pointer;
}

select {
  width: 100%;
}

.system-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.connection-status {
  font-size: 12px;
  color: #9db6cf;
}

.analysis-module {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 18px;
  background: rgba(5, 11, 19, 0.72);
  backdrop-filter: blur(12px);
  padding: 18px;
}

.module-header {
  margin-bottom: 14px;
}

.indicator-tag {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(45, 212, 191, 0.45);
  color: #7deed9;
  font-size: 11px;
  letter-spacing: 0.04em;
}

.module-title {
  margin: 10px 0 6px;
  font-size: 28px;
  font-weight: 700;
}

.module-description {
  margin: 0;
  color: #a8bdd3;
  font-size: 14px;
  line-height: 1.45;
}

.hero-meta {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
  color: #95acc2;
}

.pipeline-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 10px;
}

.pipeline-item {
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(10, 20, 32, 0.8);
  border-radius: 10px;
  padding: 10px;
}

.pipeline-item.active {
  border-color: rgba(16, 185, 129, 0.65);
  box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.24);
}

.pipeline-item span {
  font-size: 11px;
  color: #9db4c9;
}

.pipeline-item strong {
  display: block;
  margin-top: 4px;
  font-size: 13px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.kpi-card {
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(9, 19, 30, 0.8);
  border-radius: 12px;
  padding: 12px;
}

.kpi-card span {
  font-size: 12px;
  color: #9cb2c8;
}

.kpi-card strong {
  display: block;
  margin-top: 6px;
  font-size: 21px;
}

.kpi-card small {
  display: block;
  margin-top: 4px;
  color: #88a0b9;
}

.tab-switcher {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.tab-btn.active {
  border-color: rgba(45, 212, 191, 0.55);
  background: rgba(17, 94, 89, 0.35);
}

.content-grid {
  display: grid;
  grid-template-columns: 1fr 1.6fr;
  gap: 10px;
}

.release-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.full-row {
  grid-column: 1 / -1;
}

.content-card {
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(10, 20, 32, 0.82);
  border-radius: 12px;
  padding: 14px;
}

.content-card h2 {
  margin: 0 0 10px;
  font-size: 17px;
}

.wide {
  min-height: 280px;
}

.state-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.control-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #95abc1;
}

input {
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 8px;
  background: rgba(6, 13, 21, 0.92);
  color: #ebf5ff;
  padding: 9px 10px;
}

.wide-input {
  grid-column: 1 / -1;
}

.button-row {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.primary {
  border-color: rgba(14, 165, 233, 0.5);
  background: rgba(2, 132, 199, 0.3);
}

.hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #8aa0b6;
}

.drift-card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.drift-card,
.job-item,
.history-item {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.02);
}

.drift-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.drift-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: #9ab0c7;
}

.drift-primary {
  margin: 6px 0 0;
  font-size: 14px;
}

.drift-secondary {
  margin: 4px 0 0;
  font-size: 12px;
  color: #8fa4bb;
}

.job-list,
.history-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.job-row,
.history-item {
  display: grid;
  grid-template-columns: 1fr 0.8fr 1fr;
  gap: 8px;
  align-items: center;
}

.job-row.sub {
  margin-top: 4px;
  font-size: 12px;
  color: #9ab0c7;
}

.job-reason {
  margin: 6px 0 0;
  font-size: 12px;
  color: #fca5a5;
}

.state-panel {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  background: rgba(10, 20, 32, 0.82);
  padding: 26px;
  text-align: center;
}

.empty {
  font-size: 13px;
  color: #9ab0c7;
}

.global-msg {
  margin-top: 10px;
}

.ok {
  color: #86efac;
}

.warn {
  color: #fde68a;
}

.bad {
  color: #fca5a5;
}

@media (max-width: 980px) {
  .utility-bar,
  .system-meta,
  .button-row {
    flex-direction: column;
    align-items: stretch;
  }

  .pipeline-strip,
  .kpi-grid,
  .content-grid,
  .release-grid,
  .control-grid,
  .drift-card-grid,
  .job-row,
  .history-item {
    grid-template-columns: 1fr;
  }
}
</style>
