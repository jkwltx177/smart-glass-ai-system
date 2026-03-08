<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface HistoryLog {
  id: string
  timestamp: string
  type: string
  status: string
  latency: string
}

const emit = defineEmits<{
  back: []
}>()

const historyLogs = ref<HistoryLog[]>([])
const loading = ref(true)
const error = ref<string | null>(null)

async function fetchHistory() {
  loading.value = true
  error.value = null
  try {
    const response = await fetch('/api/incidents/') // Vite proxy will rewrite this to /api/v1/incidents/
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const data = await response.json()
    // Map backend incident format to HistoryLog interface
    historyLogs.value = data.map((item: any) => ({
      id: item.incident_id,
      timestamp: new Date(item.created_at).toLocaleString(),
      type: item.device_type || 'Unknown',
      status: item.status,
      latency: '-' // Not provided by real API yet
    }))
  } catch (e) {
    error.value = e instanceof Error ? e.message : '분석 이력을 불러오지 못했습니다.'
    historyLogs.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => fetchHistory())
</script>

<template>
  <main class="history-viewport">
    <div class="background-overlay"></div>

    <section class="history-container">
      <nav class="history-nav">
        <button class="back-link-btn" @click="emit('back')">
          <span class="nav-icon">←</span> Back to Dashboard
        </button>
        <div class="breadcrumb">Control Center / <span class="active">Request History</span></div>
      </nav>

      <div class="history-module shadow-2xl">
        <header class="module-header">
          <div class="header-left">
            <h1 class="module-title">Inquiry History</h1>
            <p class="module-description">플랫폼을 통해 처리된 모든 RAG 요청 이력을 실시간으로 모니터링합니다.</p>
          </div>
          <div class="header-right">
            <button class="export-btn">Export CSV</button>
          </div>
        </header>

        <div class="filter-bar">
          <div class="search-box">
            <input type="text" placeholder="Search by Request ID..." />
          </div>
          <div class="filter-options">
            <select>
              <option>All Status</option>
              <option>Success</option>
              <option>Failed</option>
            </select>
          </div>
        </div>

        <div class="table-wrapper">
          <div v-if="loading" class="loading-state">분석 이력을 불러오는 중...</div>
          <div v-else-if="error" class="error-state">{{ error }}</div>
          <table v-else class="data-table">
            <thead>
              <tr>
                <th>Request ID</th>
                <th>Timestamp</th>
                <th>Analysis Type</th>
                <th>Processing</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="log in historyLogs" :key="log.id">
                <td class="font-mono">{{ log.id }}</td>
                <td class="text-muted">{{ log.timestamp }}</td>
                <td><span class="type-tag">{{ log.type }}</span></td>
                <td class="text-muted">{{ log.latency }}</td>
                <td>
                  <span :class="['status-badge', log.status.toLowerCase()]">
                    {{ log.status }}
                  </span>
                </td>
                <td>
                  <button class="row-action-btn">View Detail</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <footer class="table-footer">
          <div class="pagination-info">Showing {{ historyLogs.length }} of {{ historyLogs.length }} entries</div>
          <div class="pagination-controls">
            <button disabled>Prev</button>
            <button class="active">1</button>
            <button>2</button>
            <button>Next</button>
          </div>
        </footer>
      </div>
    </section>
  </main>
</template>

<style scoped>
/* Core Foundation */
.history-viewport {
  min-height: 100vh;
  background-color: #0f1117;
  color: #f1f5f9;
  font-family: 'Inter', -apple-system, sans-serif;
  padding: 40px 20px;
  display: flex;
  justify-content: center;
  position: relative;
}

.background-overlay {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(at 0% 0%, rgba(59, 130, 246, 0.03) 0px, transparent 50%);
  pointer-events: none;
}

.history-container {
  width: 100%;
  max-width: 1100px;
  z-index: 10;
}

/* Navigation */
.history-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.back-link-btn {
  background: none; border: none; color: #94a3b8;
  font-size: 13px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; gap: 8px; transition: 0.2s;
}

.back-link-btn:hover { color: #fff; }

.breadcrumb { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #475569; }
.breadcrumb .active { color: #60a5fa; font-weight: 700; }

/* Main Module */
.history-module {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 40px;
}

.module-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}

.module-title { font-size: 24px; font-weight: 700; margin-bottom: 8px; color: #fff; }
.module-description { color: #94a3b8; font-size: 14px; }

.export-btn {
  background: #334155; color: #fff; border: 1px solid #475569;
  padding: 8px 16px; border-radius: 2px; font-size: 12px; font-weight: 600;
  cursor: pointer; transition: 0.2s;
}

.export-btn:hover { background: #475569; }

/* Filter Bar */
.filter-bar {
  display: flex; gap: 12px; margin-bottom: 24px;
}

.search-box input, .filter-options select {
  background: #0f172a; border: 1px solid #334155; color: #fff;
  padding: 10px 14px; border-radius: 2px; font-size: 13px;
}

.search-box input { width: 280px; }

/* Table Styling */
.table-wrapper {
  border: 1px solid #334155;
  border-radius: 2px;
  overflow: hidden;
  background: #161e2d;
}

.loading-state,
.error-state {
  padding: 48px 20px;
  text-align: center;
  color: #94a3b8;
  font-size: 14px;
}

.error-state {
  color: #ef4444;
}

.data-table {
  width: 100%; border-collapse: collapse; text-align: left;
}

.data-table th {
  background: #1e293b; color: #94a3b8; font-size: 11px;
  text-transform: uppercase; letter-spacing: 0.05em;
  padding: 14px 20px; border-bottom: 1px solid #334155;
}

.data-table td {
  padding: 16px 20px; font-size: 13px; border-bottom: 1px solid #1f2937;
}

.data-table tbody tr:hover { background: rgba(255, 255, 255, 0.02); }

.font-mono { font-family: 'JetBrains Mono', monospace; color: #60a5fa; }
.text-muted { color: #64748b; }

/* Tags & Badges */
.type-tag {
  background: rgba(96, 165, 250, 0.1); color: #60a5fa;
  padding: 2px 8px; border-radius: 2px; font-size: 11px; font-weight: 600;
}

.status-badge {
  padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700;
}

.status-badge.success { background: rgba(16, 185, 129, 0.1); color: #10b981; }
.status-badge.failed { background: rgba(239, 68, 68, 0.1); color: #ef4444; }

.row-action-btn {
  background: none; border: 1px solid #334155; color: #cbd5e1;
  padding: 4px 10px; border-radius: 2px; font-size: 11px; cursor: pointer;
}

.row-action-btn:hover { border-color: #60a5fa; color: #fff; }

/* Footer */
.table-footer {
  margin-top: 24px; display: flex; justify-content: space-between;
  align-items: center; font-size: 12px; color: #64748b;
}

.pagination-controls { display: flex; gap: 4px; }
.pagination-controls button {
  background: #0f172a; border: 1px solid #334155; color: #94a3b8;
  width: 32px; height: 32px; border-radius: 2px; cursor: pointer;
}

.pagination-controls button.active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.pagination-controls button:disabled { opacity: 0.3; cursor: not-allowed; }
</style>