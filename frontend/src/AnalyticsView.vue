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
    failure_probability?: number | null
    predicted_rul_minutes?: number | null
    anomaly_score?: number | null
  }
}

type RetrainJobItem = {
  job_id: string
  model_target: string
  status: string
  created_at?: string | null
}

type AlertsSummary = {
  HIGH?: number
  CRITICAL?: number
  MEDIUM?: number
  LOW?: number
  INFO?: number
}

const emit = defineEmits<{
  back: []
}>()

const ACCESS_TOKEN_STORAGE_KEY = 'accessToken'
const TOKEN_TYPE_STORAGE_KEY = 'tokenType'
const AUTO_REFRESH_SECONDS = 30

const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const pollStamp = ref('')
const controlBusy = ref(false)
const controlMessage = ref('')

const overview = ref<Overview | null>(null)
const driftDetected = ref(false)
const alertsSummary = ref<AlertsSummary>({})
const retrainJobs = ref<RetrainJobItem[]>([])

const retrainPeriodMonths = ref(3)
const retrainTriggerReason = ref('manual')
const retrainCycleLimit = ref(3)

let refreshTimer: number | null = null

const activeModelLabel = computed(() => {
  const latest = overview.value?.latest_prediction
  const name = String(latest?.model_name || '').trim()
  const version = String(latest?.model_version || '').trim()
  const text = [name, version].filter(Boolean).join(' ')
  return text || 'lightgbm'
})

const latestStats = computed(() => {
  const latest = overview.value?.latest_prediction
  const fp = Number(latest?.failure_probability ?? 0)
  const rul = Number(latest?.predicted_rul_minutes ?? 0)
  const anomaly = Number(latest?.anomaly_score ?? 0)
  return [
    { label: '실패 확률', value: `${(fp * 100).toFixed(1)}%` },
    { label: '예측 RUL', value: `${rul.toFixed(1)} min` },
    { label: '이상 점수', value: `${(anomaly * 100).toFixed(1)}%` },
  ]
})

const topRetrainJobs = computed(() => retrainJobs.value.slice(0, 5))
const queuedJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'queued').length
)
const runningJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'running').length
)
const failedJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'failed').length
)
const completedJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'completed').length
)
const latestJobStatus = computed(() => {
  const latest = retrainJobs.value[0]
  if (!latest) return '-'
  return String(latest.status || '-')
})
const alertHighCount = computed(
  () => Number(alertsSummary.value.HIGH || 0) + Number(alertsSummary.value.CRITICAL || 0)
)
const alertMediumCount = computed(() => Number(alertsSummary.value.MEDIUM || 0))
const alertLowCount = computed(
  () => Number(alertsSummary.value.LOW || 0) + Number(alertsSummary.value.INFO || 0)
)

const hasAuthToken = () => !!localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)

const authHeaders = (): Record<string, string> => {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  const tokenType = localStorage.getItem(TOKEN_TYPE_STORAGE_KEY) || 'Bearer'
  if (!accessToken) {
    throw new Error('로그인 토큰이 없습니다. 다시 로그인해주세요.')
  }
  return { Authorization: `${tokenType} ${accessToken}` }
}

const formatDate = (value?: string | null) => {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString()
}

const statusClass = (status?: string | null) => {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'failed') return 'bad'
  if (normalized === 'queued' || normalized === 'running') return 'warn'
  return 'ok'
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
  const data = await apiGet('/api/aiops/retrain/jobs?limit=20', true)
  retrainJobs.value = Array.isArray(data?.items) ? data.items : []
}

const refreshAll = async (silent = false) => {
  if (silent) {
    refreshing.value = true
  } else {
    loading.value = true
  }
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
    const driftData = await driftRes.json()
    const alertsData = await alertsRes.json()
    driftDetected.value = !!driftData?.drift_detected
    alertsSummary.value =
      alertsData?.severity_summary && typeof alertsData.severity_summary === 'object'
        ? alertsData.severity_summary
        : {}

    await refreshRetrainJobs()
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
  <main class="analytics-shell">
    <section class="analytics-wrap">
      <nav class="analytics-nav">
        <button class="back-button" @click="emit('back')">← Dashboard</button>
        <button class="refresh-button" :disabled="refreshing" @click="refreshAll(true)">
          {{ refreshing ? '새로고침 중' : '새로고침' }}
        </button>
      </nav>

      <header class="hero-panel">
        <h1>AIOps 운영 현황</h1>
        <p class="hero-desc">서비스 신뢰성, 모델 라이프사이클, 실시간 리스크를 통합 관제합니다.</p>
        <div class="pillars">
          <span class="pillar">운영 신뢰성 모니터링</span>
          <span class="pillar">모델 성능·재학습 운영</span>
          <span class="pillar">리스크 기반 의사결정 지원</span>
        </div>
        <div class="hero-meta">
          <span>모델 {{ activeModelLabel }}</span>
          <span :class="driftDetected ? 'bad' : 'ok'">{{ driftDetected ? '드리프트 감지' : '정상' }}</span>
          <span>동기화 {{ pollStamp || '-' }}</span>
        </div>
      </header>

      <div v-if="loading" class="state-panel">불러오는 중...</div>
      <div v-else-if="error" class="state-panel error">{{ error }}</div>

      <template v-else>
        <section class="ops-grid">
          <article class="ops-card">
            <span>운영 이벤트(24h)</span>
            <strong>{{ Number(overview?.events_last_24h || 0) }}</strong>
            <small>critical {{ Number(overview?.critical_events_last_24h || 0) }}</small>
          </article>
          <article class="ops-card">
            <span>처리 지연</span>
            <strong>{{ Number(overview?.avg_incident_latency_seconds || 0).toFixed(1) }}s</strong>
            <small>fallback {{ Number(overview?.fallback_events_last_24h || 0) }}</small>
          </article>
          <article class="ops-card">
            <span>재학습 큐</span>
            <strong>{{ queuedJobCount }} / {{ runningJobCount }}</strong>
            <small>queued / running</small>
          </article>
          <article class="ops-card">
            <span>최근 재학습</span>
            <strong :class="statusClass(latestJobStatus)">{{ latestJobStatus }}</strong>
            <small>completed {{ completedJobCount }} · failed {{ failedJobCount }}</small>
          </article>
        </section>

        <section class="stats-grid">
          <h2 class="section-title">현재 샘플 위험도</h2>
          <article v-for="item in latestStats" :key="item.label" class="stat-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </article>
        </section>

        <section class="alert-strip" aria-label="Alert Summary">
          <strong>Alert Summary</strong>
          <span class="alert-pill bad">HIGH {{ alertHighCount }}</span>
          <span class="alert-pill warn">MEDIUM {{ alertMediumCount }}</span>
          <span class="alert-pill ok">LOW {{ alertLowCount }}</span>
        </section>

        <section class="panel-grid">
          <article class="panel">
            <h2>재학습 제어</h2>
            <div class="control-grid">
              <label>
                <span>Period (months)</span>
                <input v-model.number="retrainPeriodMonths" type="number" min="1" max="24" />
              </label>
              <label>
                <span>Cycle Limit</span>
                <input v-model.number="retrainCycleLimit" type="number" min="1" max="10" />
              </label>
              <label class="wide">
                <span>Trigger Reason</span>
                <input v-model="retrainTriggerReason" type="text" maxlength="255" />
              </label>
            </div>
            <div class="button-row">
              <button class="primary" :disabled="controlBusy" @click="requestRetrain">재학습 요청</button>
              <button :disabled="controlBusy" @click="runRetrainCycle">사이클 실행</button>
            </div>
            <p v-if="controlMessage" class="control-message">{{ controlMessage }}</p>
          </article>

          <article class="panel">
            <h2>최근 재학습 작업</h2>
            <ul class="job-list">
              <li v-for="job in topRetrainJobs" :key="job.job_id" class="job-item">
                <span>#{{ job.job_id }}</span>
                <span :class="statusClass(job.status)">{{ job.status }}</span>
                <span>{{ formatDate(job.created_at) }}</span>
              </li>
              <li v-if="topRetrainJobs.length === 0" class="job-empty">표시할 작업이 없습니다.</li>
            </ul>
          </article>
        </section>
      </template>
    </section>
  </main>
</template>

<style scoped>
.analytics-shell {
  min-height: 100vh;
  background: linear-gradient(180deg, #08121d 0%, #101b28 100%);
  color: #f5f7fb;
  font-family: 'IBM Plex Sans', 'Pretendard', sans-serif;
}

.analytics-wrap {
  width: min(1040px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 40px;
}

.analytics-nav {
  display: flex;
  justify-content: space-between;
  margin-bottom: 14px;
}

.back-button,
.refresh-button,
button {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(8, 16, 26, 0.72);
  color: #f7fafc;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
}

.hero-panel,
.panel,
.stat-card,
.state-panel {
  background: rgba(8, 16, 26, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
}

.hero-panel {
  padding: 16px;
  margin-bottom: 14px;
}

.hero-panel h1 {
  margin: 0;
  font-size: 26px;
}

.hero-desc {
  margin: 8px 0 0;
  color: #b7c7da;
  font-size: 14px;
}

.pillars {
  margin-top: 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.pillar {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  color: #c5d4e6;
}

.hero-meta {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #9fb3c9;
  font-size: 13px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.section-title {
  grid-column: 1 / -1;
  margin: 0 0 2px;
  font-size: 14px;
  color: #b7c7da;
  font-weight: 600;
}

.ops-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.ops-card {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(8, 16, 26, 0.62);
}

.ops-card span {
  color: #9fb3c9;
  font-size: 12px;
}

.ops-card strong {
  display: block;
  margin-top: 6px;
  font-size: 20px;
}

.ops-card small {
  display: block;
  margin-top: 4px;
  color: #8ca2ba;
  font-size: 11px;
}

.alert-strip {
  margin-bottom: 14px;
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 12px;
  background: rgba(8, 16, 26, 0.62);
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.alert-strip strong {
  font-size: 13px;
  color: #dbe5f1;
  margin-right: 2px;
}

.alert-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(255, 255, 255, 0.07);
}

.stat-card {
  padding: 12px;
}

.stat-card span {
  color: #9fb3c9;
  font-size: 12px;
}

.stat-card strong {
  display: block;
  margin-top: 6px;
  font-size: 24px;
}

.panel-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.panel {
  padding: 14px;
}

.panel h2 {
  margin: 0 0 12px;
  font-size: 17px;
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
  color: #9fb3c9;
  font-size: 12px;
}

label.wide {
  grid-column: 1 / -1;
}

input {
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(7, 14, 24, 0.8);
  color: #f5f7fb;
  border-radius: 8px;
  padding: 9px 10px;
}

.button-row {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.primary {
  border-color: rgba(59, 130, 246, 0.45);
  background: rgba(37, 99, 235, 0.24);
}

.control-message {
  margin: 10px 0 0;
  color: #bbf7d0;
  font-size: 13px;
}

.job-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}

.job-item,
.job-empty {
  display: grid;
  grid-template-columns: 0.6fr 0.8fr 1.6fr;
  gap: 8px;
  padding: 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  font-size: 13px;
}

.state-panel {
  padding: 26px;
  text-align: center;
}

.state-panel.error,
.bad {
  color: #fecaca;
}

.warn {
  color: #fde68a;
}

.ok {
  color: #bbf7d0;
}

@media (max-width: 860px) {
  .ops-grid,
  .stats-grid,
  .panel-grid,
  .control-grid,
  .job-item {
    grid-template-columns: 1fr;
  }

  .button-row {
    flex-direction: column;
  }
}
</style>
