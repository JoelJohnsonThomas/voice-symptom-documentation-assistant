/**
 * VoxDoc - Voice Symptom Intake & Documentation Assistant
 * Dark Theme Edition - JavaScript Controller
 *
 * Features:
 * - Real-time streaming transcription via WebSocket
 * - Text input fallback for manual symptom entry
 * - SOAP note generation with MedGemma
 */

// =====================================================
// DOM ELEMENTS
// =====================================================
const elements = {
    // Sidebar
    sidebar: document.getElementById('sidebar'),
    sidebarOverlay: document.getElementById('sidebarOverlay'),
    openSidebarBtn: document.getElementById('openSidebar'),
    closeSidebarBtn: document.getElementById('closeSidebar'),

    // Voice Recording
    recordBtn: document.getElementById('recordBtn'),
    recordRipple: document.getElementById('recordRipple'),
    micIcon: document.getElementById('micIcon'),
    stopIcon: document.getElementById('stopIcon'),
    waveformContainer: document.getElementById('waveformContainer'),
    voiceStatus: document.getElementById('voiceStatus'),
    durationDisplay: document.getElementById('durationDisplay'),
    recordingTime: document.getElementById('recordingTime'),

    // Text Input
    textInput: document.getElementById('textInput'),

    // Submit
    submitBtn: document.getElementById('submitBtn'),

    // Transcript Panel
    transcriptCard: document.getElementById('transcriptCard'),
    transcriptTitle: document.getElementById('transcriptTitle'),
    liveIndicator: document.getElementById('liveIndicator'),
    emptyState: document.getElementById('emptyState'),
    loadingState: document.getElementById('loadingState'),
    resultsContainer: document.getElementById('resultsContainer'),

    // Live Transcript (Streaming)
    liveTranscriptState: document.getElementById('liveTranscriptState'),
    liveTranscriptText: document.getElementById('liveTranscriptText'),

    // Results
    transcriptionText: document.getElementById('transcriptionText'),
    chiefComplaint: document.getElementById('chiefComplaint'),
    symptomDetails: document.getElementById('symptomDetails'),
    soapNote: document.getElementById('soapNote'),
    audioPlaybackSection: document.getElementById('audioPlaybackSection'),
    resultAudioPlayer: document.getElementById('resultAudioPlayer'),
    textInputIndicator: document.getElementById('textInputIndicator'),

    // Actions
    copyBtn: document.getElementById('copyBtn'),
    exportBtn: document.getElementById('exportBtn')
};

// =====================================================
// STATE
// =====================================================
const state = {
    isRecording: false,
    mediaRecorder: null,
    audioChunks: [],
    audioBlob: null,
    audioUrl: null,
    recordingStartTime: null,
    recordingInterval: null,
    currentDocumentation: null,

    // WebSocket streaming state
    websocket: null,
    liveTranscript: '',
    wsConnected: false,
    streamingMode: true  // true = use WebSocket streaming, false = fallback to upload
};

// =====================================================
// WEBSOCKET STREAMING
// =====================================================

/**
 * Build the WebSocket URL from current page location.
 * Handles both local dev (ws://) and ngrok/production (wss://).
 */
function getWebSocketUrl() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws/transcribe`;
}

/**
 * Connect to the WebSocket streaming endpoint.
 * Returns a promise that resolves when the connection is ready.
 */
function connectWebSocket() {
    return new Promise((resolve, reject) => {
        const url = getWebSocketUrl();
        console.log(`[WS] Connecting to ${url}`);

        const ws = new WebSocket(url);
        let resolved = false;

        ws.onopen = () => {
            console.log('[WS] Connection opened');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);

                // Resolve the promise on first "connected" message
                if (data.type === 'connected' && !resolved) {
                    resolved = true;
                    state.wsConnected = true;
                    resolve(ws);
                }
            } catch (e) {
                console.error('[WS] Failed to parse message:', e);
            }
        };

        ws.onerror = (error) => {
            console.error('[WS] Error:', error);
            state.wsConnected = false;
            if (!resolved) {
                resolved = true;
                reject(error);
            }
        };

        ws.onclose = (event) => {
            console.log(`[WS] Connection closed (code: ${event.code})`);
            state.wsConnected = false;
            state.websocket = null;
        };

        // Timeout after 5 seconds
        setTimeout(() => {
            if (!resolved) {
                resolved = true;
                ws.close();
                reject(new Error('WebSocket connection timeout'));
            }
        }, 5000);
    });
}

/**
 * Handle incoming WebSocket messages (partial/final transcripts).
 */
function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'connected':
            console.log('[WS] Server ready');
            break;

        case 'partial':
            // Update live transcript with new words
            state.liveTranscript = data.full_text || '';
            updateLiveTranscript(data.text, data.full_text);
            break;

        case 'final':
            // Final transcript received
            state.liveTranscript = data.full_text || data.text || '';
            updateLiveTranscriptFinal(state.liveTranscript);
            console.log(`[WS] Final transcript: ${state.liveTranscript.length} chars`);
            break;

        case 'error':
            console.error('[WS] Server error:', data.message);
            elements.voiceStatus.textContent = `Error: ${data.message}`;
            break;

        default:
            console.log('[WS] Unknown message type:', data.type);
    }
}

/**
 * Update the live transcript display with new words (animated).
 */
function updateLiveTranscript(deltaText, fullText) {
    if (!elements.liveTranscriptText) return;

    // Remove placeholder if present
    const placeholder = elements.liveTranscriptText.querySelector('.live-placeholder');
    if (placeholder) {
        placeholder.remove();
    }

    if (deltaText && deltaText.trim()) {
        // Add new words with animation
        const words = deltaText.trim().split(/\s+/);
        words.forEach((word, i) => {
            const span = document.createElement('span');
            span.className = 'live-word';
            span.textContent = (elements.liveTranscriptText.textContent.trim() ? ' ' : '') + word;
            span.style.animationDelay = `${i * 0.05}s`;
            elements.liveTranscriptText.appendChild(span);
        });
    } else if (fullText) {
        // Full replacement (correction case) — no animation
        elements.liveTranscriptText.textContent = fullText;
    }

    // Auto-scroll to bottom
    elements.liveTranscriptText.scrollTop = elements.liveTranscriptText.scrollHeight;
}

/**
 * Set the final transcript text (removes animations).
 */
function updateLiveTranscriptFinal(text) {
    if (!elements.liveTranscriptText) return;

    // Replace with plain text (no more animation)
    elements.liveTranscriptText.textContent = text || 'No speech detected.';
    elements.liveTranscriptText.style.borderLeftColor = '#10b981'; // Green = finalized
}

/**
 * Show the live transcript panel.
 */
function showLiveTranscript() {
    elements.emptyState?.classList.add('hidden');
    elements.loadingState?.classList.add('hidden');
    elements.resultsContainer?.classList.add('hidden');
    elements.liveTranscriptState?.classList.remove('hidden');
    elements.transcriptTitle.textContent = 'Live Transcript';

    // Reset the live transcript text
    if (elements.liveTranscriptText) {
        elements.liveTranscriptText.innerHTML =
            '<span class="live-placeholder">Listening... speak clearly into your microphone</span>';
        elements.liveTranscriptText.style.borderLeftColor = '#ef4444'; // Red = live
    }
}

/**
 * Hide the live transcript panel.
 */
function hideLiveTranscript() {
    elements.liveTranscriptState?.classList.add('hidden');
}

// =====================================================
// SETTINGS & NEURAL CONFIG
// =====================================================
function setupSettings() {
    // Theme Switching
    const themeCards = document.querySelectorAll('.theme-card');

    // Load saved settings
    const savedTheme = localStorage.getItem('voxdoc_theme') || 'glass';
    applyTheme(savedTheme);

    const savedSound = localStorage.getItem('voxdoc_sound') === 'true';
    const soundToggle = document.getElementById('soundToggle');
    if (soundToggle) soundToggle.checked = savedSound;

    themeCards.forEach(card => {
        card.addEventListener('click', () => {
            const theme = card.dataset.theme;
            applyTheme(theme);
            saveSettings('voxdoc_theme', theme);
        });
    });

    // Neural Graph Animation
    setupNeuralGraph();

    // Sliders
    setupSliders();
}

function applyTheme(theme) {
    document.body.className = ''; // Reset
    if (theme !== 'glass') {
        document.body.classList.add(`theme-${theme}`);
    }

    // Update UI active state
    document.querySelectorAll('.theme-card').forEach(c => {
        c.classList.toggle('active', c.dataset.theme === theme);
    });
}

function saveSettings(key, value) {
    localStorage.setItem(key, value);
}

function setupSliders() {
    const sliders = [
        { id: 'depthSlider', display: 'depthValue', unit: '%' },
        { id: 'empathySlider', display: 'empathyValue', map: { 1: 'Low', 2: 'Medium', 3: 'High' } },
        { id: 'particleSlider', display: null } // Just visual
    ];

    sliders.forEach(s => {
        const el = document.getElementById(s.id);
        const display = s.display ? document.getElementById(s.display) : null;

        if (el) {
            el.addEventListener('input', (e) => {
                if (display) {
                    if (s.map) {
                        display.textContent = s.map[e.target.value];
                    } else {
                        display.textContent = e.target.value + (s.unit || '');
                    }
                }
            });
        }
    });

    // Sound toggle
    document.getElementById('soundToggle').addEventListener('change', (e) => {
        saveSettings('voxdoc_sound', e.target.checked);
    });
}

function setupNeuralGraph() {
    const canvas = document.getElementById('neuralGraph');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Resize handling
    const resizeObserver = new ResizeObserver(() => {
        canvas.width = canvas.parentElement.clientWidth;
        canvas.height = canvas.parentElement.clientHeight;
    });
    resizeObserver.observe(canvas.parentElement);

    // Animation loop
    const dataPoints = new Array(50).fill(0);

    function draw() {
        if (document.getElementById('settingsView').classList.contains('hidden')) {
            requestAnimationFrame(draw);
            return;
        }

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Update data
        dataPoints.shift();
        dataPoints.push(Math.random() * 0.8 + 0.1); // Random activity

        // Draw line
        ctx.beginPath();
        const step = canvas.width / (dataPoints.length - 1);

        dataPoints.forEach((val, i) => {
            const x = i * step;
            const y = canvas.height - (val * canvas.height * 0.8) - 10;

            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });

        ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--violet-500');
        ctx.lineWidth = 2;
        ctx.lineJoin = 'round';
        ctx.stroke();

        // Add glow
        ctx.shadowBlur = 10;
        ctx.shadowColor = ctx.strokeStyle;
        ctx.stroke();
        ctx.shadowBlur = 0; // Reset

        requestAnimationFrame(draw);
    }

    draw();
}

// =====================================================
// INITIALIZATION
// =====================================================
function init() {
    setupNavigation();
    setupRecording();
    setupTextInput();
    setupSubmit();
    setupActions();
    setupSettings();
}

// =====================================================
// NAVIGATION & SIDEBAR
// =====================================================
function setupNavigation() {
    // Sidebar Toggles
    elements.openSidebarBtn?.addEventListener('click', openSidebar);
    elements.closeSidebarBtn?.addEventListener('click', closeSidebar);
    elements.sidebarOverlay?.addEventListener('click', closeSidebar);

    // Navigation Tabs
    const dashboardBtn = document.querySelector('[data-tab="dashboard"]');
    const settingsBtn = document.querySelector('[data-tab="settings"]');
    const historyBtn = document.querySelector('[data-tab="history"]');

    // Views
    const contentView = document.querySelector('.content-grid');
    const settingsView = document.getElementById('settingsView');

    function setActiveTab(activeBtn) {
        [dashboardBtn, settingsBtn, historyBtn].forEach(btn => {
            if (btn) btn.classList.remove('active');
        });
        if (activeBtn) activeBtn.classList.add('active');
        closeSidebar(); // Auto close on mobile
    }

    if (dashboardBtn) {
        dashboardBtn.addEventListener('click', () => {
            setActiveTab(dashboardBtn);
            if (contentView) contentView.classList.remove('hidden');
            if (settingsView) settingsView.classList.add('hidden');
        });
    }

    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            setActiveTab(settingsBtn);
            if (contentView) contentView.classList.add('hidden');
            if (settingsView) settingsView.classList.remove('hidden');
            // Re-draw graph if needed
            setupNeuralGraph();
        });
    }

    // History placeholder
    if (historyBtn) {
        historyBtn.addEventListener('click', () => {
            setActiveTab(historyBtn);
            alert('History feature coming soon in v2.0');
        });
    }
}

function openSidebar() {
    elements.sidebar?.classList.add('open');
    elements.sidebarOverlay?.classList.add('active');
}

function closeSidebar() {
    elements.sidebar?.classList.remove('open');
    elements.sidebarOverlay?.classList.remove('active');
}

// =====================================================
// RECORDING (with WebSocket Streaming)
// =====================================================
function setupRecording() {
    elements.recordBtn?.addEventListener('click', toggleRecording);
}

async function toggleRecording() {
    if (state.isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

async function startRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        // Try to connect WebSocket first
        let wsConnected = false;
        try {
            state.websocket = await connectWebSocket();
            wsConnected = true;
            state.streamingMode = true;
            console.log('[Recording] WebSocket streaming mode enabled');
        } catch (wsErr) {
            console.warn('[Recording] WebSocket failed, falling back to upload mode:', wsErr);
            state.streamingMode = false;
        }

        state.mediaRecorder = new MediaRecorder(stream);
        state.audioChunks = [];
        state.liveTranscript = '';

        state.mediaRecorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
                state.audioChunks.push(e.data);

                // Stream audio chunk via WebSocket (if connected)
                if (state.streamingMode && state.websocket && state.websocket.readyState === WebSocket.OPEN) {
                    e.data.arrayBuffer().then(buffer => {
                        state.websocket.send(buffer);
                    }).catch(err => {
                        console.warn('[WS] Failed to send chunk:', err);
                    });
                }
            }
        };

        state.mediaRecorder.onstop = () => {
            state.audioBlob = new Blob(state.audioChunks, { type: 'audio/webm' });
            state.audioUrl = URL.createObjectURL(state.audioBlob);
            stream.getTracks().forEach(track => track.stop());
            updateSubmitButton();
        };

        // Use 500ms timeslice for streaming chunks
        state.mediaRecorder.start(500);
        state.isRecording = true;
        state.recordingStartTime = Date.now();

        // UI Updates
        elements.recordBtn?.classList.add('recording');
        elements.micIcon?.classList.add('hidden');
        elements.stopIcon?.classList.remove('hidden');
        elements.waveformContainer?.classList.add('recording');
        elements.recordRipple?.classList.add('active');
        elements.durationDisplay?.classList.remove('hidden');

        // Show live transcript if streaming
        if (state.streamingMode) {
            elements.voiceStatus.textContent = 'Listening and transcribing live...';
            showLiveTranscript();
        } else {
            elements.voiceStatus.textContent = 'Recording... (will transcribe after stop)';
        }

        // Start timer
        state.recordingInterval = setInterval(updateRecordingTime, 1000);

    } catch (error) {
        console.error('Microphone access denied:', error);
        alert('Microphone access is required for voice recording.');
    }
}

function stopRecording() {
    if (state.mediaRecorder && state.isRecording) {
        state.mediaRecorder.stop();
        state.isRecording = false;

        // UI Updates
        elements.recordBtn?.classList.remove('recording');
        elements.micIcon?.classList.remove('hidden');
        elements.stopIcon?.classList.add('hidden');
        elements.waveformContainer?.classList.remove('recording');
        elements.recordRipple?.classList.remove('active');

        // Stop timer
        clearInterval(state.recordingInterval);

        // Send stop signal via WebSocket and wait for final transcript
        if (state.streamingMode && state.websocket && state.websocket.readyState === WebSocket.OPEN) {
            elements.voiceStatus.textContent = 'Finalizing transcript...';
            state.websocket.send(JSON.stringify({ action: 'stop' }));

            // Wait a moment for the final transcript, then close
            setTimeout(() => {
                if (state.websocket && state.websocket.readyState === WebSocket.OPEN) {
                    state.websocket.close();
                }
                elements.voiceStatus.textContent = 'Recording complete. Ready to generate documentation.';
            }, 3000);
        } else {
            elements.voiceStatus.textContent = 'Recording complete. Ready to generate documentation.';
        }
    }
}

function updateRecordingTime() {
    if (!state.recordingStartTime) return;

    const elapsed = Math.floor((Date.now() - state.recordingStartTime) / 1000);
    const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
    const seconds = (elapsed % 60).toString().padStart(2, '0');

    if (elements.recordingTime) {
        elements.recordingTime.textContent = `${minutes}:${seconds}`;
    }
}

// =====================================================
// TEXT INPUT
// =====================================================
function setupTextInput() {
    elements.textInput?.addEventListener('input', () => {
        updateSubmitButton();
    });
}

function updateSubmitButton() {
    const hasAudio = state.audioBlob !== null;
    const hasText = elements.textInput?.value.trim().length > 0;
    const hasLiveTranscript = state.liveTranscript && state.liveTranscript.trim().length > 0;

    if (elements.submitBtn) {
        elements.submitBtn.disabled = !(hasAudio || hasText || hasLiveTranscript);
    }
}

// =====================================================
// SUBMIT & PROCESSING
// =====================================================
function setupSubmit() {
    elements.submitBtn?.addEventListener('click', processInput);
}

async function processInput() {
    const hasAudio = state.audioBlob !== null;
    const textContent = elements.textInput?.value.trim();
    const hasLiveTranscript = state.liveTranscript && state.liveTranscript.trim().length > 0;

    if (!hasAudio && !textContent && !hasLiveTranscript) return;

    // Hide live transcript and show loading
    hideLiveTranscript();
    showLoading();

    try {
        let response;

        // If we have a live transcript from streaming, use it directly for documentation
        if (hasLiveTranscript && state.streamingMode) {
            // Use the streaming transcript directly — skip re-transcription
            const transcriptToUse = state.liveTranscript;

            response = await fetch('/api/document', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ transcript: transcriptToUse })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Processing failed');
            }

            const data = await response.json();
            data.transcript = transcriptToUse;
            data.duration_seconds = state.recordingStartTime
                ? (Date.now() - state.recordingStartTime) / 1000
                : 0;

            state.currentDocumentation = data;
            displayResults(data);

        } else if (hasAudio && !state.streamingMode) {
            // Fallback: Upload audio for server-side transcription
            const formData = new FormData();
            formData.append('audio', state.audioBlob, 'recording.webm');

            response = await fetch('/api/voice-intake', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Processing failed');
            }

            const data = await response.json();
            state.currentDocumentation = data;
            displayResults(data);

        } else if (textContent) {
            // Text input: Use /api/document with JSON
            response = await fetch('/api/document', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ transcript: textContent })
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || 'Processing failed');
            }

            const data = await response.json();
            // Normalize response format
            data.transcript = textContent;
            data.duration_seconds = 0;

            state.currentDocumentation = data;
            displayResults(data);
        }

    } catch (error) {
        console.error('Processing error:', error);
        showError(error.message);
    }
}

// =====================================================
// UI STATE MANAGEMENT
// =====================================================
function showLoading() {
    elements.emptyState?.classList.add('hidden');
    elements.resultsContainer?.classList.add('hidden');
    elements.liveTranscriptState?.classList.add('hidden');
    elements.loadingState?.classList.remove('hidden');
    elements.transcriptTitle.textContent = 'Processing...';
}

function showResults() {
    elements.emptyState?.classList.add('hidden');
    elements.loadingState?.classList.add('hidden');
    elements.liveTranscriptState?.classList.add('hidden');
    elements.resultsContainer?.classList.remove('hidden');
    elements.transcriptTitle.textContent = 'Documentation Results';
}

function showError(message) {
    elements.loadingState?.classList.add('hidden');
    elements.liveTranscriptState?.classList.add('hidden');
    elements.transcriptTitle.textContent = 'Error';

    // Create error display
    const errorHtml = `
        <div style="padding: 20px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 12px; color: #dc2626;">
            <strong>Error:</strong> ${message}
        </div>
    `;

    if (elements.resultsContainer) {
        elements.resultsContainer.innerHTML = errorHtml;
        elements.resultsContainer.classList.remove('hidden');
    }
}

function displayResults(data) {
    showResults();

    // Transcription
    if (elements.transcriptionText) {
        elements.transcriptionText.textContent = data.transcript;
    }

    // Audio Playback (only for voice input)
    if (state.audioUrl && elements.audioPlaybackSection && elements.resultAudioPlayer) {
        elements.resultAudioPlayer.src = state.audioUrl;
        elements.audioPlaybackSection.classList.remove('hidden');
        elements.textInputIndicator?.classList.add('hidden');
    } else {
        elements.audioPlaybackSection?.classList.add('hidden');
        elements.textInputIndicator?.classList.remove('hidden');
    }

    // Documentation fields
    const doc = data.documentation;

    if (elements.chiefComplaint) {
        elements.chiefComplaint.textContent = doc.chief_complaint || 'N/A';
    }

    // Symptom Details - Map backend field names to display
    if (elements.symptomDetails && doc.symptom_details) {
        const details = doc.symptom_details;
        // symptoms_mentioned is an array, join for display
        const symptomsText = Array.isArray(details.symptoms_mentioned)
            ? details.symptoms_mentioned.join(', ')
            : (details.symptoms_mentioned || 'not specified');

        elements.symptomDetails.innerHTML = `
            <ul>
                <li><strong>Symptoms:</strong> ${symptomsText}</li>
                <li><strong>Onset:</strong> ${details.onset || 'not specified'}</li>
                <li><strong>Duration:</strong> ${details.duration || 'not specified'}</li>
                <li><strong>Location:</strong> ${details.location || 'not specified'}</li>
                <li><strong>Aggravating Factors:</strong> ${details.aggravating_factors || 'not specified'}</li>
                <li><strong>Severity:</strong> ${details.severity_description || 'not specified'}</li>
            </ul>
        `;
    }

    // SOAP Note - Backend uses soap_note_subjective
    if (elements.soapNote) {
        elements.soapNote.textContent = doc.soap_note_subjective || 'Patient describes symptoms.';
    }
}

// =====================================================
// ACTIONS (Copy, Export)
// =====================================================
function setupActions() {
    elements.copyBtn?.addEventListener('click', copyToClipboard);
    elements.exportBtn?.addEventListener('click', exportJSON);
}

async function copyToClipboard() {
    if (!state.currentDocumentation) return;

    const doc = state.currentDocumentation.documentation;
    const text = `
CHIEF COMPLAINT: ${doc.chief_complaint}

SYMPTOM DETAILS:
- Symptoms: ${Array.isArray(doc.symptom_details?.symptoms_mentioned) ? doc.symptom_details.symptoms_mentioned.join(', ') : (doc.symptom_details?.symptoms || 'N/A')}
- Onset: ${doc.symptom_details?.onset || 'N/A'}
- Duration: ${doc.symptom_details?.duration || 'N/A'}
- Location: ${doc.symptom_details?.location || 'N/A'}

SOAP NOTE (Subjective):
${doc.soap_note_subjective || 'N/A'}
    `.trim();

    try {
        await navigator.clipboard.writeText(text);

        // Visual feedback
        const originalSvg = elements.copyBtn.innerHTML;
        elements.copyBtn.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20 6 9 17 4 12" />
            </svg>
        `;
        elements.copyBtn.style.color = '#10b981';

        setTimeout(() => {
            elements.copyBtn.innerHTML = originalSvg;
            elements.copyBtn.style.color = '';
        }, 2000);

    } catch (error) {
        console.error('Copy failed:', error);
    }
}

function exportJSON() {
    if (!state.currentDocumentation) return;

    const dataStr = JSON.stringify(state.currentDocumentation, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `voxdoc_${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// =====================================================
// INITIALIZE
// =====================================================
document.addEventListener('DOMContentLoaded', init);
