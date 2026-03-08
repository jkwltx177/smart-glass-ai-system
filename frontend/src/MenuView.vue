<script setup lang="ts">
import { ref, onMounted } from 'vue'

const emit = defineEmits<{
  navigate: ['dashboard' | 'rag' | 'history' | 'analytics' | 'settings']
  logout: []
}>()

const activeMenu = ref('dashboard')
const ragImageUrl = new URL('../ragImage.png', import.meta.url).href
const predictImageUrl = new URL('../predictImage.png', import.meta.url).href

// 섹션별 노출 상태 관리
const visibleSections = ref({
  summary: false,
  ragDetail: false,
  aiDetail: false
})

onMounted(() => {
  const observerOptions = { threshold: 0.15 }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id as keyof typeof visibleSections.value
        visibleSections.value[id] = true
      }
    })
  }, observerOptions)

  document.querySelectorAll('.observe-target').forEach(el => observer.observe(el))
})

const handleNav = (target: any) => {
  activeMenu.value = target
  emit('navigate', target)
}
</script>

<template>
  <div class="dashboard-wrapper">
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
            <span class="user-name">프리미엄 관리자</span>
            <span class="user-role">엔터프라이즈 권한</span>
          </div>
          <div class="user-avatar">PA</div>
        </div>
      </header>

      <section class="dashboard-content">
        <div class="welcome-banner">
          <h2 class="welcome-text">지능형 서비스 선택</h2>
          <p class="welcome-sub">차량 제어 유닛(ECU) 데이터를 관리하는 중앙 제어 센터입니다.</p>
        </div>

        <div class="service-grid">
          <div class="service-card" @click="handleNav('rag')">
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

          <div class="service-card" @click="handleNav('history')">
            <div class="card-glow secondary"></div>
            <div class="card-inner">
              <div class="card-header">
                <span class="badge badge-secondary">데이터 로그</span>
                <div class="card-icon">📊</div>
              </div>
              <h3 class="card-title">예측형 AI 분석</h3>
              <p class="card-description">과거 요청 데이터와 AI 응답 이력을 분석하여 고장 징후 및 서비스 로그를 관리합니다.</p>
              <div class="card-footer">분석 시작 <span class="arrow">→</span></div>
            </div>
          </div>
        </div>

        <div class="metric-row">
          <div class="metric-card">
            <span class="metric-label">API 호출 성공률</span>
            <span class="metric-value text-success">99.9%</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">평균 응답 속도</span>
            <span class="metric-value">1.2s</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">처리 토큰 수</span>
            <span class="metric-value">4.2M</span>
          </div>
        </div>

        <div id="summary" class="observe-target reveal-section" :class="{ visible: visibleSections.summary }">
          <h2 class="reveal-title">지능형 ECU 데이터 관제와 미래 예측의 통합</h2>
          <p class="reveal-desc">RAG 기술로 복잡한 문서를 즉각 지식화하고, 예측형 AI로 오류를 사전 방지하는 차세대 관제 환경입니다.</p>
        </div>

        <div id="ragDetail" class="observe-target detail-block" :class="{ visible: visibleSections.ragDetail }">
          <div class="detail-text">
            <span class="tag">RAG TECHNOLOGY</span>
            <h3>기술 문서의 즉각적 해독</h3>
            <p>방대한 ECU 회로도와 매뉴얼을 AI가 실시간으로 탐색합니다. 엔지니어는 더 이상 문서를 찾지 않고, AI에게 질문하여 정확한 소스와 해결책을 얻습니다.</p>
          </div>
          <div class="detail-visual">
            <img class="detail-image" :src="ragImageUrl" alt="ECU 데이터 매핑 이미지" />
          </div>
        </div>

        <div id="aiDetail" class="observe-target detail-block reverse" :class="{ visible: visibleSections.aiDetail }">
          <div class="detail-text">
            <span class="tag">PREDICTIVE AI</span>
            <h3>미래를 대비하는 데이터 분석</h3>
            <p>ECU의 미세한 파형 변화와 로그 패턴을 분석하여 고장이 발생하기 전 징후를 감지합니다. 예방적 유지보수를 통해 시스템 다운타임을 최소화하십시오.</p>
          </div>
          <div class="detail-visual">
            <img class="detail-image" :src="predictImageUrl" alt="AI 패턴 분석 이미지" />
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
/* 핵심 레이아웃 */
.dashboard-wrapper { display: flex; min-height: 100vh; background-color: #0a0b10; color: #f8fafc; font-family: 'Inter', sans-serif; }
.side-navigation { width: 250px; background-color: #0f111a; border-right: 1px solid rgba(255, 255, 255, 0.05); padding: 32px 0; display: flex; flex-direction: column; position: fixed; height: 100vh; }
.main-viewport { flex-grow: 1; padding: 40px 60px; margin-left: 250px; }

/* 사이드바 스타일링 */
.nav-brand { padding: 0 24px; display: flex; align-items: center; gap: 12px; margin-bottom: 48px; }
.logo-hex { width: 32px; height: 32px; background: linear-gradient(135deg, #3b82f6, #8b5cf6); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-weight: 900; box-shadow: 0 0 20px rgba(59, 130, 246, 0.3); }
.brand-text { font-size: 11px; font-weight: 800; letter-spacing: 0.15em; }
.menu-section { margin-bottom: 30px; padding: 0 12px; }
.section-label { font-size: 10px; color: #475569; font-weight: 700; text-transform: uppercase; padding: 0 14px; display: block; margin-bottom: 12px; }
.menu-item { width: 100%; text-align: left; background: none; border: none; padding: 12px 14px; border-radius: 10px; font-size: 14px; color: #94a3b8; cursor: pointer; transition: 0.2s; }
.menu-item.active { background: rgba(59, 130, 246, 0.1); color: #3b82f6; font-weight: 600; }
.logout-btn { margin: 0 20px; padding: 12px; border-radius: 8px; border: 1px solid rgba(239, 68, 68, 0.3); color: #ef4444; background: none; cursor: pointer; transition: 0.3s; }
.logout-btn:hover { background: rgba(239, 68, 68, 0.1); }

/* 상단 카드 그리드 */
.welcome-banner { margin-bottom: 40px; }
.welcome-text { font-size: 32px; font-weight: 800; margin-bottom: 10px; }
.text-glow { background: linear-gradient(to right, #3b82f6, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.service-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 24px; margin-bottom: 40px; }
.service-card { background: #14161f; border-radius: 24px; padding: 35px; border: 1px solid rgba(255, 255, 255, 0.05); position: relative; overflow: hidden; cursor: pointer; transition: 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275); }
.service-card:hover { transform: translateY(-10px); border-color: rgba(59, 130, 246, 0.3); }
.card-header { display: flex; justify-content: space-between; margin-bottom: 25px; }
.card-title { font-size: 22px; margin-bottom: 15px; }
.card-description { color: #94a3b8; line-height: 1.6; font-size: 15px; margin-bottom: 30px; }
.card-footer { color: #3b82f6; font-weight: 700; display: flex; align-items: center; gap: 8px; }

/* 지표 레이아웃 */
.metric-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 100px; }
.metric-card { background: rgba(255, 255, 255, 0.02); padding: 24px; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.05); }
.metric-label { font-size: 12px; color: #64748b; margin-bottom: 8px; display: block; }
.metric-value { font-size: 28px; font-weight: 700; }
.text-success { color: #10b981; }

/* 스크롤 애니메이션 섹션 */
.observe-target { opacity: 0; transform: translateY(40px); transition: all 1s ease; }
.observe-target.visible { opacity: 1; transform: translateY(0); }

.reveal-section { text-align: center; margin-bottom: 120px; }
.reveal-title { font-size: 28px; margin-bottom: 20px; }
.reveal-desc { color: #94a3b8; max-width: 700px; margin: 0 auto; line-height: 1.8; }

.detail-block { display: flex; align-items: center; gap: 60px; margin-bottom: 120px; }
.detail-block.reverse { flex-direction: row-reverse; }
.detail-text { flex: 1; }
.tag { color: #3b82f6; font-weight: 800; font-size: 12px; letter-spacing: 2px; }
.detail-text h3 { font-size: 32px; margin: 15px 0; font-weight: 800; }
.detail-text p { color: #94a3b8; line-height: 1.8; font-size: 16px; }
.detail-visual { flex: 1; background: #1a1c25; height: 300px; border-radius: 20px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255, 255, 255, 0.05); }
.detail-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 20px;
}

@media (max-width: 1200px) {
  .service-grid { grid-template-columns: 1fr; }
  .detail-block { flex-direction: column; text-align: center; }
  .detail-block.reverse { flex-direction: column; }
}
</style>