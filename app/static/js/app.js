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
    audioPlaybackSection: document.getElementById('audioPlaybackSection'),
    resultAudioPlayer: document.getElementById('resultAudioPlayer'),
    textInputIndicator: document.getElementById('textInputIndicator'),

    // SOAP Section Cards
    soapS: document.getElementById('soapS'),
    soapO: document.getElementById('soapO'),
    soapA: document.getElementById('soapA'),
    soapP: document.getElementById('soapP'),
    soapStatusS: document.getElementById('soapStatusS'),
    soapStatusO: document.getElementById('soapStatusO'),
    soapStatusA: document.getElementById('soapStatusA'),
    soapStatusP: document.getElementById('soapStatusP'),
    soapStatusCC: document.getElementById('soapStatusCC'),
    soapStatusCD: document.getElementById('soapStatusCD'),
    soapOverallStatus: document.getElementById('soapOverallStatus'),

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
    streamingMode: true,  // true = use WebSocket streaming, false = fallback to upload

    // SOAP section approval state (with edit history)
    soapApprovals: {
        subjective: { status: 'pending', edited: false, originalText: '', history: [] },
        objective: { status: 'pending', edited: false, originalText: '', history: [] },
        assessment: { status: 'pending', edited: false, originalText: '', history: [] },
        plan: { status: 'pending', edited: false, originalText: '', history: [] },
        chief_complaint: { status: 'pending', edited: false, originalText: '', history: [] },
        clinical_details: { status: 'pending', edited: false, originalText: '', history: [] }
    }
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

// Theme cycle order for header toggle
const THEME_ORDER = ['glass', 'light', 'neon', 'midnight', 'aurora'];

// Meta theme-color mapping per theme
const THEME_META_COLORS = {
    glass: '#0f111a',
    neon: '#050505',
    midnight: '#000000',
    light: '#f0f4f8',
    aurora: '#141020'
};

function setupSettings() {
    // Theme Switching
    const themeCards = document.querySelectorAll('.theme-card');

    // Determine initial theme: saved > OS preference > default (glass)
    let initialTheme = localStorage.getItem('voxdoc_theme');
    if (!initialTheme) {
        // First visit — detect OS preference
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
            initialTheme = 'light';
        } else {
            initialTheme = 'glass';
        }
    }
    applyTheme(initialTheme);

    // Listen for OS theme changes (live)
    if (window.matchMedia) {
        window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', (e) => {
            // Only auto-switch if user hasn't explicitly picked a theme
            const userPicked = localStorage.getItem('voxdoc_theme');
            if (!userPicked) {
                applyTheme(e.matches ? 'light' : 'glass');
            }
        });
    }

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

    // Header quick-toggle
    setupThemeToggle();

    // Neural Graph Animation
    setupNeuralGraph();

    // Sliders
    setupSliders();
}

function applyTheme(theme) {
    // Remove all theme classes
    THEME_ORDER.forEach(t => {
        if (t !== 'glass') document.body.classList.remove(`theme-${t}`);
    });

    // Apply new theme class (glass = no class, uses :root defaults)
    if (theme !== 'glass') {
        document.body.classList.add(`theme-${theme}`);
    }

    // Update <meta name="theme-color">
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
        metaTheme.setAttribute('content', THEME_META_COLORS[theme] || '#0f111a');
    }

    // Update settings panel theme cards active state
    document.querySelectorAll('.theme-card').forEach(c => {
        c.classList.toggle('active', c.dataset.theme === theme);
    });

    // Store current theme for toggle cycling
    window._currentTheme = theme;
}

function setupThemeToggle() {
    const toggleBtn = document.getElementById('themeToggle');
    if (!toggleBtn) return;

    toggleBtn.addEventListener('click', () => {
        const current = window._currentTheme || 'glass';
        const currentIndex = THEME_ORDER.indexOf(current);
        const nextIndex = (currentIndex + 1) % THEME_ORDER.length;
        const nextTheme = THEME_ORDER[nextIndex];
        applyTheme(nextTheme);
        saveSettings('voxdoc_theme', nextTheme);

        // Subtle spin animation on click
        toggleBtn.style.transform = 'rotate(360deg)';
        setTimeout(() => { toggleBtn.style.transform = ''; }, 400);
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
    setupSOAPActions();
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

    // SOAP Notes + CC/CD — populate and store originals
    const soapMap = {
        soapS: doc.soap_note_subjective || 'Patient describes symptoms.',
        soapO: doc.soap_note_objective || 'Pending clinician assessment.',
        soapA: doc.soap_note_assessment || 'Pending clinician assessment.',
        soapP: doc.soap_note_plan || 'Pending clinician assessment.',
        chiefComplaint: doc.chief_complaint || 'N/A',
        symptomDetails: elements.symptomDetails?.innerHTML || 'N/A'
    };

    for (const [id, text] of Object.entries(soapMap)) {
        if (elements[id]) {
            if (id === 'symptomDetails') {
                // Already rendered formatted HTML for Symptom Details
            } else {
                elements[id].textContent = text;
            }
        }
    }

    // Reset approval states and store original AI text
    state.soapApprovals = {
        subjective: { status: 'pending', edited: false, originalText: soapMap.soapS, history: [] },
        objective: { status: 'pending', edited: false, originalText: soapMap.soapO, history: [] },
        assessment: { status: 'pending', edited: false, originalText: soapMap.soapA, history: [] },
        plan: { status: 'pending', edited: false, originalText: soapMap.soapP, history: [] },
        chief_complaint: { status: 'pending', edited: false, originalText: soapMap.chiefComplaint, history: [] },
        clinical_details: { status: 'pending', edited: false, originalText: soapMap.symptomDetails, history: [] }
    };

    // Log initial generation event
    for (const section of Object.keys(state.soapApprovals)) {
        logSOAPHistory(section, 'generated', 'AI-generated content');
    }

    resetSOAPCardStates();
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

    // Get current SOAP text (may have been edited by clinician)
    const soapS = elements.soapS?.textContent || doc.soap_note_subjective || 'N/A';
    const soapO = elements.soapO?.textContent || doc.soap_note_objective || 'N/A';
    const soapA = elements.soapA?.textContent || doc.soap_note_assessment || 'N/A';
    const soapP = elements.soapP?.textContent || doc.soap_note_plan || 'N/A';

    const text = `
CHIEF COMPLAINT: ${doc.chief_complaint}

SYMPTOM DETAILS:
- Symptoms: ${Array.isArray(doc.symptom_details?.symptoms_mentioned) ? doc.symptom_details.symptoms_mentioned.join(', ') : (doc.symptom_details?.symptoms || 'N/A')}
- Onset: ${doc.symptom_details?.onset || 'N/A'}
- Duration: ${doc.symptom_details?.duration || 'N/A'}
- Location: ${doc.symptom_details?.location || 'N/A'}

SOAP NOTE:

S (Subjective) [${state.soapApprovals.subjective.status}]:
${soapS}

O (Objective) [${state.soapApprovals.objective.status}]:
${soapO}

A (Assessment) [${state.soapApprovals.assessment.status}]:
${soapA}

P (Plan) [${state.soapApprovals.plan.status}]:
${soapP}
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

    // Enrich export data with approval status, edit history, and current content
    const exportData = JSON.parse(JSON.stringify(state.currentDocumentation));
    exportData.soap_approvals = state.soapApprovals;
    exportData.soap_edit_history = {};
    for (const [section, data] of Object.entries(state.soapApprovals)) {
        exportData.soap_edit_history[section] = {
            original_ai_text: data.originalText,
            current_status: data.status,
            was_edited: data.edited,
            timeline: data.history
        };
    }

    // Include current (possibly edited) SOAP text
    if (exportData.documentation) {
        exportData.documentation.soap_note_subjective = elements.soapS?.textContent || exportData.documentation.soap_note_subjective;
        exportData.documentation.soap_note_objective = elements.soapO?.textContent || exportData.documentation.soap_note_objective;
        exportData.documentation.soap_note_assessment = elements.soapA?.textContent || exportData.documentation.soap_note_assessment;
        exportData.documentation.soap_note_plan = elements.soapP?.textContent || exportData.documentation.soap_note_plan;
    }

    const dataStr = JSON.stringify(exportData, null, 2);
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
// SOAP SECTION EDIT / APPROVE / REJECT / HISTORY
// =====================================================

/**
 * Set up click handlers for all SOAP Edit, Reject, Approve, and History buttons.
 */
function setupSOAPActions() {
    document.querySelectorAll('.soap-edit-btn').forEach(btn => {
        btn.addEventListener('click', () => handleSOAPEdit(btn.dataset.section));
    });
    document.querySelectorAll('.soap-reject-btn').forEach(btn => {
        btn.addEventListener('click', () => handleSOAPReject(btn.dataset.section));
    });
    document.querySelectorAll('.soap-approve-btn').forEach(btn => {
        btn.addEventListener('click', () => handleSOAPApprove(btn.dataset.section));
    });
    document.querySelectorAll('.soap-history-toggle').forEach(btn => {
        btn.addEventListener('click', () => toggleSOAPHistory(btn.dataset.section));
    });
}

/**
 * Handle Edit button click for a SOAP section.
 * Toggles contenteditable on the body, changes button text.
 */
function handleSOAPEdit(section) {
    const bodyEl = getSOAPBodyEl(section);
    const card = bodyEl?.closest('.soap-section-card');
    const editBtn = card?.querySelector('.soap-edit-btn');
    const statusBadge = getSOAPStatusEl(section);

    if (!bodyEl || !editBtn) return;

    const isEditing = bodyEl.getAttribute('contenteditable') === 'true';

    if (isEditing) {
        // Save
        bodyEl.setAttribute('contenteditable', 'false');
        card?.classList.remove('editing');
        editBtn.querySelector('span').textContent = 'Edit';
        editBtn.classList.remove('saving');

        // Mark as edited and log history
        const currentText = bodyEl.textContent;
        state.soapApprovals[section].edited = true;
        state.soapApprovals[section].status = 'edited';
        logSOAPHistory(section, 'edited', currentText);

        if (statusBadge) {
            statusBadge.textContent = 'Edited';
            statusBadge.className = 'soap-status badge info';
        }

        // Clear rejected state if re-editing
        card?.classList.remove('rejected', 'just-rejected');
        const rejectBtn = card?.querySelector('.soap-reject-btn');
        if (rejectBtn) {
            rejectBtn.classList.remove('rejected');
            rejectBtn.disabled = false;
            rejectBtn.querySelector('span').textContent = 'Reject';
        }

        updateSOAPOverallStatus();
    } else {
        // Enter edit mode
        bodyEl.setAttribute('contenteditable', 'true');
        card?.classList.add('editing');
        editBtn.querySelector('span').textContent = 'Save';
        editBtn.classList.add('saving');
        bodyEl.focus();

        // Un-approve if was approved
        if (state.soapApprovals[section].status === 'approved') {
            state.soapApprovals[section].status = 'edited';
            card?.classList.remove('approved');

            const approveBtn = card?.querySelector('.soap-approve-btn');
            if (approveBtn) {
                approveBtn.classList.remove('approved');
                approveBtn.disabled = false;
                approveBtn.querySelector('span').textContent = 'Approve';
            }
        }
    }
}

/**
 * Handle Approve button click for a SOAP section.
 * Locks the section and marks it approved.
 */
function handleSOAPApprove(section) {
    const bodyEl = getSOAPBodyEl(section);
    const card = bodyEl?.closest('.soap-section-card');
    const approveBtn = card?.querySelector('.soap-approve-btn');
    const editBtn = card?.querySelector('.soap-edit-btn');
    const statusBadge = getSOAPStatusEl(section);

    if (!bodyEl || !approveBtn) return;

    // Close edit mode if open
    bodyEl.setAttribute('contenteditable', 'false');
    card?.classList.remove('editing');
    if (editBtn) {
        editBtn.querySelector('span').textContent = 'Edit';
        editBtn.classList.remove('saving');
    }

    // Mark approved and log
    state.soapApprovals[section].status = 'approved';
    card?.classList.add('approved');
    card?.classList.remove('rejected', 'just-rejected');
    approveBtn.classList.add('approved');
    approveBtn.querySelector('span').textContent = 'Approved';
    logSOAPHistory(section, 'approved', bodyEl.textContent);

    // Reset reject button
    const rejectBtn = card?.querySelector('.soap-reject-btn');
    if (rejectBtn) {
        rejectBtn.classList.remove('rejected');
        rejectBtn.disabled = false;
        rejectBtn.querySelector('span').textContent = 'Reject';
    }

    if (statusBadge) {
        statusBadge.textContent = '✓ Approved';
        statusBadge.className = 'soap-status badge success';
    }

    // Flash animation
    card?.classList.add('just-approved');
    setTimeout(() => card?.classList.remove('just-approved'), 900);

    updateSOAPOverallStatus();
}

/**
 * Reset all SOAP card states to initial "Pending Review".
 */
function resetSOAPCardStates() {
    ['subjective', 'objective', 'assessment', 'plan'].forEach(section => {
        const bodyEl = getSOAPBodyEl(section);
        const card = bodyEl?.closest('.soap-section-card');
        const statusBadge = getSOAPStatusEl(section);
        const editBtn = card?.querySelector('.soap-edit-btn');
        const approveBtn = card?.querySelector('.soap-approve-btn');

        bodyEl?.setAttribute('contenteditable', 'false');
        card?.classList.remove('editing', 'approved', 'just-approved', 'rejected', 'just-rejected');

        if (statusBadge) {
            statusBadge.textContent = 'Pending Review';
            statusBadge.className = 'soap-status badge warning';
        }

        if (editBtn) {
            editBtn.querySelector('span').textContent = 'Edit';
            editBtn.classList.remove('saving');
            editBtn.disabled = false;
        }

        if (approveBtn) {
            approveBtn.classList.remove('approved');
            approveBtn.disabled = false;
            approveBtn.querySelector('span').textContent = 'Approve';
        }

        const rejectBtn = card?.querySelector('.soap-reject-btn');
        if (rejectBtn) {
            rejectBtn.classList.remove('rejected');
            rejectBtn.disabled = false;
            rejectBtn.querySelector('span').textContent = 'Reject';
        }

        // Hide and clear history panel
        const historyEl = getSOAPHistoryEl(section);
        if (historyEl) {
            historyEl.classList.add('hidden');
            historyEl.innerHTML = '';
        }
        const historyToggle = card?.querySelector('.soap-history-toggle');
        historyToggle?.classList.remove('active');
    });

    updateSOAPOverallStatus();
}

/**
 * Update the overall SOAP status badge.
 */
function updateSOAPOverallStatus() {
    if (!elements.soapOverallStatus) return;

    const sections = Object.values(state.soapApprovals);
    const approvedCount = sections.filter(s => s.status === 'approved').length;
    const rejectedCount = sections.filter(s => s.status === 'rejected').length;
    const total = sections.length;

    if (approvedCount === total) {
        elements.soapOverallStatus.textContent = 'All sections approved ✓';
        elements.soapOverallStatus.className = 'badge success';
    } else if (rejectedCount > 0) {
        elements.soapOverallStatus.textContent = `${rejectedCount} rejected · ${total - approvedCount - rejectedCount} pending`;
        elements.soapOverallStatus.className = 'badge warning';
    } else {
        elements.soapOverallStatus.textContent = `${total - approvedCount} of ${total} pending review`;
        elements.soapOverallStatus.className = 'badge info';
    }
}

/**
 * Handle Reject button click for a SOAP section.
 * Prompts for optional reason, strikes-through the content.
 */
function handleSOAPReject(section) {
    const bodyEl = getSOAPBodyEl(section);
    const card = bodyEl?.closest('.soap-section-card');
    const rejectBtn = card?.querySelector('.soap-reject-btn');
    const approveBtn = card?.querySelector('.soap-approve-btn');
    const editBtn = card?.querySelector('.soap-edit-btn');
    const statusBadge = getSOAPStatusEl(section);

    if (!bodyEl || !rejectBtn) return;

    // Prompt for optional reason
    const reason = prompt('Reason for rejection (optional):') || '';

    // Close edit mode if open
    bodyEl.setAttribute('contenteditable', 'false');
    card?.classList.remove('editing', 'approved', 'just-approved');
    if (editBtn) {
        editBtn.querySelector('span').textContent = 'Edit';
        editBtn.classList.remove('saving');
    }
    if (approveBtn) {
        approveBtn.classList.remove('approved');
        approveBtn.querySelector('span').textContent = 'Approve';
    }

    // Mark rejected
    state.soapApprovals[section].status = 'rejected';
    card?.classList.add('rejected');
    rejectBtn.classList.add('rejected');
    rejectBtn.querySelector('span').textContent = 'Rejected';
    logSOAPHistory(section, 'rejected', reason ? `Rejected: ${reason}` : 'Rejected by clinician');

    if (statusBadge) {
        statusBadge.textContent = '✗ Rejected';
        statusBadge.className = 'soap-status badge danger';
    }

    // Flash animation
    card?.classList.add('just-rejected');
    setTimeout(() => card?.classList.remove('just-rejected'), 900);

    updateSOAPOverallStatus();
}

/**
 * Toggle the history panel for a SOAP section.
 */
function toggleSOAPHistory(section) {
    const historyEl = getSOAPHistoryEl(section);
    const bodyEl = getSOAPBodyEl(section);
    const card = bodyEl?.closest('.soap-section-card');
    const toggleBtn = card?.querySelector('.soap-history-toggle');

    if (!historyEl) return;

    const isVisible = !historyEl.classList.contains('hidden');

    if (isVisible) {
        historyEl.classList.add('hidden');
        toggleBtn?.classList.remove('active');
    } else {
        renderSOAPHistory(section);
        historyEl.classList.remove('hidden');
        toggleBtn?.classList.add('active');
    }
}

/**
 * Log a timestamped entry in a SOAP section's history.
 */
function logSOAPHistory(section, action, text) {
    if (!state.soapApprovals[section]) return;
    state.soapApprovals[section].history.push({
        action,
        text: text || '',
        timestamp: new Date().toISOString()
    });
}

/**
 * Render the history panel for a SOAP section.
 */
function renderSOAPHistory(section) {
    const historyEl = getSOAPHistoryEl(section);
    const data = state.soapApprovals[section];
    if (!historyEl || !data) return;

    const entries = data.history;

    // Build original AI text block
    const isSymptomDetails = section === 'clinical_details';
    const originalBlock = data.originalText
        ? `<div class="soap-history-original">
               <div style="display: flex; align-items: center; margin-bottom: 4px;">
                   <div class="soap-history-original-label">Original AI Output</div>
                   <button class="soap-history-restore-btn" onclick="restoreOriginalSOAP('${section}')">Restore</button>
               </div>
               ${isSymptomDetails ? data.originalText : escapeHTML(data.originalText)}
           </div>`
        : '';

    // Build timeline
    let timeline = '';
    if (entries.length === 0) {
        timeline = '<p class="soap-history-empty">No history yet.</p>';
    } else {
        const items = entries.map(e => {
            const time = new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const dotClass = e.action;
            const actionLabel = e.action.charAt(0).toUpperCase() + e.action.slice(1);
            let detail = '';
            if (e.text) {
                const plainText = e.text.replace(/<[^>]*>?/gm, ''); // Strip HTML for list items in history
                detail = ` — ${escapeHTML(truncate(plainText, 120))}`;
            }
            return `<li class="soap-history-entry">
                        <span class="soap-history-dot ${dotClass}"></span>
                        <span class="soap-history-time">${time}</span>
                        <span class="soap-history-action"><strong>${actionLabel}</strong>${detail}</span>
                    </li>`;
        }).join('');
        timeline = `<ul class="soap-history-timeline">${items}</ul>`;
    }

    historyEl.innerHTML = originalBlock + timeline;
}

/**
 * Restore a section to its original AI-generated text.
 */
function restoreOriginalSOAP(section) {
    const data = state.soapApprovals[section];
    if (!data || !data.originalText) return;

    if (!confirm(`Are you sure you want to restore the original ${section.replace('_', ' ')}? Current edits will be lost.`)) {
        return;
    }

    const bodyEl = getSOAPBodyEl(section);
    const card = bodyEl?.closest('.soap-section-card');
    const statusBadge = getSOAPStatusEl(section);

    if (!bodyEl) return;

    // Restore text
    if (section === 'clinical_details') {
        bodyEl.innerHTML = data.originalText;
    } else {
        bodyEl.textContent = data.originalText;
    }

    // Reset state
    data.status = 'pending';
    data.edited = false;
    logSOAPHistory(section, 'restored', 'Restored to original AI output');

    // UI Reset
    card?.classList.remove('approved', 'rejected', 'editing', 'just-approved', 'just-rejected');
    if (statusBadge) {
        statusBadge.textContent = 'Pending Review';
        statusBadge.className = 'soap-status badge warning';
    }

    const approveBtn = card?.querySelector('.soap-approve-btn');
    if (approveBtn) {
        approveBtn.classList.remove('approved');
        approveBtn.disabled = false;
        approveBtn.querySelector('span').textContent = 'Approve';
    }

    const rejectBtn = card?.querySelector('.soap-reject-btn');
    if (rejectBtn) {
        rejectBtn.classList.remove('rejected');
        rejectBtn.disabled = false;
        rejectBtn.querySelector('span').textContent = 'Reject';
    }

    const editBtn = card?.querySelector('.soap-edit-btn');
    if (editBtn) {
        editBtn.querySelector('span').textContent = 'Edit';
        editBtn.classList.remove('saving');
    }

    bodyEl.setAttribute('contenteditable', 'false');

    // Re-render history to show "Restored" entry
    renderSOAPHistory(section);
    updateSOAPOverallStatus();
}

/** Escape HTML entities. */
function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/** Truncate a string to maxLen characters. */
function truncate(str, maxLen) {
    return str.length > maxLen ? str.slice(0, maxLen) + '…' : str;
}

/** Get the body element for a SOAP section. */
function getSOAPBodyEl(section) {
    const map = {
        subjective: 'soapS',
        objective: 'soapO',
        assessment: 'soapA',
        plan: 'soapP',
        chief_complaint: 'chiefComplaint',
        clinical_details: 'symptomDetails'
    };
    return elements[map[section]] || null;
}

/** Get the status badge element for a SOAP section. */
function getSOAPStatusEl(section) {
    const map = {
        subjective: 'soapStatusS',
        objective: 'soapStatusO',
        assessment: 'soapStatusA',
        plan: 'soapStatusP',
        chief_complaint: 'soapStatusCC',
        clinical_details: 'soapStatusCD'
    };
    return elements[map[section]] || null;
}

/** Get the history panel element for a SOAP section. */
function getSOAPHistoryEl(section) {
    const map = {
        subjective: 'soapHistoryS',
        objective: 'soapHistoryO',
        assessment: 'soapHistoryA',
        plan: 'soapHistoryP',
        chief_complaint: 'soapHistoryCC',
        clinical_details: 'soapHistoryCD'
    };
    return document.getElementById(map[section]) || null;
}

// =====================================================
// INITIALIZE
// =====================================================
document.addEventListener('DOMContentLoaded', init);
