<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  ragLoading: boolean
  ragMessage: string
}>()

const emit = defineEmits<{
  submit: [{ imageFile: File | null; audioFile: File | null }]
  back: []
  logout: []
}>()

const selectedImage = ref<File | null>(null)
const selectedAudio = ref<File | null>(null)

const isRecording = ref(false)
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []

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
  emit('submit', { imageFile: selectedImage.value, audioFile: selectedAudio.value })
}
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
              <span class="timestamp">2026-03-06 | Admin-01</span>
            </div>
            <div class="report-body">
              {{ props.ragMessage }}
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
  display: flex; justify-content: space-between; margin-bottom: 20px;
}

.report-tag { font-size: 11px; font-weight: 800; color: #fff; text-transform: uppercase; letter-spacing: 0.05em; }
.timestamp { font-size: 11px; color: #475569; }

.report-body {
  font-size: 15px; line-height: 1.8; color: #cbd5e1;
  background: #0a0c10; padding: 24px; border-radius: 2px;
  white-space: pre-wrap; /* 이 부분을 추가하여 줄바꿈을 유지합니다 */
}

/* Utilities */
.spinner {
  width: 16px; height: 16px; border: 2px solid rgba(0,0,0,0.1);
  border-top-color: #000; border-radius: 50%; animation: spin 0.8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.report-fade-enter-active { transition: opacity 0.6s, transform 0.6s; }
.report-fade-enter-from { opacity: 0; transform: translateY(10px); }
</style>