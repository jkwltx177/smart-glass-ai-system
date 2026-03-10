<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type Overview = {
  generated_at: string
  incident_count: number
  completed_incident_count: number
  failed_incident_count: number
  prediction_count: number
  avg_incident_latency_seconds: number
  events_last_24h: number
  critical_events_last_24h: number
  fallback_events_last_24h: number
  latest_prediction: {
    model_name?: string | null
    model_version?: string | null
    failure_probability?: number | null
    predicted_rul_minutes?: number | null
    anomaly_score?: number | null
  }
}

type AlertItem = {
  type: string
  severity: string
  title: string
  service?: string | null
  stage?: string | null
  incident_id?: number | null
  device_id?: string | null
  status?: string | null
  message?: string | null
  created_at?: string | null
}

type DriftEvent = {
  category: string
  metric: string
  severity: string
  [key: string]: unknown
}

type ModelItem = {
  name: string
  version: string
  prediction_count: number
  last_used_at?: string | null
  status: string
}

const emit = defineEmits<{
  back: []
}>()

const loading = ref(true)
const refreshing = ref(false)
const error = ref('')
const overview = ref<Overview | null>(null)
const alerts = ref<AlertItem[]>([])
const severitySummary = ref<Record<string, number>>({})
const driftDetected = ref(false)
const driftEvents = ref<DriftEvent[]>([])
const models = ref<ModelItem[]>([])
const pollStamp = ref('')
let refreshTimer: number | null = null

const summaryCards = computed(() => {
  const data = overview.value
  if (!data) return []
  return [
    {
      key: 'incidents',
      label: '총 Incident',
      value: String(data.incident_count),
      tone: 'cyan',
    },
    {
      key: 'events',
      label: '24시간 이벤트',
      value: String(data.events_last_24h),
      tone: 'amber',
    },
    {
      key: 'critical',
      label: 'Critical Event',
      value: String(data.critical_events_last_24h),
      tone: 'red',
    },
    {
      key: 'latency',
      label: '평균 처리 지연',
      value: `${Number(data.avg_incident_latency_seconds || 0).toFixed(1)}s`,
      tone: 'mint',
    },
  ]
})

const latestPredictionStats = computed(() => {
  const latest = overview.value?.latest_prediction
  if (!latest) return []
  const fp = Number(latest.failure_probability ?? 0)
  const rul = Number(latest.predicted_rul_minutes ?? 0)
  const anomaly = Number(latest.anomaly_score ?? 0)
  return [
    { label: '실패 확률', value: `${(fp * 100).toFixed(1)}%` },
    { label: '예측 RUL', value: `${rul.toFixed(1)} min` },
    { label: '이상 점수', value: `${(anomaly * 100).toFixed(1)}%` },
  ]
})

const topAlerts = computed(() => alerts.value.slice(0, 8))
const topModels = computed(() => models.value.slice(0, 6))

const formatDate = (value?: string | null) => {
  if (!value) return '-'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return value
  return dt.toLocaleString()
}

const severityClass = (severity?: string | null) => {
  const normalized = String(severity || '').toLowerCase()
  if (normalized === 'high' || normalized === 'critical') return 'sev-high'
  if (normalized === 'medium') return 'sev-medium'
  return 'sev-low'
}

const refreshAll = async (silent = false) => {
  if (silent) {
    refreshing.value = true
  } else {
    loading.value = true
  }
  error.value = ''
  try {
    const [overviewRes, alertsRes, driftRes, modelsRes] = await Promise.all([
      fetch('/api/aiops/overview'),
      fetch('/api/aiops/alerts?limit=20'),
      fetch('/api/aiops/drift'),
      fetch('/api/aiops/models'),
    ])

    if (!overviewRes.ok || !alertsRes.ok || !driftRes.ok || !modelsRes.ok) {
      throw new Error(
        `AIOps 데이터 조회 실패 (${[
          overviewRes.status,
          alertsRes.status,
          driftRes.status,
          modelsRes.status,
        ].join('/')})`
      )
    }

    const overviewData = await overviewRes.json()
    const alertsData = await alertsRes.json()
    const driftData = await driftRes.json()
    const modelsData = await modelsRes.json()

    overview.value = overviewData
    alerts.value = Array.isArray(alertsData?.items) ? alertsData.items : []
    severitySummary.value =
      alertsData?.severity_summary && typeof alertsData.severity_summary === 'object'
        ? alertsData.severity_summary
        : {}
    driftDetected.value = !!driftData?.drift_detected
    driftEvents.value = Array.isArray(driftData?.events) ? driftData.events : []
    models.value = Array.isArray(modelsData?.items) ? modelsData.items : []
    pollStamp.value = new Date().toLocaleTimeString()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'AIOps 데이터를 불러오지 못했습니다.'
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

onMounted(() => {
  refreshAll()
  refreshTimer = window.setInterval(() => {
    refreshAll(true)
  }, 30000)
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
    <div class="analytics-backdrop"></div>

    <section class="analytics-wrap">
      <nav class="analytics-nav">
        <button class="back-button" @click="emit('back')">← Dashboard</button>
        <div class="nav-meta">
          <span class="nav-chip">AIOPS CONSOLE</span>
          <button class="refresh-button" :disabled="refreshing" @click="refreshAll(true)">
            {{ refreshing ? '새로고침 중' : '새로고침' }}
          </button>
        </div>
      </nav>

      <header class="hero-panel">
        <div class="hero-copy">
          <p class="eyebrow">Runtime Intelligence</p>
          <h1>AIOps 운영 현황</h1>
          <p class="hero-desc">
            파이프라인 이벤트, 예측 리스크, 드리프트 징후를 한 화면에서 모니터링합니다.
          </p>
        </div>
        <div class="hero-status">
          <div class="status-card">
            <span class="status-label">드리프트 상태</span>
            <strong :class="driftDetected ? 'sev-high' : 'sev-low'">
              {{ driftDetected ? '주의 필요' : '안정' }}
            </strong>
          </div>
          <div class="status-card">
            <span class="status-label">최근 동기화</span>
            <strong>{{ pollStamp || '-' }}</strong>
          </div>
        </div>
      </header>

      <div v-if="loading" class="state-panel">AIOps 데이터를 불러오는 중입니다.</div>
      <div v-else-if="error" class="state-panel error">{{ error }}</div>
      <template v-else>
        <section class="summary-grid">
          <article
            v-for="card in summaryCards"
            :key="card.key"
            class="summary-card"
            :class="card.tone"
          >
            <span class="summary-label">{{ card.label }}</span>
            <strong class="summary-value">{{ card.value }}</strong>
          </article>
        </section>

        <section class="panel-grid">
          <article class="panel prediction-panel">
            <div class="panel-header">
              <h2>최근 모델 상태</h2>
              <span class="panel-note">
                {{ overview?.latest_prediction?.model_name || 'unknown' }}
                {{ overview?.latest_prediction?.model_version || '' }}
              </span>
            </div>
            <div class="mini-stats">
              <div v-for="item in latestPredictionStats" :key="item.label" class="mini-stat">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <div class="health-strip">
              <div class="health-block">
                <span>Completed</span>
                <strong>{{ overview?.completed_incident_count ?? 0 }}</strong>
              </div>
              <div class="health-block">
                <span>Failed</span>
                <strong>{{ overview?.failed_incident_count ?? 0 }}</strong>
              </div>
              <div class="health-block">
                <span>Fallback</span>
                <strong>{{ overview?.fallback_events_last_24h ?? 0 }}</strong>
              </div>
            </div>
          </article>

          <article class="panel alert-panel">
            <div class="panel-header">
              <h2>Alert Summary</h2>
            </div>
            <div class="severity-row">
              <div class="severity-box sev-high">
                <span>HIGH</span>
                <strong>{{ severitySummary.HIGH || severitySummary.CRITICAL || 0 }}</strong>
              </div>
              <div class="severity-box sev-medium">
                <span>MEDIUM</span>
                <strong>{{ severitySummary.MEDIUM || 0 }}</strong>
              </div>
              <div class="severity-box sev-low">
                <span>LOW</span>
                <strong>{{ severitySummary.LOW || severitySummary.INFO || 0 }}</strong>
              </div>
            </div>
            <ul class="alert-list">
              <li v-for="alert in topAlerts" :key="`${alert.title}-${alert.created_at}-${alert.incident_id}`" class="alert-item">
                <div class="alert-head">
                  <span class="alert-title">{{ alert.title }}</span>
                  <span class="severity-pill" :class="severityClass(alert.severity)">
                    {{ alert.severity }}
                  </span>
                </div>
                <p class="alert-message">{{ alert.message || `${alert.service || 'system'} / ${alert.stage || '-'}` }}</p>
                <div class="alert-meta">
                  <span>{{ alert.service || '-' }}</span>
                  <span>{{ alert.incident_id ? `INC-${alert.incident_id}` : alert.status || '-' }}</span>
                  <span>{{ formatDate(alert.created_at) }}</span>
                </div>
              </li>
            </ul>
          </article>
        </section>

        <section class="panel-grid secondary">
          <article class="panel drift-panel">
            <div class="panel-header">
              <h2>Drift Detection</h2>
            </div>
            <div v-if="driftEvents.length === 0" class="empty-note">
              현재 감지된 드리프트 이벤트가 없습니다.
            </div>
            <div v-else class="drift-list">
              <div v-for="item in driftEvents" :key="`${item.category}-${item.metric}`" class="drift-item">
                <div class="drift-top">
                  <strong>{{ item.metric }}</strong>
                  <span class="severity-pill" :class="severityClass(item.severity)">{{ item.severity }}</span>
                </div>
                <p>{{ item.category }}</p>
              </div>
            </div>
          </article>

          <article class="panel model-panel">
            <div class="panel-header">
              <h2>Model Registry</h2>
            </div>
            <div class="model-table">
              <div class="model-row model-head">
                <span>Model</span>
                <span>Version</span>
                <span>Predictions</span>
                <span>Last Used</span>
              </div>
              <div v-for="item in topModels" :key="`${item.name}-${item.version}`" class="model-row">
                <span>{{ item.name }}</span>
                <span>{{ item.version }}</span>
                <span>{{ item.prediction_count }}</span>
                <span>{{ formatDate(item.last_used_at) }}</span>
              </div>
            </div>
          </article>
        </section>
      </template>
    </section>
  </main>
</template>

<style scoped>
.analytics-shell {
  min-height: 100vh;
  color: #f5f7fb;
  background:
    radial-gradient(circle at top left, rgba(245, 158, 11, 0.14), transparent 30%),
    radial-gradient(circle at 85% 20%, rgba(34, 197, 94, 0.14), transparent 26%),
    linear-gradient(180deg, #07111b 0%, #0d1724 45%, #111c29 100%);
  font-family: 'IBM Plex Sans', 'Pretendard', sans-serif;
  position: relative;
  overflow: hidden;
}

.analytics-backdrop {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 36px 36px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.75), transparent);
  pointer-events: none;
}

.analytics-wrap {
  width: min(1240px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 48px;
  position: relative;
  z-index: 1;
}

.analytics-nav,
.hero-panel,
.summary-grid,
.panel-grid {
  margin-bottom: 20px;
}

.analytics-nav,
.nav-meta,
.hero-status,
.panel-header,
.severity-row,
.alert-meta,
.drift-top,
.model-row {
  display: flex;
  align-items: center;
}

.analytics-nav,
.panel-header,
.model-row {
  justify-content: space-between;
}

.back-button,
.refresh-button {
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(8, 16, 26, 0.68);
  color: #f7fafc;
  padding: 10px 14px;
  border-radius: 999px;
  cursor: pointer;
}

.nav-meta {
  gap: 12px;
}

.nav-chip {
  letter-spacing: 0.24em;
  font-size: 11px;
  color: #8fb8ff;
}

.hero-panel,
.panel,
.summary-card,
.state-panel {
  backdrop-filter: blur(18px);
  background: rgba(8, 16, 26, 0.72);
  border: 1px solid rgba(148, 163, 184, 0.18);
  box-shadow: 0 24px 60px rgba(3, 10, 18, 0.34);
}

.hero-panel {
  padding: 28px;
  border-radius: 28px;
  display: grid;
  grid-template-columns: 1.5fr 0.9fr;
  gap: 18px;
}

.eyebrow {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.22em;
  color: #fbbf24;
  font-size: 12px;
}

.hero-panel h1 {
  margin: 0;
  font-size: clamp(32px, 4vw, 46px);
  line-height: 1;
}

.hero-desc {
  margin: 14px 0 0;
  max-width: 48rem;
  color: #b8c6d8;
  line-height: 1.6;
}

.hero-status {
  gap: 14px;
  justify-content: flex-end;
}

.status-card {
  min-width: 150px;
  padding: 16px 18px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.07), rgba(255, 255, 255, 0.03));
}

.status-label,
.summary-label,
.panel-note,
.mini-stat span,
.health-block span,
.empty-note,
.alert-meta,
.drift-item p,
.model-head {
  color: #8ea1b7;
  font-size: 12px;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.summary-card {
  padding: 18px 20px;
  border-radius: 22px;
}

.summary-value {
  display: block;
  margin-top: 10px;
  font-size: 30px;
}

.summary-card.cyan { box-shadow: inset 0 0 0 1px rgba(34, 211, 238, 0.22); }
.summary-card.amber { box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.22); }
.summary-card.red { box-shadow: inset 0 0 0 1px rgba(248, 113, 113, 0.22); }
.summary-card.mint { box-shadow: inset 0 0 0 1px rgba(52, 211, 153, 0.22); }

.panel-grid {
  display: grid;
  grid-template-columns: 1.05fr 0.95fr;
  gap: 16px;
}

.panel-grid.secondary {
  grid-template-columns: 0.85fr 1.15fr;
}

.panel {
  border-radius: 26px;
  padding: 22px;
}

.panel-header h2 {
  margin: 0;
  font-size: 18px;
}

.mini-stats,
.health-strip,
.alert-list,
.drift-list,
.model-table {
  display: grid;
  gap: 12px;
}

.mini-stats {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 18px;
}

.mini-stat,
.health-block,
.severity-box,
.alert-item,
.drift-item {
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.04);
}

.mini-stat strong,
.health-block strong,
.severity-box strong {
  display: block;
  margin-top: 8px;
  font-size: 24px;
}

.health-strip,
.severity-row {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 16px;
}

.severity-row {
  display: grid;
}

.alert-list {
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
}

.alert-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.alert-title {
  font-weight: 700;
}

.alert-message {
  margin: 10px 0;
  color: #dbe5f1;
  line-height: 1.5;
}

.alert-meta {
  gap: 14px;
  flex-wrap: wrap;
}

.severity-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}

.sev-high {
  color: #fecaca;
  background: rgba(239, 68, 68, 0.18);
}

.sev-medium {
  color: #fde68a;
  background: rgba(245, 158, 11, 0.18);
}

.sev-low {
  color: #bbf7d0;
  background: rgba(34, 197, 94, 0.18);
}

.drift-list,
.model-table {
  margin-top: 16px;
}

.drift-item strong {
  font-size: 16px;
}

.model-row {
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  display: grid;
  grid-template-columns: 1.4fr 0.8fr 0.8fr 1fr;
}

.model-row:last-child {
  border-bottom: none;
}

.state-panel {
  padding: 32px;
  border-radius: 24px;
  text-align: center;
}

.state-panel.error {
  color: #fecaca;
}

@media (max-width: 960px) {
  .hero-panel,
  .panel-grid,
  .panel-grid.secondary,
  .summary-grid,
  .mini-stats,
  .health-strip,
  .severity-row {
    grid-template-columns: 1fr;
  }

  .hero-status {
    justify-content: flex-start;
    flex-direction: column;
  }

  .model-row {
    grid-template-columns: 1fr;
  }
}
</style>
