<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  initialCode: string
}>()

const code = ref(props.initialCode || '')
const pairedEquipmentId = ref('')
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
const recordingSeconds = ref(0)
let audioStream: MediaStream | null = null
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []
let orientationQuery: MediaQueryList | null = null
let orientationHandler: (() => void) | null = null
let captionTimer: number | null = null
let recordingTimerId: number | null = null
let activeAudio: HTMLAudioElement | null = null
let speechSessionId = 0

const deviceLabel = `Smartphone-${navigator.platform || 'mobile'}`
const imageFallbackRef = ref<HTMLInputElement | null>(null)
const audioFallbackRef = ref<HTMLInputElement | null>(null)
const secureContextOk = computed(() => window.isSecureContext || ['localhost', '127.0.0.1'].includes(window.location.hostname))
const urlProtocol = computed(() => window.location.protocol)
const iosLikeBrowser = computed(() => /iPhone|iPad|iPod/i.test(navigator.userAgent))
const mediaBusyHint = ref('')
const fallbackNotice = computed(() => {
  const notices: string[] = []
  if (cameraError.value) {
    notices.push(`카메라: ${cameraError.value}`)
  }
  if (audioError.value) {
    notices.push(`마이크: ${audioError.value}`)
  }
  return notices.join(' / ')
})

const previewChecks = computed(() => [
  { label: `접속 프로토콜: ${urlProtocol.value}`, ok: secureContextOk.value, hint: secureContextOk.value ? '보안 컨텍스트 OK' : 'HTTPS(또는 localhost) 필요' },
  { label: '카메라 시작 방식', ok: true, hint: 'Start Camera Preview 버튼 클릭 후 실행' },
  { label: 'video 속성', ok: true, hint: 'autoplay / playsinline / muted 적용' },
  { label: 'iPhone 브라우저 제약', ok: true, hint: iosLikeBrowser.value ? 'Safari/Chrome/Firefox 동일 WebKit 제약 적용' : '일반 모바일 브라우저 제약 적용' },
  { label: '카메라 점유 상태', ok: !mediaBusyHint.value, hint: mediaBusyHint.value || '점유 오류 감지 안 됨' },
  { label: '권한 상태', ok: !cameraError.value.toLowerCase().includes('denied') && !cameraError.value.toLowerCase().includes('notallowed'), hint: '거부 이력 시 브라우저 설정에서 카메라/마이크 재허용' },
])

const mapMediaError = (error: unknown, target: 'camera' | 'audio') => {
  const err = error as DOMException
  const name = err?.name || 'UnknownError'
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return `${target === 'camera' ? '카메라' : '마이크'} 권한이 거부되었습니다. 브라우저 설정에서 다시 허용하세요.`
  }
  if (name === 'NotReadableError' || name === 'TrackStartError') {
    mediaBusyHint.value = '다른 앱/탭이 카메라를 사용 중일 수 있습니다.'
    return `${target === 'camera' ? '카메라' : '마이크'} 장치를 점유 중인 앱이 있습니다. 다른 앱을 닫고 다시 시도하세요.`
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return `${target === 'camera' ? '카메라' : '마이크'} 장치를 찾지 못했습니다.`
  }
  if (name === 'OverconstrainedError' || name === 'ConstraintNotSatisfiedError') {
    return '요청한 미디어 조건을 만족하지 못했습니다.'
  }
  return err?.message || `${target === 'camera' ? '카메라' : '마이크'} 접근 실패`
}

const formatRecordingTime = (seconds: number) => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

const startRecordingTimer = () => {
  if (recordingTimerId !== null) {
    window.clearInterval(recordingTimerId)
  }
  recordingSeconds.value = 0
  recordingTimerId = window.setInterval(() => {
    recordingSeconds.value += 1
  }, 1000)
}

const stopRecordingTimer = () => {
  if (recordingTimerId !== null) {
    window.clearInterval(recordingTimerId)
    recordingTimerId = null
  }
}

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
    const data = await response.json()
    pairedEquipmentId.value = String(data?.equipment_id ?? '')
    connected.value = true
    message.value = pairedEquipmentId.value
      ? `연결 완료. 바인딩 장비: ${pairedEquipmentId.value}`
      : '연결 완료. PC에서 장비를 먼저 선택해 주세요.'
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error'
    message.value = `세션 연결 오류: ${errorMessage}`
  } finally {
    connecting.value = false
  }
}

const startCamera = async () => {
  cameraError.value = ''
  mediaBusyHint.value = ''
  if (!secureContextOk.value) {
    supportsRealtimeMedia.value = false
    cameraReady.value = false
    cameraError.value = 'HTTPS(또는 localhost) 환경에서만 카메라 프리뷰가 동작합니다.'
    return
  }
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
    cameraError.value = mapMediaError(error, 'camera')
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
  if (!secureContextOk.value) {
    supportsRealtimeMedia.value = false
    audioReady.value = false
    audioError.value = 'HTTPS(또는 localhost) 환경에서만 마이크 프리뷰가 동작합니다.'
    return
  }
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
    // iOS/WebKit 일부 환경에서 audio-only 요청이 실패할 수 있어 video+audio로 재시도
    try {
      const combined = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: true,
      })
      const audioTracks = combined.getAudioTracks()
      const videoTracks = combined.getVideoTracks()

      if (videoTracks.length > 0 && videoRef.value) {
        stopCamera()
        cameraStream = new MediaStream(videoTracks)
        videoRef.value.srcObject = cameraStream
        await videoRef.value.play()
        cameraReady.value = true
      }

      if (audioTracks.length > 0) {
        audioStream = new MediaStream(audioTracks)
        audioReady.value = true
        audioError.value = ''
      } else {
        audioReady.value = false
        audioError.value = '마이크 트랙을 가져오지 못했습니다.'
      }
    } catch (retryError) {
      audioReady.value = false
      audioError.value = mapMediaError(retryError, 'audio')
    }
  }
}

const startRecording = async () => {
  if (typeof MediaRecorder === 'undefined') {
    audioError.value = '현재 브라우저는 실시간 녹음을 지원하지 않습니다. Open Mic / Choose Audio를 사용하세요.'
    return
  }
  if (!audioStream) {
    await initAudio()
  }
  if (!audioStream) {
    audioError.value = audioError.value || '마이크 접근에 실패했습니다. 권한을 확인해 주세요.'
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
    stopRecordingTimer()
    isRecording.value = false
  }
  mediaRecorder.onerror = () => {
    stopRecordingTimer()
    isRecording.value = false
  }
  mediaRecorder.start()
  isRecording.value = true
  startRecordingTimer()
}

const stopRecording = () => {
  if (mediaRecorder && isRecording.value) {
    mediaRecorder.stop()
  }
  stopRecordingTimer()
}

const toggleRecording = async () => {
  if (isRecording.value) {
    stopRecording()
    return
  }
  await startRecording()
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
  speechSessionId += 1
  if (captionTimer !== null) {
    window.clearTimeout(captionTimer)
    captionTimer = null
  }
  if (activeAudio) {
    activeAudio.pause()
    activeAudio.src = ''
    activeAudio = null
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

const playAudioBlob = (blob: Blob): Promise<void> =>
  new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob)
    const audio = new Audio(url)
    activeAudio = audio
    audio.onended = () => {
      URL.revokeObjectURL(url)
      if (activeAudio === audio) activeAudio = null
      resolve()
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      if (activeAudio === audio) activeAudio = null
      reject(new Error('audio_playback_error'))
    }
    audio.play().catch((err) => {
      URL.revokeObjectURL(url)
      if (activeAudio === audio) activeAudio = null
      reject(err)
    })
  })

const speakWithServerTTS = async (lines: string[]) => {
  const mySession = ++speechSessionId
  speaking.value = true
  for (const line of lines) {
    if (mySession !== speechSessionId) return
    currentCaption.value = line
    const response = await fetch('/api/mobile/tts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ text: line }),
    })
    if (!response.ok) {
      throw new Error(`TTS 요청 실패 (${response.status})`)
    }
    const blob = await response.blob()
    if (!blob.size) {
      throw new Error('빈 오디오 응답')
    }
    await playAudioBlob(blob)
  }
  if (mySession === speechSessionId) {
    speaking.value = false
    if (!isLandscape.value) currentCaption.value = ''
  }
}

const speakActionSteps = (steps: string[], explanation: string) => {
  const queue = extractActionLines(steps, explanation)
  if (queue.length === 0) {
    currentCaption.value = ''
    speaking.value = false
    return
  }

  stopSpeech()
  void speakWithServerTTS(queue).catch(() => {
    if (!('speechSynthesis' in window)) {
      playCaptionOnly(queue)
      return
    }

    let index = 0
    const speakNext = () => {
      if (index >= queue.length) {
        speaking.value = false
        if (!isLandscape.value) currentCaption.value = ''
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
  })
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
  if (!pairedEquipmentId.value.trim()) {
    message.value = 'PC에서 장비를 선택한 뒤 새 페어링 코드를 생성해 주세요.'
    return
  }

  submitting.value = true
  message.value = ''

  const formData = new FormData()
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
    pairedEquipmentId.value = String(data?.equipment_id ?? pairedEquipmentId.value)
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
  // iOS/WebKit 환경 제약 대응: 사용자 버튼 클릭 후 카메라 시작
  // 마이크도 사용자 제스처(버튼 클릭) 후 initAudio를 호출하도록 변경

  orientationHandler()
})

onUnmounted(() => {
  stopSpeech()
  stopCamera()
  stopRecordingTimer()
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
  <main class="mobile-page" :class="{ landscape: isLandscape }">
    <section class="mobile-card" :class="{ landscape: isLandscape }">
      <h1>Smart Glass Mobile Capture</h1>
      <p class="subtitle">페어링 코드로 연결 후, PC에서 선택한 장비로 바로 촬영/녹음 전송</p>

      <div class="session-strip">
        <div class="row2">
          <div>
            <label>Pair Code</label>
            <input v-model="code" type="text" placeholder="A1B2C3" />
          </div>
        </div>

        <div class="pair-meta">
          <strong>Bound Equipment:</strong> {{ pairedEquipmentId || 'Not assigned' }}
        </div>

        <button class="btn connect-btn" :disabled="connecting" @click="connectSession">
          {{ connecting ? 'Connecting...' : connected ? 'Connected' : 'Connect Pairing' }}
        </button>
      </div>

      <div class="capture-layout" :class="{ landscape: isLandscape }">
        <section class="capture-box camera-main">
          <h2>Camera</h2>
          <div v-if="!cameraReady" class="camera-boot">
            <button class="btn primary" @click="startCamera">Start Camera Preview</button>
          </div>
          <video v-if="supportsRealtimeMedia" ref="videoRef" class="camera" playsinline muted autoplay></video>
          <div v-if="isLandscape && currentCaption" class="caption-line">{{ currentCaption }}</div>
          <p v-if="cameraError && !isLandscape" class="error">{{ cameraError }}</p>
          <div v-if="supportsRealtimeMedia" class="actions">
            <button class="btn" :disabled="!cameraReady" @click="capturePhoto">Capture</button>
            <button class="btn" :disabled="!capturedImageFile" @click="clearPhoto">Clear Photo</button>
          </div>
          <img v-if="capturedImagePreview" :src="capturedImagePreview" class="preview" alt="captured" />
        </section>

        <div class="side-panel">
          <section class="capture-box compact-controls">
            <h2>Control Panel</h2>
            <div v-if="supportsRealtimeMedia" class="actions compact-stack">
              <p class="panel-group">ACCESS</p>
              <button class="btn btn-access" @click="startCamera">Camera Access</button>
              <button class="btn btn-access" @click="initAudio">Mic Access</button>
              <p class="panel-group">CAPTURE</p>
              <button class="btn btn-capture" :disabled="!cameraReady" @click="capturePhoto">Capture Photo</button>
              <button class="btn btn-neutral" :disabled="!capturedImageFile" @click="clearPhoto">Clear Photo</button>
              <p class="panel-group">AUDIO</p>
              <button
                class="btn"
                :class="isRecording ? 'btn-stop' : 'btn-record'"
                @click="toggleRecording"
              >
                {{ isRecording ? `Stop Recording (${formatRecordingTime(recordingSeconds)})` : 'Start Recording' }}
              </button>
            </div>
            <div v-else class="fallback-box compact-stack">
              <button class="btn btn-access" @click="imageFallbackRef?.click()">Choose Image</button>
              <input ref="imageFallbackRef" type="file" accept="image/*" capture="environment" @change="onFallbackImage" />
              <button class="btn btn-access" @click="audioFallbackRef?.click()">Choose Audio</button>
              <input ref="audioFallbackRef" type="file" accept="audio/*" capture @change="onFallbackAudio" />
            </div>

            <p v-if="fallbackNotice" class="error compact-error">{{ fallbackNotice }}</p>
            <p class="hint">{{ capturedImageFile ? `이미지: ${capturedImageFile.name}` : '캡처 이미지 없음' }}</p>
            <p class="hint">{{ recordedAudioFile ? recordedAudioFile.name : '아직 녹음 파일 없음' }}</p>

            <button class="btn primary send-btn btn-send" :disabled="submitting || !connected" @click="submitPayload">
              {{ submitting ? 'Submitting...' : 'Send To AI Server' }}
            </button>

            <p v-if="message" class="message">{{ message }}</p>
          </section>
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

.mobile-page.landscape {
  background: #000;
  padding: 0;
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

.mobile-card.landscape {
  max-width: none;
  width: 100%;
  height: 100vh;
  border-radius: 0;
  border: none;
  background: #000;
  padding: 0;
  gap: 0;
  overflow: hidden;
  position: relative;
}

.subtitle {
  margin: 0;
  color: #93c5fd;
  font-size: 12px;
}

.row2 {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.session-strip {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.pair-meta {
  font-size: 12px;
  color: #cbd5e1;
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
  min-height: 0;
}

.side-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.camera-main {
  min-height: 260px;
  position: relative;
  overflow: hidden;
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

.camera-boot {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 6;
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

.compact-controls {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel-group {
  margin: 6px 0 0;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: #94a3b8;
}

.btn.btn-access {
  background: #1e3a8a;
  border-color: #1d4ed8;
}

.btn.btn-capture {
  background: #0369a1;
  border-color: #0ea5e9;
}

.btn.btn-record {
  background: #7c2d12;
  border-color: #f97316;
}

.btn.btn-stop {
  background: #7f1d1d;
  border-color: #ef4444;
}

.btn.btn-neutral {
  background: #1f2937;
  border-color: #475569;
}

.btn.btn-send {
  background: #16a34a;
  border-color: #16a34a;
  color: #f8fafc;
}

.compact-stack {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
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
    padding: 0;
    align-items: stretch;
  }

  .mobile-card {
    max-width: none;
    width: 100%;
    height: 100vh;
    border-radius: 0;
    border: none;
    background: #000;
    padding: 0;
    gap: 0;
    overflow: hidden;
  }

  .mobile-card > h1,
  .mobile-card > .subtitle {
    display: none;
  }

  .session-strip {
    position: absolute;
    top: 8px;
    left: 10px;
    right: 10px;
    z-index: 30;
    display: grid;
    grid-template-columns: minmax(180px, 280px) minmax(0, 1fr) auto;
    gap: 10px;
    align-items: center;
    background: rgba(2, 6, 23, 0.64);
    border: 1px solid rgba(148, 163, 184, 0.26);
    border-radius: 12px;
    padding: 8px 10px;
    backdrop-filter: blur(7px);
    min-height: 56px;
  }

  .session-strip .row2 {
    gap: 0;
  }

  .session-strip label {
    font-size: 11px;
    margin-bottom: 2px;
  }

  .session-strip input {
    height: 34px;
    padding: 6px 10px;
  }

  .session-strip .pair-meta {
    margin: 0;
    font-size: 12px;
    color: #dbeafe;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .connect-btn {
    height: 36px;
    padding: 0 14px;
    white-space: nowrap;
  }

  .capture-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 240px;
    gap: 10px;
    height: 100vh;
    min-height: 0;
    padding: 74px 8px 8px;
    box-sizing: border-box;
    align-items: stretch;
  }

  .camera-main {
    min-height: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid rgba(148, 163, 184, 0.24);
    border-radius: 12px;
    background: #000;
    padding: 0;
  }

  .camera-main h2 {
    display: none;
  }

  .camera-boot {
    top: 10px;
    left: 10px;
  }

  .camera {
    width: 100%;
    height: 100%;
    min-height: 0;
    max-height: none;
    border-radius: 0;
    object-fit: cover;
  }

  .side-panel {
    min-width: 240px;
    min-height: 0;
    height: 100%;
    max-height: 100%;
    background: rgba(2, 6, 23, 0.78);
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 12px;
    padding: 8px;
    overflow: auto;
    box-sizing: border-box;
  }

  .camera-main .actions {
    display: none;
  }

  .preview {
    display: none;
  }

  .caption-line {
    bottom: 14px;
    border-radius: 10px;
    font-size: 14px;
  }

  .compact-controls {
    border-radius: 10px;
    padding: 10px;
    background: rgba(15, 23, 42, 0.86);
  }

  .compact-controls h2 {
    font-size: 12px;
    margin-bottom: 6px;
    text-transform: uppercase;
    color: #93c5fd;
    letter-spacing: 0.06em;
  }

  .compact-controls .btn {
    padding: 9px 10px;
    font-size: 12px;
  }

  .compact-controls .hint,
  .compact-controls .message,
  .compact-controls .error {
    font-size: 11px;
  }

  .compact-error {
    line-height: 1.4;
  }
}
</style>
