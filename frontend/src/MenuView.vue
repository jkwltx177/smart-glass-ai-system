<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  userName: string
  userRole: string
  userAvatar: string
}>()

const emit = defineEmits<{
  navigate: ['dashboard' | 'rag' | 'history' | 'analytics' | 'settings']
  logout: []
}>()

const activeMenu = ref('dashboard')
const ragImageUrl = new URL('../ragImage.png', import.meta.url).href
const predictImageUrl = new URL('../predictImage.png', import.meta.url).href

type AIOpsOverview = {
  incident_count: number
  completed_incident_count: number
  failed_incident_count: number
  prediction_count: number
  events_last_24h: number
  critical_events_last_24h: number
  fallback_events_last_24h: number
  avg_incident_latency_seconds: number
  latest_prediction?: {
    model_name?: string | null
    model_version?: string | null
  }
}

type RetrainJobItem = {
  job_id: string
  status: string
  created_at?: string | null
}

const aiopsOverview = ref<AIOpsOverview | null>(null)
const retrainJobs = ref<RetrainJobItem[]>([])

// 섹션별 노출 상태 관리
const visibleSections = ref({
  summary: false,
  ragDetail: false,
  aiDetail: false,
  serviceSelect: false
})

const sectionOffsets = ref({
  summary: 0,
  ragDetail: 0,
  aiDetail: 0,
  serviceSelect: 0,
})
const scrollProgress = ref(0)

let observer: IntersectionObserver | null = null
let scrollRafId: number | null = null

const updateScrollMotion = () => {
  const viewportCenter = window.innerHeight * 0.5
  const ids: Array<keyof typeof sectionOffsets.value> = ['summary', 'ragDetail', 'aiDetail', 'serviceSelect']
  ids.forEach((id) => {
    const el = document.getElementById(id)
    if (!el) return
    const rect = el.getBoundingClientRect()
    const elementCenter = rect.top + rect.height * 0.5
    const normalized = (elementCenter - viewportCenter) / Math.max(window.innerHeight, 1)
    const clamped = Math.max(-1, Math.min(1, normalized))
    sectionOffsets.value[id] = clamped
  })
  const maxScroll = Math.max(
    document.documentElement.scrollHeight - window.innerHeight,
    1
  )
  scrollProgress.value = Math.max(0, Math.min(1, window.scrollY / maxScroll))
}

const onScroll = () => {
  if (scrollRafId !== null) return
  scrollRafId = window.requestAnimationFrame(() => {
    updateScrollMotion()
    scrollRafId = null
  })
}

const sectionStyle = (id: keyof typeof sectionOffsets.value) => {
  const offset = sectionOffsets.value[id]
  const translateY = offset * -34
  const scale = 1 - Math.abs(offset) * 0.03
  const rotate = offset * -1.2
  return {
    transform: `translateY(${translateY.toFixed(2)}px) scale(${Math.max(0.95, scale).toFixed(3)}) rotate(${rotate.toFixed(2)}deg)`,
  }
}

onMounted(() => {
  const observerOptions = { threshold: 0.15 }
  observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id as keyof typeof visibleSections.value
        visibleSections.value[id] = true
      }
    })
  }, observerOptions)

  document.querySelectorAll('.observe-target').forEach(el => observer?.observe(el))
  updateScrollMotion()
  fetchAIOpsOverview()
  fetchRetrainJobs()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll)
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  if (observer) {
    observer.disconnect()
    observer = null
  }
  if (scrollRafId !== null) {
    window.cancelAnimationFrame(scrollRafId)
    scrollRafId = null
  }
})

const handleNav = (target: any) => {
  activeMenu.value = target
  emit('navigate', target)
}

const handleCardPointerMove = (event: MouseEvent) => {
  const card = event.currentTarget as HTMLElement | null
  if (!card) return
  const rect = card.getBoundingClientRect()
  const x = event.clientX - rect.left
  const y = event.clientY - rect.top
  const rx = ((y / rect.height) - 0.5) * -10
  const ry = ((x / rect.width) - 0.5) * 14
  card.style.setProperty('--mx', `${x.toFixed(1)}px`)
  card.style.setProperty('--my', `${y.toFixed(1)}px`)
  card.style.setProperty('--rx', `${rx.toFixed(2)}deg`)
  card.style.setProperty('--ry', `${ry.toFixed(2)}deg`)
}

const resetCardPointer = (event: MouseEvent) => {
  const card = event.currentTarget as HTMLElement | null
  if (!card) return
  card.style.setProperty('--rx', '0deg')
  card.style.setProperty('--ry', '0deg')
}

const fetchAIOpsOverview = async () => {
  try {
    const response = await fetch('/api/aiops/overview')
    if (!response.ok) return
    aiopsOverview.value = await response.json()
  } catch {
    // Keep menu stable even if overview API fails.
  }
}

const getAuthHeaders = (): Record<string, string> => {
  const accessToken = localStorage.getItem('accessToken')
  const tokenType = localStorage.getItem('tokenType') || 'Bearer'
  if (!accessToken) return {}
  return { Authorization: `${tokenType} ${accessToken}` }
}

const fetchRetrainJobs = async () => {
  const headers = getAuthHeaders()
  if (!headers.Authorization) {
    retrainJobs.value = []
    return
  }
  try {
    const response = await fetch('/api/aiops/retrain/jobs?limit=20', { headers })
    if (!response.ok) return
    const data = await response.json()
    retrainJobs.value = Array.isArray(data?.items) ? data.items : []
  } catch {
    retrainJobs.value = []
  }
}

const queuedJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'queued').length
)
const runningJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'running').length
)
const completedJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'completed').length
)
const failedJobCount = computed(
  () => retrainJobs.value.filter((j) => String(j.status || '').toLowerCase() === 'failed').length
)
const latestRetrainStatus = computed(() => {
  const latest = retrainJobs.value[0]
  return String(latest?.status || '-').toLowerCase()
})
</script>

<template>
  <div class="dashboard-wrapper">
    <div class="ambient-layer"></div>
    <div class="scroll-progress">
      <span :style="{ transform: `scaleX(${scrollProgress.toFixed(4)})` }"></span>
    </div>
    <aside class="side-navigation">
      <div class="nav-brand">
        <div class="logo-hex">S</div>
        <span class="brand-text">지능형 제어 플랫폼</span>
      </div>

      <nav class="nav-menu">
        <div class="menu-section">
          <span class="section-label">주요 콘솔</span>
          <button class="menu-item" :class="{ active: activeMenu === 'dashboard' }" @click="handleNav('dashboard')">대시보드</button>
          <button class="menu-item" :class="{ active: activeMenu === 'rag' }" @click="handleNav('rag')">ECU RAG 엔진</button>
        </div>
        <div class="menu-section">
          <span class="section-label">데이터 및 보고서</span>
          <button class="menu-item" :class="{ active: activeMenu === 'history' }" @click="handleNav('history')">요청 이력</button>
          <button class="menu-item" :class="{ active: activeMenu === 'analytics' }" @click="handleNav('analytics')">분석 통계</button>
        </div>
        <div class="menu-section">
          <span class="section-label">시스템</span>
          <button class="menu-item" :class="{ active: activeMenu === 'settings' }" @click="handleNav('settings')">환경 설정</button>
        </div>
      </nav>

      <div class="nav-footer">
        <button class="logout-btn" @click="emit('logout')">접속 종료</button>
      </div>
    </aside>

    <main class="main-viewport">
      <header class="content-header">
        <div class="header-info">
          <span class="system-status"><span class="status-dot"></span> 시스템 정상 가동 중</span>
          <h1 class="header-title">ECU <span class="text-glow">통합 제어 센터</span></h1>
        </div>
        <div class="user-meta">
          <div class="user-info">
            <span class="user-name">{{ props.userName || '로그인 사용자' }}</span>
            <span class="user-role">{{ props.userRole || '인증 사용자' }}</span>
          </div>
          <div class="user-avatar">{{ props.userAvatar || 'US' }}</div>
        </div>
      </header>

      <section class="dashboard-content">
        <section class="intro-stage">
          <div id="summary" class="observe-target reveal-section" :class="{ visible: visibleSections.summary }" :style="sectionStyle('summary')">
            <h2 class="reveal-title">ECU 품질 진단과 예방 운영의 통합</h2>
            <p class="reveal-desc">서비스 신뢰성, 모델 성능·재학습, 리스크 기반 의사결정을 통합 운영합니다.</p>
            <div class="summary-pillars">
              <span>운영 신뢰성 모니터링</span>
              <span>모델 성능·재학습 운영</span>
              <span>리스크 기반 의사결정 지원</span>
            </div>
          </div>

          <div id="ragDetail" class="observe-target detail-block" :class="{ visible: visibleSections.ragDetail }" :style="sectionStyle('ragDetail')">
            <div class="detail-text">
              <span class="tag">QUALITY ASSIST</span>
              <h3>품질 이슈 원인 근거의 빠른 확보</h3>
              <p>오류 로그, 과거 조치 이력, 점검 기준을 통합 조회해 현장 엔지니어가 품질 판단에 필요한 근거를 빠르게 확인할 수 있습니다.</p>
            </div>
            <div class="detail-visual" :style="{ transform: `translateY(${(-sectionOffsets.ragDetail * 22).toFixed(2)}px)` }">
              <img class="detail-image" :src="ragImageUrl" alt="ECU 데이터 매핑 이미지" />
            </div>
          </div>

          <div id="aiDetail" class="observe-target detail-block reverse" :class="{ visible: visibleSections.aiDetail }" :style="sectionStyle('aiDetail')">
            <div class="detail-text">
              <span class="tag">PREDICTIVE AI</span>
              <h3>품질 리스크의 선제적 대응</h3>
              <p>센서 이상 패턴과 실패 확률을 기반으로 우선 조치 대상을 제시해 다운타임과 불량 확산 위험을 줄입니다.</p>
            </div>
            <div class="detail-visual" :style="{ transform: `translateY(${(-sectionOffsets.aiDetail * 22).toFixed(2)}px)` }">
              <img class="detail-image" :src="predictImageUrl" alt="AI 패턴 분석 이미지" />
            </div>
          </div>
        </section>

        <section class="service-stage">
          <div id="serviceSelect" class="observe-target welcome-banner reveal-focus" :class="{ visible: visibleSections.serviceSelect }" :style="sectionStyle('serviceSelect')">
            <h2 class="welcome-text">지능형 서비스 선택</h2>
            <p class="welcome-sub">차량 제어 유닛(ECU) 데이터를 관리하는 중앙 제어 센터입니다.</p>
            <div class="quick-actions">
              <button class="quick-action-btn" @click="handleNav('history')">요청 이력 보기</button>
            </div>
          </div>

          <div class="service-grid">
            <div class="service-card" @click="handleNav('rag')" @mousemove="handleCardPointerMove" @mouseleave="resetCardPointer">
              <div class="card-glow"></div>
              <div class="card-inner">
                <div class="card-header">
                  <span class="badge badge-primary">활성 엔진</span>
                  <div class="card-icon">🔍</div>
                </div>
                <h3 class="card-title">ECU RAG 엔진 v2.4</h3>
                <p class="card-description">실시간 기술 문서 분석 및 지식 베이스 검색을 통해 최적화된 제어 솔루션을 제공합니다.</p>
                <div class="card-footer">콘솔 실행 <span class="arrow">→</span></div>
              </div>
            </div>
          
            <div class="service-card" @click="handleNav('analytics')" @mousemove="handleCardPointerMove" @mouseleave="resetCardPointer">
              <div class="card-glow secondary"></div>
              <div class="card-inner">
                <div class="card-header">
                  <span class="badge badge-secondary">AIOPS 운영</span>
                  <div class="card-icon">📊</div>
                </div>
                <h3 class="card-title">AIOps 운영 현황</h3>
                <p class="card-description">운영 모니터링, 모델 운영, 샘플 리스크를 한 화면에서 점검합니다.</p>
                <div class="card-footer">운영 현황 보기 <span class="arrow">→</span></div>
              </div>
            </div>
          </div>

          <div class="ops-row">
            <div class="ops-card">
              <span class="ops-label">운영 이벤트(24h)</span>
              <span class="ops-value">{{ aiopsOverview?.events_last_24h ?? 0 }}</span>
              <span class="ops-sub">critical {{ aiopsOverview?.critical_events_last_24h ?? 0 }}</span>
            </div>
            <div class="ops-card">
              <span class="ops-label">처리 지연</span>
              <span class="ops-value">{{ aiopsOverview ? `${Number(aiopsOverview.avg_incident_latency_seconds || 0).toFixed(1)}s` : '-' }}</span>
              <span class="ops-sub">fallback {{ aiopsOverview?.fallback_events_last_24h ?? 0 }}</span>
            </div>
            <div class="ops-card">
              <span class="ops-label">재학습 큐</span>
              <span class="ops-value">{{ queuedJobCount }} / {{ runningJobCount }}</span>
              <span class="ops-sub">queued / running</span>
            </div>
            <div class="ops-card">
              <span class="ops-label">최근 재학습</span>
              <span class="ops-value text-success">{{ latestRetrainStatus }}</span>
              <span class="ops-sub">completed {{ completedJobCount }} · failed {{ failedJobCount }}</span>
            </div>
          </div>
        </section>
      </section>
    </main>
  </div>
</template>

<style scoped>
/* 핵심 레이아웃 */
.dashboard-wrapper {
  --line-soft: rgba(255, 255, 255, 0.08);
  --glass-bg: rgba(20, 24, 34, 0.52);
  --glow-blue: #66a7ff;
  display: flex;
  min-height: 100vh;
  background: radial-gradient(circle at 78% -10%, rgba(104, 150, 255, 0.28), transparent 42%),
    radial-gradient(circle at 8% 12%, rgba(83, 117, 199, 0.22), transparent 34%),
    #06080d;
  color: #f8fafc;
  font-family: "SF Pro Display", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  position: relative;
  overflow-x: hidden;
}
.ambient-layer {
  position: fixed;
  inset: 0;
  background: radial-gradient(circle at 22% 20%, rgba(146, 193, 255, 0.12), transparent 36%),
    radial-gradient(circle at 88% 28%, rgba(158, 130, 255, 0.1), transparent 38%);
  pointer-events: none;
  z-index: 0;
}
.scroll-progress {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 3px;
  background: rgba(255, 255, 255, 0.06);
  z-index: 1400;
}
.scroll-progress span {
  display: block;
  height: 100%;
  width: 100%;
  transform-origin: left center;
  transform: scaleX(0);
  background: linear-gradient(90deg, #6ea8ff, #9dc5ff 60%, #d9eaff);
}
.side-navigation {
  width: 250px;
  background: rgba(12, 16, 24, 0.74);
  border-right: 1px solid var(--line-soft);
  backdrop-filter: blur(16px);
  padding: 32px 0;
  display: flex;
  flex-direction: column;
  position: fixed;
  height: 100vh;
  z-index: 20;
}
.main-viewport { flex-grow: 1; padding: 40px 60px; margin-left: 250px; position: relative; z-index: 1; }

.dashboard-content {
  scroll-snap-type: y mandatory;
}
.intro-stage,
.service-stage {
  scroll-snap-align: start;
  scroll-snap-stop: always;
}
.intro-stage {
  min-height: calc(100vh - 160px);
}

/* 사이드바 스타일링 */
.nav-brand { padding: 0 24px; display: flex; align-items: center; gap: 12px; margin-bottom: 48px; }
.logo-hex { width: 32px; height: 32px; background: linear-gradient(160deg, #a9c9ff, #4f7ef0); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-weight: 900; color: #071226; box-shadow: 0 10px 22px rgba(70, 122, 255, 0.35); }
.brand-text { font-size: 11px; font-weight: 800; letter-spacing: 0.15em; }
.menu-section { margin-bottom: 30px; padding: 0 12px; }
.section-label { font-size: 10px; color: #475569; font-weight: 700; text-transform: uppercase; padding: 0 14px; display: block; margin-bottom: 12px; }
.menu-item { width: 100%; text-align: left; background: none; border: none; padding: 12px 14px; border-radius: 12px; font-size: 14px; color: #94a3b8; cursor: pointer; transition: 0.22s; }
.menu-item.active { background: rgba(104, 150, 255, 0.16); color: #dcecff; font-weight: 600; border: 1px solid rgba(146, 193, 255, 0.26); }
.logout-btn { margin: 0 20px; padding: 12px; border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; background: none; cursor: pointer; transition: 0.3s; }
.logout-btn:hover { background: rgba(239, 68, 68, 0.1); }

/* 상단 카드 그리드 */
.welcome-banner {
  margin-top: 0;
  margin-bottom: 42px;
}
.service-stage {
  background:
    radial-gradient(circle at 18% 0%, rgba(120, 168, 255, 0.12), transparent 42%),
    linear-gradient(180deg, rgba(13, 19, 30, 0.56), rgba(10, 14, 22, 0.46));
  border: 1px solid rgba(166, 197, 255, 0.16);
  border-radius: 30px;
  padding: 22px 24px 10px;
  margin-top: 110px;
  margin-bottom: 28px;
  min-height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.welcome-text { font-size: clamp(28px, 3.6vw, 44px); letter-spacing: -0.02em; font-weight: 760; margin-bottom: 10px; line-height: 1.07; }
.welcome-sub { font-size: 16px; color: #b4c2d8; letter-spacing: -0.01em; }
.reveal-focus {
  opacity: 0;
  transform: translateY(30px) scale(0.97);
  filter: saturate(0.85);
  background: transparent;
  border: 0;
  box-shadow: none;
  transition: opacity 0.65s ease, transform 0.65s ease, filter 0.65s ease;
}
.reveal-focus.visible {
  opacity: 1;
  transform: translateY(0) scale(1);
  filter: saturate(1);
}
.welcome-banner::after {
  content: "";
  display: block;
  width: min(420px, 34vw);
  height: 2px;
  margin-top: 16px;
  background: linear-gradient(90deg, rgba(153, 196, 255, 0.95), rgba(153, 196, 255, 0.05));
}
.quick-actions {
  margin-top: 14px;
}
.quick-action-btn {
  border: 1px solid rgba(148, 163, 184, 0.4);
  background: rgba(12, 18, 30, 0.55);
  color: #dbeafe;
  padding: 8px 14px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: 0.2s ease;
}
.quick-action-btn:hover {
  border-color: rgba(147, 197, 253, 0.7);
  background: rgba(30, 58, 138, 0.35);
}
.text-glow { background: linear-gradient(95deg, #dce9ff 0%, #97beff 48%, #709fff 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.service-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; margin-bottom: 34px; }
.service-card {
  --mx: 50%;
  --my: 50%;
  --rx: 0deg;
  --ry: 0deg;
  background: linear-gradient(160deg, rgba(20, 28, 40, 0.78), rgba(17, 20, 30, 0.58));
  border-radius: 28px;
  padding: 35px;
  border: 1px solid rgba(166, 197, 255, 0.16);
  position: relative;
  overflow: hidden;
  cursor: pointer;
  backdrop-filter: blur(14px);
  transform: perspective(900px) rotateX(var(--rx)) rotateY(var(--ry)) translateY(0);
  transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
}
.service-card::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(220px circle at var(--mx) var(--my), rgba(146, 190, 255, 0.32), transparent 60%);
  pointer-events: none;
  opacity: 0.8;
}
.service-card:hover {
  transform: perspective(900px) rotateX(var(--rx)) rotateY(var(--ry)) translateY(-10px);
  border-color: rgba(181, 210, 255, 0.38);
  box-shadow: 0 22px 48px rgba(50, 108, 211, 0.27);
}
.card-header { display: flex; justify-content: space-between; margin-bottom: 25px; }
.card-title { font-size: clamp(26px, 2.1vw, 30px); margin-bottom: 15px; line-height: 1.2; }
.card-description { color: #94a3b8; line-height: 1.6; font-size: 15px; margin-bottom: 30px; }
.card-footer { color: #9ac2ff; font-weight: 700; display: flex; align-items: center; gap: 8px; letter-spacing: 0.01em; }

/* 지표 레이아웃 */
.ops-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 100px; }
.ops-card {
  background: linear-gradient(180deg, rgba(9, 17, 30, 0.82), rgba(7, 14, 24, 0.72));
  padding: 22px 24px;
  border-radius: 22px;
  border: 1px solid rgba(154, 179, 216, 0.22);
  box-shadow: inset 0 0 0 1px rgba(106, 143, 196, 0.1);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ops-label { font-size: 14px; color: #96a8c1; font-weight: 700; }
.ops-value { font-size: clamp(28px, 2.4vw, 34px); line-height: 1.15; font-weight: 800; letter-spacing: 0; color: #e9f2ff; }
.ops-sub { font-size: 12px; color: #97abc7; font-weight: 600; }
.text-success { color: #10b981; }

/* 스크롤 애니메이션 섹션 */
.observe-target { opacity: 0; transform: translateY(18px); transition: opacity 0.6s ease, transform 0.6s ease; }
.observe-target.visible { opacity: 1; transform: translateY(0); }

.reveal-section { text-align: center; margin-bottom: 64px; }
.reveal-title { font-size: clamp(30px, 3.8vw, 55px); letter-spacing: -0.03em; line-height: 1.08; margin-bottom: 14px; font-weight: 760; }
.reveal-desc {
  color: #9fb2cf;
  max-width: 1100px;
  margin: 0 auto;
  line-height: 1.8;
  font-size: 17px;
  word-break: keep-all;
  line-break: strict;
}

@media (min-width: 1280px) {
  .reveal-desc {
    white-space: nowrap;
  }
}

.summary-pillars {
  margin-top: 12px;
  display: flex;
  justify-content: center;
  gap: 8px;
  flex-wrap: wrap;
}

.summary-pillars span {
  font-size: 11px;
  color: #c9d8ee;
  border: 1px solid rgba(166, 197, 255, 0.24);
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(17, 28, 44, 0.35);
}

.detail-block { display: flex; align-items: center; gap: 32px; margin-bottom: 52px; }
.detail-block.reverse { flex-direction: row-reverse; }
.detail-text { flex: 1; }
.tag { color: #3b82f6; font-weight: 800; font-size: 12px; letter-spacing: 2px; }
.detail-text h3 { font-size: 32px; margin: 15px 0; font-weight: 800; }
.detail-text p { color: #94a3b8; line-height: 1.8; font-size: 16px; }
.detail-visual {
  flex: 1;
  background: linear-gradient(145deg, rgba(22, 29, 42, 0.86), rgba(16, 20, 29, 0.58));
  height: 300px;
  border-radius: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(169, 197, 255, 0.16);
  transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease;
  box-shadow: 0 16px 44px rgba(14, 25, 48, 0.3);
}
.detail-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 20px;
  transition: transform 0.25s ease;
}

@media (max-width: 1200px) {
  .service-grid { grid-template-columns: 1fr; }
  .detail-block { flex-direction: column; text-align: center; }
  .detail-block.reverse { flex-direction: column; }
  .ops-row { grid-template-columns: repeat(2, 1fr); }
}

.content-header {
  position: relative;
  margin-bottom: 100px;
}
.system-status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #22c55e;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #22c55e;
  box-shadow: 0 0 0 6px rgba(34, 197, 94, 0.18);
}

.user-meta {
  position: fixed;
  top: 18px;
  right: 24px;
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(10, 11, 16, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.25);
  border-radius: 12px;
  padding: 8px 10px;
  z-index: 1000;
  backdrop-filter: blur(6px);
}

.user-info {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  line-height: 1.2;
}

.user-name {
  font-size: 12px;
  font-weight: 700;
  color: #e2e8f0;
}

.user-role {
  font-size: 11px;
  color: #94a3b8;
}

.user-avatar {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  color: #dbeafe;
  background: rgba(37, 99, 235, 0.18);
}
</style>
