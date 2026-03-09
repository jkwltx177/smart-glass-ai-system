<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  ragLoading: boolean
  ragMessage: string
  incidentId: string | null
  predictiveSummary: {
    failure_probability: number
    predicted_rul_minutes: number
    anomaly_score: number
  } | null
}>()

const emit = defineEmits<{
  submit: [{ imageFile: File | null; audioFile: File | null; equipmentId: string }]
  mobileResult: [{ incidentId: string; explanation: string; steps: string[] }]
  back: []
  logout: []
}>()

const selectedImage = ref<File | null>(null)
const selectedAudio = ref<File | null>(null)
const equipmentId = ref('')
const deviceOptions = ref<Array<{ device_id: string; device_name?: string }>>([])
const devicesLoading = ref(false)
const devicesError = ref('')
const showAddDevice = ref(false)
const addDeviceLoading = ref(false)
const newDeviceId = ref('')
const newDeviceName = ref('')
const newVehicleType = ref('')
const newLineOrSite = ref('')
const newLocation = ref('')
const reportGenerating = ref(false)
const previewUrl = ref<string | null>(null)
const mobileCode = ref('')
const mobileLink = ref('')
const mobileConnected = ref(false)
const mobileDeviceLabel = ref('')
const mobileLastSeen = ref('')
const mobileStatusError = ref('')
const mobileStatusLoading = ref(false)
const mobilePollingId = ref<number | null>(null)
const lastMobileResultId = ref('')
const ACCESS_TOKEN_STORAGE_KEY = 'accessToken'
const TOKEN_TYPE_STORAGE_KEY = 'tokenType'
const getUserStorageSuffix = () => {
  const token = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  if (!token) return 'anon'
  try {
    const payloadPart = token.split('.')[1] || ''
    const b64 = payloadPart.replace(/-/g, '+').replace(/_/g, '/')
    const pad = '='.repeat((4 - (b64.length % 4)) % 4)
    const json = atob(b64 + pad)
    const payload = JSON.parse(json)
    return String(payload?.sub || 'anon')
  } catch {
    return 'anon'
  }
}

const mobileHostStorageKey = `mobileHostOverride:${getUserStorageSuffix()}`
const mobileHost = ref(localStorage.getItem(mobileHostStorageKey) || '')
const mobileQrSrc = computed(() => {
  if (!mobileLink.value) return ''
  return `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(mobileLink.value)}`
})
const metricCards = computed(() => {
  if (!props.predictiveSummary) return []
  const fp = Math.max(0, Math.min(1, Number(props.predictiveSummary.failure_probability || 0)))
  const an = Math.max(0, Math.min(1, Number(props.predictiveSummary.anomaly_score || 0)))
  const rulRaw = Math.max(0, Number(props.predictiveSummary.predicted_rul_minutes || 0))
  const rulMax = 1440
  const rulRatio = Math.max(0, Math.min(1, rulRaw / rulMax))

  return [
    {
      key: 'failure',
      label: 'Failure Probability',
      value: `${(fp * 100).toFixed(1)}%`,
      ratio: fp,
      color: '#ef4444',
    },
    {
      key: 'anomaly',
      label: 'Anomaly Score',
      value: `${(an * 100).toFixed(1)}%`,
      ratio: an,
      color: '#f59e0b',
    },
    {
      key: 'rul',
      label: 'Predicted RUL',
      value: `${rulRaw.toFixed(1)} min`,
      ratio: rulRatio,
      color: '#10b981',
    },
  ]
})

const isRecording = ref(false)
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []

const getAuthHeaders = (): Record<string, string> => {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  const tokenType = localStorage.getItem(TOKEN_TYPE_STORAGE_KEY) ?? 'Bearer'
  if (!accessToken) return {}
  return { Authorization: `${tokenType} ${accessToken}` }
}

const isLocalHost = () =>
  ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname)

const buildMobileOrigin = (): string => {
  if (!isLocalHost()) {
    return window.location.origin
  }
  const host = mobileHost.value.trim()
  if (!host) {
    return ''
  }
  return `${window.location.protocol}//${host}`
}

const rebuildMobileLink = () => {
  const origin = buildMobileOrigin()
  if (!origin || !mobileCode.value) {
    mobileLink.value = ''
    return
  }
  mobileLink.value = `${origin}/?mobile=1&code=${mobileCode.value}`
}

const startMobileSession = async () => {
  try {
    const response = await fetch('/api/mobile/session/start', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        equipment_id: equipmentId.value.trim() || undefined,
      }),
    })
    if (!response.ok) {
      throw new Error(`세션 생성 실패 (${response.status})`)
    }
    const data = await response.json()
    mobileCode.value = String(data?.code ?? '')
    rebuildMobileLink()
  } catch (error) {
    mobileStatusError.value = error instanceof Error ? error.message : '모바일 세션 생성 오류'
  }
}

const bindMobileSessionEquipment = async () => {
  if (!mobileCode.value || !equipmentId.value.trim()) return
  try {
    await fetch(`/api/mobile/session/${mobileCode.value}/equipment`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        equipment_id: equipmentId.value.trim(),
      }),
    })
  } catch {
    // Ignore transient binding failures; polling will keep main flow alive.
  }
}

const pollMobileStatus = async () => {
  if (!mobileCode.value) return
  mobileStatusLoading.value = true
  try {
    const response = await fetch(`/api/mobile/session/${mobileCode.value}`, {
      headers: {
        ...getAuthHeaders(),
      },
    })
    if (!response.ok) {
      throw new Error(`모바일 상태 조회 실패 (${response.status})`)
    }
    const data = await response.json()
    mobileConnected.value = !!data?.connected
    mobileDeviceLabel.value = String(data?.device_label ?? '')
    mobileLastSeen.value = String(data?.last_seen ?? '')

    const result = data?.result
    if (result && typeof result === 'object') {
      const resultIncidentId = String(result.incident_id ?? '')
      if (resultIncidentId && lastMobileResultId.value !== resultIncidentId) {
        lastMobileResultId.value = resultIncidentId
        const explanation = String(result.explanation ?? '')
        const steps = Array.isArray(result.steps) ? result.steps.map((s: unknown) => String(s)) : []
        emit('mobileResult', {
          incidentId: resultIncidentId,
          explanation,
          steps,
        })
      }
    }
  } catch (error) {
    mobileStatusError.value = error instanceof Error ? error.message : '모바일 상태 조회 오류'
  } finally {
    mobileStatusLoading.value = false
  }
}

const loadDevices = async () => {
  devicesLoading.value = true
  devicesError.value = ''
  try {
    const response = await fetch('/api/equipment/devices', {
      headers: {
        ...getAuthHeaders(),
      },
    })
    if (!response.ok) {
      throw new Error(`장비 목록 조회 실패 (${response.status})`)
    }
    const data = await response.json()
    const items = Array.isArray(data?.items) ? data.items : []
    deviceOptions.value = items.map((it: any) => ({
      device_id: String(it.device_id ?? ''),
      device_name: typeof it.device_name === 'string' ? it.device_name : '',
    })).filter((it: { device_id: string }) => !!it.device_id)

  } catch (error) {
    devicesError.value = error instanceof Error ? error.message : '장비 목록 조회 오류'
  } finally {
    devicesLoading.value = false
  }
}

const addDevice = async () => {
  if (!newDeviceId.value.trim() || !newDeviceName.value.trim()) {
    devicesError.value = '신규 장비는 device_id와 device_name이 필요합니다.'
    return
  }
  addDeviceLoading.value = true
  devicesError.value = ''
  try {
    const response = await fetch('/api/equipment/devices', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({
        device_id: newDeviceId.value.trim(),
        device_name: newDeviceName.value.trim(),
        vehicle_type: newVehicleType.value.trim(),
        line_or_site: newLineOrSite.value.trim(),
        location: newLocation.value.trim(),
      }),
    })
    if (!response.ok) {
      throw new Error(`장비 추가 실패 (${response.status})`)
    }
    const data = await response.json()
    const createdId = String(data?.device?.device_id ?? newDeviceId.value.trim())
    if (!deviceOptions.value.some((d) => d.device_id === createdId)) {
      deviceOptions.value.unshift({
        device_id: createdId,
        device_name: String(data?.device?.device_name ?? newDeviceName.value.trim()),
      })
    }
    equipmentId.value = createdId
    showAddDevice.value = false
    newDeviceId.value = ''
    newDeviceName.value = ''
    newVehicleType.value = ''
    newLineOrSite.value = ''
    newLocation.value = ''
  } catch (error) {
    devicesError.value = error instanceof Error ? error.message : '장비 추가 오류'
  } finally {
    addDeviceLoading.value = false
  }
}

const generateReport = async () => {
  if (!props.incidentId) return null
  reportGenerating.value = true
  try {
    const response = await fetch(`/api/report/quality?incident_id=${props.incidentId}`, {
      method: 'POST'
    })
    if (!response.ok) throw new Error('Failed to generate report')
    const data = await response.json()
    return data.report_url
  } catch (e) {
    alert('보고서 생성 중 오류가 발생했습니다.')
    return null
  } finally {
    reportGenerating.value = false
  }
}

const downloadReport = async () => {
  const url = await generateReport()
  if (url) {
    window.open(url, '_blank')
  }
}

const previewReport = async () => {
  if (previewUrl.value) {
    // If already showing, close preview
    previewUrl.value = null
    return
  }
  const url = await generateReport()
  if (url) {
    previewUrl.value = url
  }
}

const toggleRecording = async () => {
  if (!isRecording.value) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaRecorder = new MediaRecorder(stream)
      audioChunks = []

      mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data)

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunks, { type: 'audio/webm' })
        selectedAudio.value = new File([blob], 'recording.webm', { type: 'audio/webm' })
      }

      mediaRecorder.start()
      isRecording.value = true
    } catch (err) {
      alert('마이크 권한을 허용해 주세요.')
    }
  } else {
    if (mediaRecorder) {
      mediaRecorder.stop()
    }
    isRecording.value = false
  }
}

const onImageChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  selectedImage.value = target.files?.[0] ?? null
}

const onAudioChange = (event: Event) => {
  const target = event.target as HTMLInputElement
  selectedAudio.value = target.files?.[0] ?? null
}

const onSubmit = () => {
  if (!equipmentId.value.trim()) {
    alert('장비 ID를 선택하거나 입력해 주세요.')
    return
  }
  emit('submit', {
    imageFile: selectedImage.value,
    audioFile: selectedAudio.value,
    equipmentId: equipmentId.value.trim(),
  })
}

onMounted(async () => {
  await loadDevices()
  await startMobileSession()
  await pollMobileStatus()
  mobilePollingId.value = window.setInterval(() => {
    pollMobileStatus()
  }, 2500)
})

onUnmounted(() => {
  if (mobilePollingId.value !== null) {
    window.clearInterval(mobilePollingId.value)
    mobilePollingId.value = null
  }
})

watch(mobileHost, (value) => {
  localStorage.setItem(mobileHostStorageKey, value)
  rebuildMobileLink()
})

watch(equipmentId, () => {
  bindMobileSessionEquipment()
})
</script>

<template>
  <main class="enterprise-viewport">
    <div class="background-overlay"></div>

    <section class="console-wrapper">
      <nav class="utility-bar">
        <button class="nav-action-btn" @click="emit('back')">
          <span class="nav-icon-back"></span>
          Back to Dashboard
        </button>
        <div class="system-meta">
          <span class="connection-status">Secure Connection</span>
          <button class="logout-link" @click="emit('logout')">Sign Out</button>
        </div>
      </nav>

      <div class="analysis-module">
        <header class="module-header">
          <div class="indicator-tag">Multimodal Engine v3.0</div>
          <h1 class="module-title">RAG Knowledge Acquisition</h1>
          <p class="module-description">
            정형 및 비정형 데이터를 분석하여 최적의 비즈니스 인텔리전스를 도출합니다.<br>
            참조 이미지와 음성 쿼리를 업로드하거나 직접 녹음하여 프로세스를 시작하십시오.
          </p>
        </header>

        <div class="form-structure">
          <div class="upload-slot">
            <div class="slot-header">
              <label class="slot-label">Mobile Bridge</label>
              <span class="slot-ext status-required">{{ mobileConnected ? 'Connected' : 'Waiting for mobile' }}</span>
            </div>
            <div class="equipment-panel">
              <div class="mobile-meta-line"><strong>Pair Code:</strong> {{ mobileCode || 'N/A' }}</div>
              <div class="mobile-meta-line">
                <strong>Mobile Host(IP:Port):</strong>
                <input
                  class="mobile-host-input"
                  v-model="mobileHost"
                  type="text"
                  placeholder="예: 192.168.0.12:5173"
                />
              </div>
              <div class="mobile-meta-line"><strong>Mobile URL:</strong> <a :href="mobileLink" target="_blank">{{ mobileLink }}</a></div>
              <p v-if="!mobileLink" class="device-error">
                현재 PC가 localhost로 열려 있습니다. 모바일 접속용 IP:PORT를 입력하세요.
              </p>
              <div v-if="mobileQrSrc" class="qr-wrap">
                <img :src="mobileQrSrc" alt="Mobile URL QR" class="qr-image" />
                <p class="qr-caption">스마트폰 카메라로 QR을 스캔해 접속</p>
              </div>
              <div class="mobile-meta-line"><strong>Device:</strong> {{ mobileDeviceLabel || '-' }}</div>
              <div class="mobile-meta-line"><strong>Last Seen:</strong> {{ mobileLastSeen || '-' }}</div>
              <div class="equipment-actions">
                <button class="action-btn-inline" type="button" @click="startMobileSession">New Code</button>
                <button class="action-btn-inline" type="button" :disabled="mobileStatusLoading" @click="pollMobileStatus">
                  {{ mobileStatusLoading ? 'Checking...' : 'Refresh Status' }}
                </button>
              </div>
              <p v-if="mobileStatusError" class="device-error">{{ mobileStatusError }}</p>
            </div>
          </div>

          <div class="upload-slot">
            <div class="slot-header">
              <label class="slot-label">Equipment ID</label>
              <span class="slot-ext status-required">Required</span>
            </div>
            <div class="equipment-panel">
              <input
                class="equipment-input"
                v-model="equipmentId"
                list="equipment-id-options"
                type="text"
                placeholder="장비를 선택하거나 ID 입력"
                required
                @focus="loadDevices"
              />
              <datalist id="equipment-id-options">
                <option v-for="item in deviceOptions" :key="item.device_id" :value="item.device_id">
                  {{ item.device_name || item.device_id }}
                </option>
              </datalist>

              <div class="equipment-actions">
                <button class="action-btn-inline" type="button" @click="showAddDevice = !showAddDevice">
                  {{ showAddDevice ? 'Cancel' : 'Add New Device' }}
                </button>
                <button class="action-btn-inline" type="button" @click="loadDevices" :disabled="devicesLoading">
                  {{ devicesLoading ? 'Loading...' : 'Refresh' }}
                </button>
              </div>

              <div v-if="showAddDevice" class="device-create-form">
                <input v-model="newDeviceId" type="text" placeholder="device_id (예: DEV-NEW-01)" />
                <input v-model="newDeviceName" type="text" placeholder="device_name" />
                <input v-model="newVehicleType" type="text" placeholder="vehicle_type" />
                <input v-model="newLineOrSite" type="text" placeholder="line_or_site" />
                <input v-model="newLocation" type="text" placeholder="location" />
                <button class="action-btn-inline primary" type="button" :disabled="addDeviceLoading" @click="addDevice">
                  {{ addDeviceLoading ? 'Saving...' : 'Save Device' }}
                </button>
              </div>

              <p v-if="devicesError" class="device-error">{{ devicesError }}</p>
            </div>
          </div>

          <div class="upload-slot">
            <div class="slot-header">
              <label class="slot-label">Visual Reference</label>
              <span class="slot-ext">Optional / Image Files</span>
            </div>
            <div class="drop-container" :class="{ 'file-active': selectedImage }">
              <input type="file" accept="image/*" @change="onImageChange" />
              <div class="drop-placeholder">
                <span class="placeholder-text">
                  {{ selectedImage ? selectedImage.name : 'Select or drag visual data' }}
                </span>
                <span class="placeholder-sub" v-if="!selectedImage">Recommended: High-resolution JPG or PNG</span>
              </div>
            </div>
          </div>

          <div class="upload-slot">
            <div class="slot-header">
              <label class="slot-label">Audio Query</label>
              <span class="slot-ext status-required">Required / Record or Upload</span>
            </div>
            
            <div class="audio-controls">
              <button class="record-btn" :class="{ 'is-recording': isRecording }" @click="toggleRecording">
                <span class="record-icon"></span>
                {{ isRecording ? 'Stop Recording' : 'Start Recording' }}
              </button>

              <div class="drop-container highlight-border" :class="{ 'file-active': selectedAudio }">
                <input type="file" accept="audio/*" @change="onAudioChange" />
                <div class="drop-placeholder">
                  <span class="placeholder-text">
                    {{ selectedAudio ? selectedAudio.name : 'Or upload inquiry audio file' }}
                  </span>
                  <span class="placeholder-sub" v-if="!selectedAudio">Sampling rate: 16kHz or higher recommended</span>
                </div>
              </div>
            </div>
          </div>

          <div class="action-footer">
            <button 
              class="primary-execute-btn" 
              :disabled="props.ragLoading || !selectedAudio" 
              @click="onSubmit"
            >
              <div v-if="props.ragLoading" class="spinner"></div>
              <span>{{ props.ragLoading ? 'Processing Request' : 'Execute Analysis' }}</span>
            </button>
          </div>
        </div>

        <transition name="report-fade">
          <div v-if="props.ragMessage" class="report-area">
            <div class="report-header">
              <span class="report-tag">Inference Result</span>
              <div class="report-actions">
                <button 
                  v-if="props.incidentId" 
                  @click="previewReport" 
                  class="action-btn" 
                  :disabled="reportGenerating"
                >
                  <span v-if="reportGenerating" class="spinner-small"></span>
                  {{ previewUrl ? 'Hide Preview' : '👁️ Preview PDF' }}
                </button>
                <button 
                  v-if="props.incidentId" 
                  @click="downloadReport" 
                  class="action-btn" 
                  :disabled="reportGenerating"
                >
                  <span v-if="reportGenerating" class="spinner-small"></span>
                  📄 Download
                </button>
                <span class="timestamp">2026-03-06 | Admin-01</span>
              </div>
            </div>
            <div class="report-body">
              {{ props.ragMessage }}
            </div>
            <div v-if="metricCards.length > 0" class="inference-metrics">
              <div v-for="metric in metricCards" :key="metric.key" class="metric-card">
                <div class="metric-top">
                  <span class="metric-label">{{ metric.label }}</span>
                  <span class="metric-value">{{ metric.value }}</span>
                </div>
                <div class="metric-rail">
                  <div
                    class="metric-fill"
                    :style="{ width: `${(metric.ratio * 100).toFixed(1)}%`, background: metric.color }"
                  ></div>
                </div>
              </div>
            </div>
            
            <div v-if="previewUrl" class="pdf-preview-container">
              <iframe :src="previewUrl" class="pdf-iframe"></iframe>
            </div>
          </div>
        </transition>
      </div>
    </section>
  </main>
</template>

<style scoped>
/* Core Foundation */
.enterprise-viewport {
  min-height: 100vh;
  background-color: #050505;
  color: #e2e8f0;
  font-family: 'Inter', -apple-system, sans-serif;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 20px;
  position: relative;
}

.background-overlay {
  position: absolute;
  top: 0; left: 0; width: 100%; height: 100%;
  background: radial-gradient(at 0% 0%, rgba(37, 99, 235, 0.05) 0, transparent 50%),
              radial-gradient(at 100% 100%, rgba(139, 92, 246, 0.05) 0, transparent 50%);
  pointer-events: none;
}

.console-wrapper {
  width: 100%;
  max-width: 800px;
  z-index: 10;
  min-width: 0;
}

/* Navigation & Status */
.utility-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
}

.nav-action-btn {
  background: none; border: none; color: #64748b;
  font-size: 13px; font-weight: 500; cursor: pointer;
  display: flex; align-items: center; gap: 8px; transition: 0.2s;
}

.nav-action-btn:hover { color: #fff; }

.system-meta { display: flex; align-items: center; gap: 24px; }

.connection-status {
  font-size: 11px; color: #10b981; text-transform: uppercase;
  letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px;
}

.connection-status::before {
  content: ''; width: 6px; height: 6px; background: #10b981; border-radius: 50%;
}

.logout-link {
  background: none; border: none; color: #94a3b8; font-size: 12px;
  cursor: pointer; text-decoration: underline; text-underline-offset: 4px;
}

/* Analysis Module */
.analysis-module {
  background: #0f1115;
  border: 1px solid #1f2937;
  border-radius: 4px;
  padding: 56px;
  box-shadow: 0 40px 100px rgba(0,0,0,0.5);
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
}

.module-header { margin-bottom: 48px; }

.indicator-tag {
  color: #3b82f6; font-size: 11px; font-weight: 700;
  letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 12px;
}

.module-title { font-size: 32px; font-weight: 700; letter-spacing: -0.02em; margin-bottom: 16px; }
.module-description { color: #94a3b8; font-size: 15px; line-height: 1.6; }

/* Form Elements */
.upload-slot { margin-bottom: 32px; }

.slot-header { display: flex; justify-content: space-between; margin-bottom: 12px; }
.slot-label { font-size: 13px; font-weight: 600; color: #f1f5f9; }
.slot-ext { font-size: 11px; color: #475569; }
.status-required { color: #3b82f6; }

.audio-controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.record-btn {
  width: 100%;
  padding: 14px;
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 4px;
  color: #f1f5f9;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: 0.3s;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 10px;
}

.record-btn:hover {
  background: #374151;
}

.record-btn.is-recording {
  background: rgba(239, 68, 68, 0.1);
  border-color: #ef4444;
  color: #ef4444;
  animation: pulse 1.5s infinite;
}

.record-icon {
  width: 12px;
  height: 12px;
  background-color: currentColor;
  border-radius: 50%;
}

.record-btn.is-recording .record-icon {
  border-radius: 2px;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
  70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
  100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
}

.drop-container {
  position: relative; border: 1px solid #1f2937; border-radius: 2px;
  background: #0a0c10; height: 100px; transition: 0.3s;
  display: flex; align-items: center; justify-content: center;
}

.drop-container:hover { border-color: #3b82f6; background: #0e1117; }
.drop-container.file-active { border-color: #3b82f6; background: rgba(59, 130, 246, 0.02); }

.drop-container input {
  position: absolute; width: 100%; height: 100%; opacity: 0; cursor: pointer;
}

.equipment-panel {
  border: 1px solid #1f2937;
  border-radius: 4px;
  background: #0a0c10;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-sizing: border-box;
  min-width: 0;
}

.equipment-input {
  width: 100%;
  background: #0f172a;
  color: #e2e8f0;
  border: 1px solid #334155;
  border-radius: 4px;
  padding: 10px 12px;
  font-size: 14px;
  box-sizing: border-box;
  min-width: 0;
}

.equipment-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.action-btn-inline {
  background: #1f2937;
  border: 1px solid #334155;
  color: #cbd5e1;
  border-radius: 4px;
  font-size: 12px;
  padding: 8px 10px;
  cursor: pointer;
  box-sizing: border-box;
  max-width: 100%;
}

.action-btn-inline.primary {
  background: #1d4ed8;
  border-color: #1d4ed8;
  color: #ffffff;
}

.device-create-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  min-width: 0;
}

.device-create-form input {
  background: #111827;
  color: #e2e8f0;
  border: 1px solid #374151;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
  box-sizing: border-box;
  min-width: 0;
}

.device-error {
  color: #fda4af;
  font-size: 12px;
  margin: 0;
}

.mobile-meta-line {
  font-size: 12px;
  color: #cbd5e1;
  line-height: 1.5;
  word-break: break-all;
}

.mobile-meta-line a {
  color: #93c5fd;
}

.mobile-host-input {
  margin-top: 6px;
  width: 100%;
  box-sizing: border-box;
  background: #0f172a;
  border: 1px solid #334155;
  color: #f8fafc;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 12px;
}

.qr-wrap {
  border: 1px solid #334155;
  border-radius: 6px;
  padding: 10px;
  background: #0f172a;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.qr-image {
  width: 180px;
  height: 180px;
  border-radius: 4px;
  background: #ffffff;
}

.qr-caption {
  margin: 0;
  font-size: 12px;
  color: #cbd5e1;
}

.drop-placeholder { text-align: center; }
.placeholder-text { display: block; font-size: 14px; color: #94a3b8; }
.placeholder-sub { font-size: 11px; color: #475569; margin-top: 4px; display: block; }

/* Execute Button */
.primary-execute-btn {
  width: 100%; padding: 18px; background: #fff; border: none;
  border-radius: 2px; color: #000; font-weight: 700; font-size: 14px;
  text-transform: uppercase; letter-spacing: 0.05em;
  cursor: pointer; transition: 0.3s;
  display: flex; justify-content: center; align-items: center; gap: 12px;
}

.primary-execute-btn:hover:not(:disabled) { background: #3b82f6; color: #fff; }
.primary-execute-btn:disabled { background: #1f2937; color: #475569; cursor: not-allowed; }

/* Report Section */
.report-area {
  margin-top: 48px; padding-top: 40px; border-top: 1px solid #1f2937;
}

.report-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;
}

.report-actions {
  display: flex; align-items: center; gap: 16px;
}

.action-btn {
  background: #1f2937; border: 1px solid #3b82f6; color: #60a5fa;
  padding: 6px 12px; border-radius: 4px; font-size: 11px; font-weight: 600;
  cursor: pointer; transition: 0.2s; display: flex; align-items: center; gap: 6px;
}
.action-btn:hover:not(:disabled) { background: #3b82f6; color: #fff; }
.action-btn:disabled { opacity: 0.5; cursor: not-allowed; border-color: #475569; color: #94a3b8; }

.spinner-small {
  width: 10px; height: 10px; border: 2px solid rgba(255,255,255,0.1);
  border-top-color: currentColor; border-radius: 50%; animation: spin 0.8s linear infinite;
}

.report-tag { font-size: 11px; font-weight: 800; color: #fff; text-transform: uppercase; letter-spacing: 0.05em; }
.timestamp { font-size: 11px; color: #475569; }

.report-body {
  font-size: 15px; line-height: 1.8; color: #cbd5e1;
  background: #0a0c10; padding: 24px; border-radius: 2px;
  white-space: pre-wrap; /* 이 부분을 추가하여 줄바꿈을 유지합니다 */
}

.inference-metrics {
  margin-top: 14px;
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.metric-card {
  border: 1px solid #1f2937;
  border-radius: 4px;
  background: #0b0f16;
  padding: 10px 12px;
}

.metric-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.metric-label {
  font-size: 12px;
  color: #94a3b8;
}

.metric-value {
  font-size: 13px;
  font-weight: 700;
  color: #f8fafc;
}

.metric-rail {
  height: 8px;
  border-radius: 999px;
  background: #1f2937;
  overflow: hidden;
}

.metric-fill {
  height: 100%;
  border-radius: 999px;
}

.pdf-preview-container {
  margin-top: 24px;
  width: 100%;
  height: 600px;
  border: 1px solid #3b82f6;
  border-radius: 4px;
  overflow: hidden;
  background-color: white;
}

.pdf-iframe {
  width: 100%;
  height: 100%;
  border: none;
}

/* Utilities */
.spinner {
  width: 16px; height: 16px; border: 2px solid rgba(0,0,0,0.1);
  border-top-color: #000; border-radius: 50%; animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.report-fade-enter-active { transition: opacity 0.6s, transform 0.6s; }
.report-fade-enter-from { opacity: 0; transform: translateY(10px); }

@media (max-width: 900px) {
  .analysis-module {
    padding: 28px 18px;
  }

  .device-create-form {
    grid-template-columns: 1fr;
  }
}
</style>
