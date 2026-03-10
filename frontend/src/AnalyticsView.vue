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

type AIOpsEventItem = {
  event_id: number
  event_type: string
  severity?: string
  service?: string | null
  stage?: string | null
  incident_id?: number | null
  device_id?: string | null
  model_name?: string | null
  status?: string | null
  message?: string | null
  created_at?: string | null
}

const emit = defineEmits<{ back: [] }>()

const ACCESS_TOKEN_STORAGE_KEY = 'accessToken'
const TOKEN_TYPE_STORAGE_KEY = 'tokenType'
const AUTO_REFRESH_SECONDS = 5

const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const pollStamp = ref('')
const releaseBusy = ref(false)
const selectedCandidateJobId = ref('')
const actionMessage = ref('')

const overview = ref<Overview | null>(null)
const drift = ref<DriftPayload>({})
const alertsSummary = ref<AlertsSummary>({})
const retrainJobs = ref<RetrainJobItem[]>([])
const deployment = ref<DeploymentState>({ status: 'ok', current: null, previous: null, history: [] })
const liveEvents = ref<AIOpsEventItem[]>([])

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
  if (normalized === 'failed' || normalized === 'critical' || normalized === 'blocked') return 'bad'
  if (normalized === 'queued' || normalized === 'running' || normalized === 'medium' || normalized === 'pending') return 'warn'
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
  const passed = typeof payload.gate_passed === 'boolean' ? payload.gate_passed : String(job.status || '').toLowerCase() === 'completed'
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

const latestEvent = computed(() => liveEvents.value[0] || null)
const deployCurrent = computed(() => (deployment.value.current && typeof deployment.value.current === 'object' ? deployment.value.current : null))
const deployPrevious = computed(() => (deployment.value.previous && typeof deployment.value.previous === 'object' ? deployment.value.previous : null))
const deploymentHistory = computed(() => (Array.isArray(deployment.value.history) ? deployment.value.history.slice(0, 6) : []))

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

const automationStages = computed(() => {
  const hasCandidate = candidateJobs.value.length > 0
  return [
    { label: '1. Predict Monitor', state: latestEvent.value ? 'active' : 'idle', text: latestEvent.value ? String(latestEvent.value.event_type || 'active') : 'waiting' },
    { label: '2. Drift Detection', state: driftDetected.value ? 'active' : 'idle', text: driftDetected.value ? 'drift detected' : 'normal' },
    { label: '3. Auto Retrain', state: queuedJobCount.value + runningJobCount.value > 0 ? 'active' : 'idle', text: queuedJobCount.value + runningJobCount.value > 0 ? `${queuedJobCount.value} queued / ${runningJobCount.value} running` : 'standby' },
    { label: '4. Candidate Ready', state: hasCandidate ? 'active' : 'idle', text: hasCandidate ? `${candidateJobs.value.length} ready` : 'not ready' },
    { label: '5. Manual Deploy', state: deployCurrent.value ? 'active' : 'idle', text: deployCurrent.value ? String(deployCurrent.value.model_version || 'active') : 'awaiting approval' },
  ]
})

const flowHeadline = computed(() => {
  if (candidateJobs.value.length > 0) return '후보 모델 준비 완료'
  if (runningJobCount.value > 0) return '자동 재학습 실행 중'
  if (queuedJobCount.value > 0) return '자동 재학습 대기 중'
  if (driftDetected.value) return '드리프트 감지'
  return '실시간 감시 정상'
})

const automationSignal = computed(() => {
  const items = [
    { label: '현재 단계', value: automationStages.value.find((item) => item.state === 'active')?.label || '1. Predict Monitor' },
    { label: '마지막 이벤트', value: String(latestEvent.value?.event_type || '-') },
    { label: '마지막 동기화', value: pollStamp.value || '-' },
  ]
  return items
})

const driftSummary = (evt: DriftEvent) => {
  const category = String(evt.category || 'unknown')
  if (category === 'data_drift') return `변화율 ${toPct(evt.delta_ratio)} / 기준 평균 ${Number(evt.baseline_mean || 0).toFixed(2)}`
  if (category === 'performance_drift') return `RMSE ${toPct(evt.recent_rmse, 2)} / 임계 ${toPct(evt.threshold, 2)}`
  if (category === 'model_drift') return `실패확률 ${toPct(evt.recent_failure_probability)} / 기준 ${toPct(evt.baseline_failure_probability)}`
  if (category === 'service_drift') return `24h ${Number(evt.recent_24h_count || 0)}건 / 일평균 ${Number(evt.baseline_daily_count || 0).toFixed(2)}건`
  return '이상 패턴 감지'
}

const apiGet = async (url: string, useAuth = false) => {
  const headers: Record<string, string> = {}
  if (useAuth) Object.assign(headers, authHeaders())
  const res = await fetch(url, { headers })
  if (!res.ok) throw new Error(`${url} 요청 실패 (${res.status})`)
  return res.json()
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

const refreshLiveEvents = async () => {
  if (!hasAuthToken()) {
    liveEvents.value = []
    return
  }
  const data = await apiGet('/api/aiops/events/recent?limit=12', true)
  liveEvents.value = Array.isArray(data?.items) ? data.items : []
}

const refreshAll = async (silent = false) => {
  if (silent) refreshing.value = true
  else loading.value = true
  error.value = ''

  try {
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

    await Promise.all([refreshRetrainJobs(), refreshDeployment(), refreshLiveEvents()])
    if (!selectedCandidateJobId.value && candidateJobs.value.length > 0) {
      const firstCandidate = candidateJobs.value[0]
      if (firstCandidate) selectedCandidateJobId.value = String(firstCandidate.job_id)
    }
    pollStamp.value = new Date().toLocaleTimeString()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'AIOps 데이터를 불러오지 못했습니다.'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

const promoteCandidate = async () => {
  if (!selectedCandidateJobId.value) {
    actionMessage.value = '배포할 후보 모델이 없습니다.'
    return
  }
  releaseBusy.value = true
  actionMessage.value = ''
  try {
    const res = await fetch(`/api/aiops/deployment/promote?job_id=${encodeURIComponent(selectedCandidateJobId.value)}`, {
      method: 'POST',
      headers: authHeaders(),
    })
    if (!res.ok) throw new Error(`배포 실패 (${res.status})`)
    actionMessage.value = '후보 모델을 프로덕션에 배포했습니다.'
    await refreshAll(true)
  } catch (err) {
    actionMessage.value = err instanceof Error ? err.message : '배포 실패'
  } finally {
    releaseBusy.value = false
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
          <span class="connection-status">AIOps Automation Monitor</span>
          <button class="report-btn" :disabled="refreshing" @click="refreshAll(true)">{{ refreshing ? 'Sync...' : 'Refresh' }}</button>
        </div>
      </nav>

      <div class="analysis-module">
        <header class="module-header">
          <div class="indicator-tag">AIOps Runtime Live</div>
          <h1 class="module-title">Predictive AI Automation Flow</h1>
          <p class="module-description">실시간 예측 결과를 감시하고, 드리프트 감지 이후 자동 재학습과 후보 생성까지 이어지는 흐름만 남긴 운영 모니터입니다.</p>
          <div class="hero-meta">
            <span>모델 {{ activeModelLabel }}</span>
            <span :class="driftDetected ? 'bad' : 'ok'">{{ driftDetected ? '드리프트 감지' : '모니터링 정상' }}</span>
            <span>동기화 {{ pollStamp || '-' }}</span>
          </div>
        </header>

        <div v-if="loading" class="state-panel">불러오는 중...</div>
        <div v-else-if="error" class="state-panel error">{{ error }}</div>

        <template v-else>
          <section class="pipeline-strip">
            <article v-for="item in automationStages" :key="item.label" class="pipeline-item" :class="item.state === 'active' ? 'active' : ''">
              <span>{{ item.label }}</span>
              <strong>{{ item.text }}</strong>
            </article>
          </section>

          <section class="spotlight-card">
            <div>
              <p class="spotlight-label">Automation Status</p>
              <h2 class="spotlight-title">{{ flowHeadline }}</h2>
            </div>
            <div class="spotlight-meta">
              <div v-for="item in automationSignal" :key="item.label" class="spotlight-pill">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
          </section>

          <section class="content-grid">
            <article class="content-card">
              <h2>Live Runtime</h2>
              <div class="state-line"><span>Refresh Interval</span><strong>5s</strong></div>
              <div class="state-line"><span>Latest Event</span><strong>{{ String(latestEvent?.event_type || '-') }}</strong></div>
              <div class="state-line"><span>Latest Status</span><strong :class="statusClass(String(latestEvent?.status || 'ok'))">{{ String(latestEvent?.status || '-') }}</strong></div>
              <div class="state-line"><span>Generated At</span><strong>{{ formatDate(latestEvent?.created_at) }}</strong></div>
            </article>

            <article class="content-card wide">
              <h2>실시간 AIOps Feed</h2>
              <div v-if="liveEvents.length === 0" class="empty">표시할 이벤트가 없습니다.</div>
              <ul v-else class="job-list">
                <li v-for="item in liveEvents" :key="item.event_id" class="job-item">
                  <div class="job-row"><strong>{{ item.event_type }}</strong><span :class="severityClass(item.severity)">{{ String(item.severity || 'INFO') }}</span><span>{{ formatDate(item.created_at) }}</span></div>
                  <div class="job-row sub"><span>service: {{ String(item.service || '-') }}</span><span>stage: {{ String(item.stage || '-') }}</span><span :class="statusClass(item.status)">{{ String(item.status || '-') }}</span></div>
                  <div class="job-row sub">
                    <span v-if="item.incident_id !== null && item.incident_id !== undefined">incident: {{ item.incident_id }}</span>
                    <span v-if="item.device_id">device: {{ String(item.device_id) }}</span>
                    <span>{{ String(item.model_name || '-') }}</span>
                  </div>
                  <p v-if="item.message" class="drift-secondary">{{ item.message }}</p>
                </li>
              </ul>
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
              <span>재학습 상태</span>
              <strong>{{ queuedJobCount }} / {{ runningJobCount }} / {{ completedJobCount }}</strong>
              <small>queued / running / completed</small>
            </article>
            <article class="kpi-card">
              <span>Alert 수준</span>
              <strong>{{ alertHighCount }} / {{ alertMediumCount }} / {{ alertLowCount }}</strong>
              <small>high / med / low</small>
            </article>
          </section>

          <section class="automation-grid">
            <article class="content-card">
              <h2>Drift Summary</h2>
              <div class="state-line"><span>감지 여부</span><strong :class="driftDetected ? 'bad' : 'ok'">{{ driftDetected ? '감지됨' : '정상' }}</strong></div>
              <div class="state-line"><span>자동 재학습 권고</span><strong :class="retrainRecommended ? 'warn' : 'ok'">{{ retrainRecommended ? '활성' : '대기' }}</strong></div>
              <div class="state-line"><span>드리프트 이벤트</span><strong>{{ driftEvents.length }}건</strong></div>
              <div class="state-line"><span>생성 시각</span><strong>{{ formatDate(drift.generated_at || null) }}</strong></div>
              <div class="event-chips">
                <span v-for="(evt, idx) in driftEvents.slice(0, 4)" :key="`${evt.category}-${evt.metric}-${idx}`" class="event-chip" :class="severityClass(evt.severity)">
                  {{ String(evt.category || 'unknown') }} · {{ String(evt.metric || '-') }}
                </span>
              </div>
            </article>

            <article class="content-card wide">
              <h2>Auto Retrain Jobs</h2>
              <div v-if="retrainJobs.length === 0" class="empty">자동 생성된 작업이 없습니다.</div>
              <ul v-else class="job-list">
                <li v-for="job in retrainJobs.slice(0, 6)" :key="job.job_id" class="job-item">
                  <div class="job-row"><strong>{{ job.job_id }}</strong><span :class="statusClass(job.status)">{{ job.status }}</span><span>{{ formatDate(job.created_at) }}</span></div>
                  <div class="job-row sub"><span>trigger: {{ String(job.trigger_reason || '-') }}</span><span>period: {{ Number(job.period_months || 0) }}m</span><span :class="statusClass(gateInfo(job).deployStatus || 'pending')">deploy: {{ gateInfo(job).deployStatus || 'pending' }}</span></div>
                  <div class="job-row sub"><span>gate: <strong :class="gateInfo(job).passed === false ? 'bad' : gateInfo(job).passed === true ? 'ok' : 'warn'">{{ gateInfo(job).passed === false ? 'blocked' : gateInfo(job).passed === true ? 'passed' : 'pending' }}</strong></span><span>RMSE: {{ toPct(gateInfo(job).gateValue, 2) }}</span><span>Threshold: {{ toPct(gateInfo(job).gateThreshold, 2) }}</span></div>
                  <p v-if="gateInfo(job).reason" class="job-reason">사유: {{ gateInfo(job).reason }}</p>
                </li>
              </ul>
            </article>
          </section>

          <section class="content-grid lower-grid">
            <article class="content-card wide">
              <h2>Detected Drift Signals</h2>
              <div v-if="driftEvents.length === 0" class="empty">현재 감지된 드리프트 신호가 없습니다.</div>
              <ul v-else class="job-list">
                <li v-for="(evt, idx) in driftEvents.slice(0, 6)" :key="`${evt.category}-${evt.metric}-${idx}`" class="job-item">
                  <div class="job-row"><strong>{{ String(evt.category || 'unknown') }}</strong><span :class="severityClass(evt.severity)">{{ String(evt.severity || 'INFO') }}</span><span>{{ String(evt.metric || '-') }}</span></div>
                  <p class="drift-secondary">{{ driftSummary(evt) }}</p>
                </li>
              </ul>
            </article>

            <article class="content-card">
              <h2>Deploy Gate</h2>
              <div class="state-line"><span>배포 후보</span><strong>{{ candidateJobs.length }}개</strong></div>
              <div class="state-line"><span>현재 배포 버전</span><strong>{{ String(deployCurrent?.model_version || '-') }}</strong></div>
              <div class="state-line"><span>이전 버전</span><strong>{{ String(deployPrevious?.model_version || '-') }}</strong></div>
              <label>
                <span>승인할 후보 모델</span>
                <select v-model="selectedCandidateJobId">
                  <option value="">선택하세요</option>
                  <option v-for="job in candidateJobs" :key="job.job_id" :value="job.job_id">{{ job.job_id }} · {{ String(job.trigger_reason || '-') }} · {{ formatDate(job.completed_at || job.created_at) }}</option>
                </select>
              </label>
              <div class="button-row">
                <button class="primary" :disabled="releaseBusy || !selectedCandidateJobId" @click="promoteCandidate">프로덕션 배포</button>
              </div>
              <p class="hint">자동화는 후보 생성까지 수행하고, 최종 배포만 운영자가 승인합니다.</p>
              <p v-if="actionMessage" class="action-message">{{ actionMessage }}</p>
            </article>
          </section>

          <section class="content-card history-card">
            <h2>최근 배포 이력</h2>
            <div v-if="deploymentHistory.length === 0" class="empty">표시할 이력이 없습니다.</div>
            <ul v-else class="history-list">
              <li v-for="(item, idx) in deploymentHistory" :key="idx" class="history-item">
                <span>{{ formatDate(item.deployed_at || item.rolled_back_at || item.created_at) }}</span>
                <strong>{{ String(item.model_version || item.event || '-') }}</strong>
                <span>{{ String(item.deployed_by || item.requested_by || '-') }}</span>
              </li>
            </ul>
          </section>
        </template>
      </div>
    </section>
  </main>
</template>

<style scoped>
.enterprise-viewport {
  position: relative;
  min-height: 100vh;
  background:
    radial-gradient(circle at 15% 10%, rgba(30, 64, 175, 0.34) 0%, transparent 28%),
    radial-gradient(circle at 85% 15%, rgba(14, 165, 233, 0.22) 0%, transparent 24%),
    linear-gradient(135deg, #07111a 0%, #0c1722 44%, #111f2b 100%);
  color: #ecf4ff;
  overflow: hidden;
  font-family: 'IBM Plex Sans', 'Pretendard', sans-serif;
}

.background-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(120deg, rgba(16, 185, 129, 0.06), rgba(59, 130, 246, 0.04));
  pointer-events: none;
}

.console-wrapper {
  position: relative;
  width: min(1180px, calc(100% - 36px));
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

button:disabled,
select:disabled {
  opacity: 0.55;
  cursor: not-allowed;
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
  border-radius: 20px;
  background: rgba(5, 11, 19, 0.74);
  backdrop-filter: blur(12px);
  padding: 20px;
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.28);
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
  font-size: 30px;
  font-weight: 700;
}

.module-description {
  margin: 0;
  color: #a8bdd3;
  font-size: 14px;
  line-height: 1.45;
  max-width: 780px;
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
  margin-bottom: 12px;
}

.pipeline-item {
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(10, 20, 32, 0.8);
  border-radius: 12px;
  padding: 12px;
}

.pipeline-item.active {
  border-color: rgba(16, 185, 129, 0.68);
  box-shadow: inset 0 0 0 1px rgba(16, 185, 129, 0.24);
  background: linear-gradient(180deg, rgba(14, 116, 144, 0.24), rgba(10, 20, 32, 0.92));
}

.pipeline-item span {
  font-size: 11px;
  color: #9db4c9;
}

.pipeline-item strong {
  display: block;
  margin-top: 6px;
  font-size: 13px;
}

.spotlight-card {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1px solid rgba(59, 130, 246, 0.26);
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(12, 74, 110, 0.38), rgba(10, 20, 32, 0.92));
}

.spotlight-label {
  margin: 0 0 6px;
  font-size: 12px;
  color: #89d5ff;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.spotlight-card h2 {
  margin: 0;
  font-size: 22px;
}

.spotlight-title {
  font-size: 7px;
  line-height: 1.35;
}

.spotlight-meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.spotlight-pill {
  min-width: 148px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.spotlight-pill span {
  display: block;
  font-size: 11px;
  color: #9db6cf;
}

.spotlight-pill strong {
  display: block;
  margin-top: 4px;
  font-size: 13px;
}

.content-grid,
.automation-grid {
  display: grid;
  grid-template-columns: 1fr 1.6fr;
  gap: 10px;
  margin-bottom: 12px;
}

.lower-grid {
  align-items: start;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
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

.content-card {
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(10, 20, 32, 0.82);
  border-radius: 14px;
  padding: 14px;
}

.content-card h2 {
  margin: 0 0 10px;
  font-size: 17px;
}

.wide {
  min-height: 280px;
}

.history-card {
  margin-top: 0;
}

.state-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #95abc1;
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

.event-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.event-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.04);
  font-size: 12px;
}

.job-item,
.history-item {
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.02);
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

.job-reason,
.drift-secondary,
.action-message {
  margin: 6px 0 0;
  font-size: 12px;
}

.job-reason,
.action-message {
  color: #fca5a5;
}

.drift-secondary {
  color: #8fa4bb;
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
  .button-row,
  .spotlight-card,
  .spotlight-meta {
    flex-direction: column;
    align-items: stretch;
  }

  .pipeline-strip,
  .kpi-grid,
  .content-grid,
  .automation-grid,
  .job-row,
  .history-item {
    grid-template-columns: 1fr;
  }
}
</style>
