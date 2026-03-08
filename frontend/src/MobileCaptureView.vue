<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  initialCode: string
}>()

const code = ref(props.initialCode || '')
const equipmentId = ref('DEV-MAF-01')
const message = ref('')
const currentCaption = ref('')
const speaking = ref(false)
const isLandscape = ref(window.matchMedia('(orientation: landscape)').matches)

const connecting = ref(false)
const connected = ref(false)
const submitting = ref(false)

const cameraReady = ref(false)
const cameraError = ref('')
const supportsRealtimeMedia = ref(true)
const videoRef = ref<HTMLVideoElement | null>(null)
let cameraStream: MediaStream | null = null

const capturedImageFile = ref<File | null>(null)
const capturedImagePreview = ref('')

const audioReady = ref(false)
const isRecording = ref(false)
const audioError = ref('')
const recordedAudioFile = ref<File | null>(null)
let audioStream: MediaStream | null = null
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []
let orientationQuery: MediaQueryList | null = null
let orientationHandler: (() => void) | null = null
let captionTimer: number | null = null

const deviceLabel = `Smartphone-${navigator.platform || 'mobile'}`
const imageFallbackRef = ref<HTMLInputElement | null>(null)
const audioFallbackRef = ref<HTMLInputElement | null>(null)

const connectSession = async () => {
  if (!code.value.trim()) {
    message.value = '페어링 코드를 입력해 주세요.'
    return
  }
  connecting.value = true
  message.value = ''
  try {
    const response = await fetch('/api/mobile/session/connect', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        code: code.value.trim(),
        device_label: deviceLabel,
      }),
    })
    if (!response.ok) {
      throw new Error(`연결 실패 (${response.status})`)
    }
    connected.value = true
    message.value = '연결 완료. 카메라/마이크 캡처 후 전송하세요.'
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    message.value = `세션 연결 오류: ${errorMessage}`
  } finally {
    connecting.value = false
  }
}

const startCamera = async () => {
  cameraError.value = ''
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    supportsRealtimeMedia.value = false
    cameraReady.value = false
    cameraError.value = '실시간 카메라 접근을 지원하지 않는 환경입니다. 아래 파일 캡처를 사용하세요.'
    return
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: 'environment' },
      },
      audio: false,
    })
    if (videoRef.value) {
      videoRef.value.srcObject = cameraStream
      await videoRef.value.play()
      cameraReady.value = true
    }
  } catch (error) {
    cameraReady.value = false
    cameraError.value = error instanceof Error ? error.message : '카메라 접근 실패'
  }
}

const stopCamera = () => {
  if (cameraStream) {
    cameraStream.getTracks().forEach((t) => t.stop())
    cameraStream = null
  }
  cameraReady.value = false
}

const capturePhoto = () => {
  if (!videoRef.value) return
  const video = videoRef.value
  const width = video.videoWidth || 1280
  const height = video.videoHeight || 720

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, width, height)

  const dataUrl = canvas.toDataURL('image/jpeg', 0.92)
  capturedImagePreview.value = dataUrl

  canvas.toBlob((blob) => {
    if (!blob) return
    capturedImageFile.value = new File([blob], `capture_${Date.now()}.jpg`, { type: 'image/jpeg' })
  }, 'image/jpeg', 0.92)
}

const clearPhoto = () => {
  capturedImageFile.value = null
  capturedImagePreview.value = ''
}

const initAudio = async () => {
  audioError.value = ''
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    supportsRealtimeMedia.value = false
    audioReady.value = false
    audioError.value = '실시간 마이크 접근을 지원하지 않는 환경입니다. 아래 음성 파일 캡처를 사용하세요.'
    return
  }
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    audioReady.value = true
  } catch (error) {
    audioReady.value = false
    audioError.value = error instanceof Error ? error.message : '마이크 접근 실패'
  }
}

const startRecording = () => {
  if (!audioStream) {
    audioError.value = '마이크 초기화가 필요합니다.'
    return
  }
  audioChunks = []
  mediaRecorder = new MediaRecorder(audioStream)
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) {
      audioChunks.push(e.data)
    }
  }
  mediaRecorder.onstop = () => {
    const blob = new Blob(audioChunks, { type: 'audio/webm' })
    recordedAudioFile.value = new File([blob], `voice_${Date.now()}.webm`, { type: 'audio/webm' })
  }
  mediaRecorder.start()
  isRecording.value = true
}

const stopRecording = () => {
  if (mediaRecorder && isRecording.value) {
    mediaRecorder.stop()
  }
  isRecording.value = false
}

const onFallbackImage = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0] ?? null
  if (!file) return
  capturedImageFile.value = file
  const reader = new FileReader()
  reader.onload = () => {
    capturedImagePreview.value = typeof reader.result === 'string' ? reader.result : ''
  }
  reader.readAsDataURL(file)
}

const onFallbackAudio = (event: Event) => {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0] ?? null
  if (!file) return
  recordedAudioFile.value = file
}

const stopSpeech = () => {
  if (captionTimer !== null) {
    window.clearTimeout(captionTimer)
    captionTimer = null
  }
  if ('speechSynthesis' in window) {
    window.speechSynthesis.cancel()
  }
  speaking.value = false
  currentCaption.value = ''
}

const extractActionLines = (steps: string[], explanation: string) => {
  const normalizedSteps = steps.map((s) => s.trim()).filter((s) => !!s)
  if (normalizedSteps.length > 0) {
    return normalizedSteps
  }

  const banTokens = ['[조치 절차]', '조치 절차', 'Action', 'Description', '상세 조치 내용은 아래 분석 결과를 확인하세요.']
  const lines = explanation
    .split(/\r?\n/)
    .map((line) => line.replace(/[*#`>-]/g, '').trim())
    .filter((line) => !!line && !banTokens.some((token) => line.includes(token)))

  const unique: string[] = []
  for (const line of lines) {
    if (!unique.includes(line)) {
      unique.push(line)
    }
  }
  return unique.slice(0, 6)
}

const playCaptionOnly = (lines: string[]) => {
  if (lines.length === 0) {
    return
  }
  let index = 0
  speaking.value = true

  const next = () => {
    if (index >= lines.length) {
      speaking.value = false
      if (!isLandscape.value) {
        currentCaption.value = ''
      }
      return
    }
    currentCaption.value = lines[index] ?? ''
    index += 1
    captionTimer = window.setTimeout(next, 2200)
  }
  next()
}

const speakActionSteps = (steps: string[], explanation: string) => {
  const queue = extractActionLines(steps, explanation)
  if (queue.length === 0) {
    currentCaption.value = ''
    speaking.value = false
    return
  }

  if (!('speechSynthesis' in window)) {
    playCaptionOnly(queue)
    return
  }

  stopSpeech()
  let index = 0

  const speakNext = () => {
    if (index >= queue.length) {
      speaking.value = false
      if (!isLandscape.value) {
        currentCaption.value = ''
      }
      return
    }

    const line = queue[index] ?? ''
    if (!line) {
      index += 1
      speakNext()
      return
    }
    currentCaption.value = line
    speaking.value = true

    const utterance = new SpeechSynthesisUtterance(line)
    utterance.lang = 'ko-KR'
    utterance.rate = 1.0
    utterance.pitch = 1.0
    utterance.onend = () => {
      index += 1
      speakNext()
    }
    utterance.onerror = () => {
      index += 1
      speakNext()
    }
    window.speechSynthesis.speak(utterance)
  }

  speakNext()
}

const submitPayload = async () => {
  if (!connected.value) {
    message.value = '먼저 페어링 연결을 완료해 주세요.'
    return
  }
  if (!recordedAudioFile.value) {
    message.value = '음성을 녹음해 주세요.'
    return
  }

  submitting.value = true
  message.value = ''

  const formData = new FormData()
  formData.append('equipment_id', equipmentId.value.trim() || 'DEV-MAF-01')
  formData.append('audio', recordedAudioFile.value)
  if (capturedImageFile.value) {
    formData.append('image', capturedImageFile.value)
  }

  try {
    const response = await fetch(`/api/mobile/session/${code.value.trim().toUpperCase()}/submit`, {
      method: 'POST',
      body: formData,
    })
    if (!response.ok) {
      throw new Error(`전송 실패 (${response.status})`)
    }
    const data = await response.json()
    const steps = Array.isArray(data?.action_steps) ? data.action_steps.map((s: unknown) => String(s)) : []
    const explanation = typeof data?.explanation === 'string' ? data.explanation : ''
    const lines = extractActionLines(steps, explanation)
    if (lines.length === 0) {
      message.value = '전송 완료. 안내할 조치 문장을 찾지 못했습니다.'
      stopSpeech()
      currentCaption.value = ''
    } else {
      message.value = '전송 완료. 조치 절차를 음성/자막으로 안내합니다.'
      speakActionSteps(steps, explanation)
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    message.value = `전송 오류: ${errorMessage}`
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  orientationQuery = window.matchMedia('(orientation: landscape)')
  orientationHandler = () => {
    isLandscape.value = orientationQuery ? orientationQuery.matches : false
    if (!isLandscape.value && !speaking.value) {
      currentCaption.value = ''
    }
  }
  if (orientationQuery.addEventListener && orientationHandler) {
    orientationQuery.addEventListener('change', orientationHandler)
  } else {
    orientationQuery.addListener(orientationHandler as EventListener)
  }

  if (code.value.trim()) {
    await connectSession()
  }
  await startCamera()
  await initAudio()

  orientationHandler()
})

onUnmounted(() => {
  stopSpeech()
  stopCamera()
  if (audioStream) {
    audioStream.getTracks().forEach((t) => t.stop())
    audioStream = null
  }
  if (orientationQuery) {
    if (orientationQuery.removeEventListener && orientationHandler) {
      orientationQuery.removeEventListener('change', orientationHandler)
    } else {
      orientationQuery.removeListener(orientationHandler as EventListener)
    }
  }
})
</script>

<template>
  <main class="mobile-page">
    <section class="mobile-card">
      <h1>Smart Glass Mobile Capture</h1>
      <p class="subtitle">페어링 코드와 장비 ID만 설정 후, 바로 촬영/녹음해서 전송</p>

      <div class="row2">
        <div>
          <label>Pair Code</label>
          <input v-model="code" type="text" placeholder="A1B2C3" />
        </div>
        <div>
          <label>Equipment ID</label>
          <input v-model="equipmentId" type="text" placeholder="DEV-MAF-01" />
        </div>
      </div>

      <button class="btn" :disabled="connecting" @click="connectSession">
        {{ connecting ? 'Connecting...' : connected ? 'Connected' : 'Connect Pairing' }}
      </button>

      <div class="capture-layout">
        <section class="capture-box camera-main">
          <h2>Camera</h2>
          <video v-if="supportsRealtimeMedia" ref="videoRef" class="camera" playsinline muted autoplay></video>
          <div v-if="isLandscape && currentCaption" class="caption-line">{{ currentCaption }}</div>
          <div v-if="!supportsRealtimeMedia" class="fallback-box">
            <button class="btn" @click="imageFallbackRef?.click()">Open Camera / Choose Image</button>
            <input ref="imageFallbackRef" type="file" accept="image/*" capture="environment" @change="onFallbackImage" />
          </div>
          <p v-if="cameraError" class="error">{{ cameraError }}</p>
          <div v-if="supportsRealtimeMedia" class="actions">
            <button class="btn" :disabled="!cameraReady" @click="capturePhoto">Capture</button>
            <button class="btn" :disabled="!capturedImageFile" @click="clearPhoto">Clear Photo</button>
          </div>
          <img v-if="capturedImagePreview" :src="capturedImagePreview" class="preview" alt="captured" />
        </section>

        <div class="side-panel">
          <section class="capture-box">
            <h2>Audio</h2>
            <p v-if="audioError" class="error">{{ audioError }}</p>
            <div v-if="supportsRealtimeMedia" class="actions">
              <button class="btn" :disabled="!audioReady || isRecording" @click="startRecording">Start Record</button>
              <button class="btn" :disabled="!isRecording" @click="stopRecording">Stop Record</button>
            </div>
            <div v-else class="fallback-box">
              <button class="btn" @click="audioFallbackRef?.click()">Open Mic / Choose Audio</button>
              <input ref="audioFallbackRef" type="file" accept="audio/*" capture @change="onFallbackAudio" />
            </div>
            <p class="hint">{{ recordedAudioFile ? recordedAudioFile.name : '아직 녹음 파일 없음' }}</p>
          </section>

          <button class="btn primary send-btn" :disabled="submitting || !connected" @click="submitPayload">
            {{ submitting ? 'Submitting...' : 'Send To AI Server' }}
          </button>

          <p v-if="message" class="message">{{ message }}</p>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.mobile-page {
  min-height: 100vh;
  background: #0b1220;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
}

.mobile-card {
  width: 100%;
  max-width: 520px;
  background: #111827;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 14px;
  color: #e5e7eb;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-sizing: border-box;
}

.subtitle {
  margin: 0;
  color: #93c5fd;
  font-size: 12px;
}

.row2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

label {
  display: block;
  font-size: 12px;
  color: #cbd5e1;
  margin-bottom: 4px;
}

input {
  width: 100%;
  box-sizing: border-box;
  background: #0f172a;
  border: 1px solid #334155;
  color: #f8fafc;
  border-radius: 6px;
  padding: 10px;
}

.capture-box {
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 10px;
  background: #0f172a;
}

.capture-layout {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.camera-main {
  min-height: 260px;
  position: relative;
}

.capture-box h2 {
  margin: 0 0 8px 0;
  font-size: 14px;
}

.fallback-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fallback-box input {
  display: none;
}

.camera {
  width: 100%;
  height: 260px;
  border-radius: 8px;
  background: #020617;
  object-fit: cover;
}

.caption-line {
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 18px;
  background: rgba(2, 6, 23, 0.72);
  color: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.45);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preview {
  margin-top: 8px;
  width: 100%;
  border-radius: 8px;
}

.actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.btn {
  border: 1px solid #334155;
  background: #1f2937;
  color: #f8fafc;
  border-radius: 6px;
  padding: 10px;
  font-size: 13px;
}

.btn.primary {
  background: #2563eb;
  border-color: #2563eb;
}

.send-btn {
  width: 100%;
}

.error {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #fda4af;
}

.hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #bfdbfe;
}

.message {
  margin: 0;
  font-size: 12px;
  color: #a7f3d0;
}

@media (max-width: 560px) {
  .row2 {
    grid-template-columns: 1fr;
  }
}

@media (orientation: landscape) and (min-width: 700px) {
  .mobile-page {
    padding: 8px;
    align-items: stretch;
  }

  .mobile-card {
    max-width: 1100px;
    height: calc(100vh - 16px);
    overflow: auto;
  }

  .capture-layout {
    flex-direction: row;
    align-items: stretch;
    gap: 12px;
    min-height: 420px;
  }

  .camera-main {
    flex: 1.9;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .camera {
    flex: 1;
    height: auto;
    min-height: 300px;
    max-height: 56vh;
  }

  .side-panel {
    flex: 1;
    min-width: 320px;
  }
}
</style>
