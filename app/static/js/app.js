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
    userAvatar: document.getElementById('userAvatar'),
    userName: document.getElementById('userName'),
    userRole: document.getElementById('userRole'),

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
    followupState: document.getElementById('followupState'),
    followupQuestions: document.getElementById('followupQuestions'),
    followupSubmitBtn: document.getElementById('followupSubmitBtn'),
    followupSkipBtn: document.getElementById('followupSkipBtn'),
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
    visualFindings: document.getElementById('visualFindings'),
    imageFindingsCard: document.getElementById('imageFindingsCard'),
    imageFindingsThumbnailContainer: document.getElementById('imageFindingsThumbnailContainer'),
    soapStatusS: document.getElementById('soapStatusS'),
    soapStatusO: document.getElementById('soapStatusO'),
    soapStatusA: document.getElementById('soapStatusA'),
    soapStatusP: document.getElementById('soapStatusP'),
    soapStatusCC: document.getElementById('soapStatusCC'),
    soapStatusCD: document.getElementById('soapStatusCD'),
    soapStatusVI: document.getElementById('soapStatusVI'),
    soapOverallStatus: document.getElementById('soapOverallStatus'),

    // Image Upload
    imageDropZone: document.getElementById('imageDropZone'),
    imageFileInput: document.getElementById('imageFileInput'),
    imagePreviewContainer: document.getElementById('imagePreviewContainer'),
    imagePreview: document.getElementById('imagePreview'),
    removeImageBtn: document.getElementById('removeImageBtn'),
    imageFilename: document.getElementById('imageFilename'),
    imageFilesize: document.getElementById('imageFilesize'),
    dropZoneContent: document.getElementById('dropZoneContent'),
    imageAnalyzingState: document.getElementById('imageAnalyzingState'),

    // Actions
    copyBtn: document.getElementById('copyBtn'),
    exportBtn: document.getElementById('exportBtn'),
    exportPdfBtn: document.getElementById('exportPdfBtn'),
    batchExportBtn: document.getElementById('batchExportBtn'),

    // PWA
    offlineBadge: document.getElementById('offlineBadge'),
    installAppBtn: document.getElementById('installAppBtn'),

    // NER Entities
    nerEntitiesCard: document.getElementById('nerEntitiesCard'),
    nerEntityCount: document.getElementById('nerEntityCount'),
    nerConditionBadges: document.getElementById('nerConditionBadges'),
    nerMedicationBadges: document.getElementById('nerMedicationBadges'),

    // FHIR / EHR
    fhirExportBtn: document.getElementById('fhirExportBtn'),
    ehrPushBtn: document.getElementById('ehrPushBtn'),
    ehrModal: document.getElementById('ehrModal'),
    ehrModalClose: document.getElementById('ehrModalClose'),
    ehrModalCancel: document.getElementById('ehrModalCancel'),
    ehrModalSubmit: document.getElementById('ehrModalSubmit'),
    ehrServerUrl: document.getElementById('ehrServerUrl'),
    ehrAuthToken: document.getElementById('ehrAuthToken')
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
        clinical_details: { status: 'pending', edited: false, originalText: '', history: [] },
        visual_findings: { status: 'pending', edited: false, originalText: '', history: [] }
    },

    // Image Upload State
    uploadedImageFile: null,
    imageAnalysis: null,

    // Session History
    sessionHistory: [],

    // User (no auth)
    currentUser: {
        id: 'system',
        username: 'local_operator',
        full_name: 'Local Operator',
        role: 'admin',
        is_active: true
    },

    // PWA State
    deferredInstallPrompt: null,
    isOffline: !navigator.onLine
};

const ROLE_LABELS = {
    admin: 'Admin',
    clinician: 'Clinician',
    intake_staff: 'Intake Staff'
};

const LOCAL_USER = {
    id: 'system',
    username: 'local_operator',
    full_name: 'Local Operator',
    role: 'admin',
    is_active: true
};

function getRoleLabel(role) {
    return ROLE_LABELS[role] || role || 'Unknown';
}

function getInitials(name) {
    if (!name) return '--';
    const parts = String(name).trim().split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '--';
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
    return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function updateAuthUI(message = null) {
    const currentUser = state.currentUser || LOCAL_USER;

    if (elements.userAvatar) {
        elements.userAvatar.textContent = getInitials(currentUser.full_name || currentUser.username);
    }
    if (elements.userName) {
        elements.userName.textContent = currentUser.full_name || currentUser.username;
    }
    if (elements.userRole) {
        elements.userRole.textContent = getRoleLabel(currentUser.role);
    }

    updateSubmitButton();
}

async function apiFetch(url, options = {}) {
    const headers = new Headers(options.headers || {});

    const response = await fetch(url, {
        ...options,
        headers
    });

    if (response.status === 429) {
        const errorData = await response.json().catch(() => ({}));
        const detail = errorData.detail || {};
        const retryAfter = detail.retry_after_seconds || parseInt(response.headers.get('Retry-After') || '30', 10);
        const queueLength = detail.queue_length;
        const msg = detail.error || 'Rate limit exceeded. Please wait before retrying.';
        showRateLimitToast(msg, retryAfter);
        throw new Error(msg);
    }

    return response;
}

function showRateLimitToast(message, retryAfter) {
    const existing = document.querySelector('.rate-limit-toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'rate-limit-toast';
    toast.textContent = `${message} (retry in ${retryAfter}s)`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), Math.min(retryAfter * 1000, 10000));
}

let queuePollInterval = null;

function showQueueStatus(position, waitSeconds) {
    const banner = document.getElementById('queueBanner');
    const posEl = document.getElementById('queuePosition');
    const waitEl = document.getElementById('queueWait');
    if (!banner) return;

    banner.classList.remove('hidden');
    posEl.textContent = `Position in queue: ${position}`;
    waitEl.textContent = `Estimated wait: ${Math.ceil(waitSeconds)}s`;
}

function hideQueueStatus() {
    const banner = document.getElementById('queueBanner');
    if (banner) banner.classList.add('hidden');
    if (queuePollInterval) {
        clearInterval(queuePollInterval);
        queuePollInterval = null;
    }
}

function startQueuePolling() {
    hideQueueStatus();
    queuePollInterval = setInterval(async () => {
        try {
            const resp = await apiFetch('/api/queue/status');
            if (!resp.ok) return;
            const data = await resp.json();
            if (data.queue_length > 0) {
                showQueueStatus(data.queue_length, data.queue_length * data.avg_inference_seconds);
            } else {
                hideQueueStatus();
                const msgEl = document.getElementById('loadingMessage');
                if (msgEl) msgEl.textContent = 'Processing and generating documentation...';
            }
        } catch { /* ignore polling errors */ }
    }, 3000);
}

// =====================================================
// MONITORING DASHBOARD
// =====================================================

let monitoringAutoRefresh = null;

async function loadMonitoringDashboard() {
    try {
        const resp = await apiFetch('/api/monitoring/dashboard');
        if (!resp.ok) {
            if (resp.status === 403) {
                const mv = document.getElementById('monitoringView');
                if (mv) mv.innerHTML = '<p style="padding:20px;color:var(--text-secondary);">Admin access required for monitoring dashboard.</p>';
            }
            return;
        }
        const data = await resp.json();
        renderMonitoringData(data);

        // Auto-refresh every 10s while on the monitoring tab
        if (monitoringAutoRefresh) clearInterval(monitoringAutoRefresh);
        monitoringAutoRefresh = setInterval(async () => {
            const mv = document.getElementById('monitoringView');
            if (mv && !mv.classList.contains('hidden')) {
                try {
                    const r = await apiFetch('/api/monitoring/dashboard');
                    if (r.ok) renderMonitoringData(await r.json());
                } catch { /* ignore */ }
            } else {
                clearInterval(monitoringAutoRefresh);
                monitoringAutoRefresh = null;
            }
        }, 10000);
    } catch (e) {
        console.error('Failed to load monitoring data:', e);
    }
}

function renderMonitoringData(data) {
    // Uptime
    const uptimeEl = document.getElementById('monitoringUptime');
    if (uptimeEl) {
        const h = Math.floor(data.uptime_seconds / 3600);
        const m = Math.floor((data.uptime_seconds % 3600) / 60);
        uptimeEl.textContent = `Uptime: ${h}h ${m}m`;
    }

    // Model cards
    const modelMap = {
        medasr: { req: 'medasrRequests', err: 'medasrErrorRate', lat: 'medasrLatency', p95: 'medasrP95', dot: 'statusDotMedasr', card: 'monitorCardMedasr' },
        medgemma: { req: 'medgemmaRequests', err: 'medgemmaErrorRate', lat: 'medgemmaLatency', p95: 'medgemmaP95', dot: 'statusDotMedgemma', card: 'monitorCardMedgemma' },
        medgemma_vision: { req: 'visionRequests', err: 'visionErrorRate', lat: 'visionLatency', p95: 'visionP95', dot: 'statusDotVision', card: 'monitorCardVision' },
        ner: { req: 'nerRequests', err: 'nerErrorRate', lat: 'nerLatency', p95: 'nerP95', dot: 'statusDotNer', card: 'monitorCardNer' },
    };

    for (const [model, ids] of Object.entries(modelMap)) {
        const stats = data.models?.[model];
        if (!stats) continue;

        const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        setTxt(ids.req, stats.total_requests);
        setTxt(ids.err, (stats.error_rate * 100).toFixed(1) + '%');
        setTxt(ids.lat, stats.latency?.avg ? stats.latency.avg.toFixed(2) + 's' : '--');
        setTxt(ids.p95, stats.latency?.p95 ? stats.latency.p95.toFixed(2) + 's' : '--');

        const dot = document.getElementById(ids.dot);
        if (dot) {
            dot.className = 'monitor-status-dot ' + (stats.ready ? 'ready' : 'not-ready');
        }

        const card = document.getElementById(ids.card);
        if (card) {
            card.classList.remove('alert-warning', 'alert-critical');
            if (stats.error_rate >= 0.25) card.classList.add('alert-critical');
            else if (stats.error_rate >= 0.1) card.classList.add('alert-warning');
        }
    }

    // Queue
    if (data.queue) {
        const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
        setTxt('queueActive', data.queue.active_inferences);
        setTxt('queueWaiting', data.queue.queue_length);
        setTxt('queueMaxConc', data.queue.max_concurrent);
        setTxt('queueAvgTime', data.queue.avg_inference_seconds + 's');
    }

    // Connections
    const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    setTxt('connHttp', data.active_http_connections || 0);
    setTxt('connWs', data.active_websockets || 0);

    // Alerts
    const alertsBanner = document.getElementById('alertsBanner');
    if (alertsBanner) {
        if (data.alerts && data.alerts.length > 0) {
            alertsBanner.classList.remove('hidden');
            alertsBanner.innerHTML = data.alerts.map(a => `
                <div class="alert-item ${a.severity}">
                    <span class="alert-severity">${a.severity}</span>
                    <span>${a.description}</span>
                </div>
            `).join('');
        } else {
            alertsBanner.classList.add('hidden');
            alertsBanner.innerHTML = '';
        }
    }
}

function requireAuthentication() {
    return true;
}

async function refreshCurrentUser() {
    state.currentUser = { ...LOCAL_USER };
    updateAuthUI();
    return true;
}

function setupAuth() {
    updateAuthUI();
}

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
const THEME_ORDER = ['glass', 'light', 'neon', 'midnight', 'aurora', 'high-contrast'];

// Meta theme-color mapping per theme
const THEME_META_COLORS = {
    glass: '#0f111a',
    neon: '#050505',
    midnight: '#000000',
    light: '#f0f4f8',
    aurora: '#141020',
    'high-contrast': '#000000'
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
        const activateTheme = () => {
            const theme = card.dataset.theme;
            applyTheme(theme);
            saveSettings('voxdoc_theme', theme);
        };
        card.addEventListener('click', activateTheme);
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                activateTheme();
            }
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
async function init() {
    setupNavigation();
    setupAuth();
    setupRecording();
    setupTextInput();
    setupImageUpload();
    setupSubmit();
    setupActions();
    setupSOAPActions();
    setupSettings();
    await refreshCurrentUser();
    await loadSessionHistory();
    setupPDFExport();
    setupPWA();
}

// =====================================================
// PWA & OFFLINE SETUP
// =====================================================

function setupPWA() {
    // 1. Register Service Worker
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/service-worker.js')
                .then(reg => console.log('SW registered!', reg))
                .catch(err => console.error('SW registration failed', err));
        });
    }

    // 2. Handle Network Status
    const updateOnlineStatus = () => {
        state.isOffline = !navigator.onLine;
        if (state.isOffline) {
            elements.offlineBadge?.classList.remove('hidden');
            console.warn("App is offline. API calls may fail.");
        } else {
            elements.offlineBadge?.classList.add('hidden');
            console.log("App is back online. Attempting to sync...");
            syncOfflineQueue();
        }
    };

    window.addEventListener('online', updateOnlineStatus);
    window.addEventListener('offline', updateOnlineStatus);
    updateOnlineStatus(); // Set initial

    // 3. Handle Install Prompt
    window.addEventListener('beforeinstallprompt', (e) => {
        // Prevent Chrome 67 and earlier from automatically showing the prompt
        e.preventDefault();
        // Stash the event so it can be triggered later.
        state.deferredInstallPrompt = e;
        // Update UI to notify the user they can add to home screen
        elements.installAppBtn?.classList.remove('hidden');
    });

    elements.installAppBtn?.addEventListener('click', async () => {
        if (!state.deferredInstallPrompt) return;

        // Show the prompt
        state.deferredInstallPrompt.prompt();
        // Wait for the user to respond to the prompt
        const { outcome } = await state.deferredInstallPrompt.userChoice;
        console.log(`User response to the install prompt: ${outcome}`);

        // We've used the prompt, and can't use it again, throw it away
        state.deferredInstallPrompt = null;
        elements.installAppBtn.classList.add('hidden');
    });

    window.addEventListener('appinstalled', () => {
        // Hide the app-provided install promotion
        elements.installAppBtn?.classList.add('hidden');
        // Clear the deferredPrompt so it can be garbage collected
        state.deferredInstallPrompt = null;
        console.log('PWA was installed');
    });
}

// Simple IndexedDB wrapper for Offline Queue
const dbPromise = (() => {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('VoxDocDB', 1);
        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains('offlineQueue')) {
                db.createObjectStore('offlineQueue', { keyPath: 'id' });
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
})();

async function saveToOfflineQueue(type, data) {
    try {
        const db = await dbPromise;
        const tx = db.transaction('offlineQueue', 'readwrite');
        const store = tx.objectStore('offlineQueue');
        const item = {
            id: Date.now().toString(),
            timestamp: new Date().toISOString(),
            type: type, // 'audio' or 'text'
            data: data
        };
        await new Promise((resolve, reject) => {
            const req = store.add(item);
            req.onsuccess = resolve;
            req.onerror = reject;
        });
        alert(`You are offline. ${type === 'audio' ? 'Recording' : 'Text'} saved locally and will sync when reconnected.`);
    } catch (e) {
        console.error("Failed to save to offline queue", e);
    }
}

async function syncOfflineQueue() {
    try {
        const db = await dbPromise;
        const tx = db.transaction('offlineQueue', 'readonly');
        const store = tx.objectStore('offlineQueue');
        const req = store.getAll();

        req.onsuccess = async () => {
            const items = req.result;
            if (!items || items.length === 0) return;

            console.log(`Syncing ${items.length} offline items...`);

            for (const item of items) {
                try {
                    if (item.type === 'audio') {
                        // Re-submit audio
                        const formData = new FormData();
                        formData.append('audio', item.data.blob, "offline_recording.webm");
                        // Assuming a submitAudio function exists or re-implementing the logic here
                        const response = await apiFetch('/api/voice-intake', {
                            method: 'POST',
                            body: formData
                        });
                        if (!response.ok) throw new Error('Failed to re-submit audio');
                        // Process response if needed, for now just delete from queue
                    } else if (item.type === 'text') {
                        // Re-submit text
                        // Assuming a submitText function exists or re-implementing the logic here
                        const response = await apiFetch('/api/document', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ transcript: item.data.text })
                        });
                        if (!response.ok) throw new Error('Failed to re-submit text');
                        // Process response if needed
                    }

                    // On success, clean from queue
                    const delTx = db.transaction('offlineQueue', 'readwrite');
                    delTx.objectStore('offlineQueue').delete(item.id);
                } catch (e) {
                    console.error("Sync failed for item", item.id, e);
                    // Leave in queue
                }
            }
            console.log("Offline sync complete");
        };
    } catch (e) {
        console.error("Failed to access offline queue for sync", e);
    }
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
    const monitoringBtn = document.querySelector('[data-tab="monitoring"]');
    const hipaaBtn = document.querySelector('[data-tab="hipaa"]');

    // Views
    const dashboardView = document.getElementById('dashboardView');
    const settingsView = document.getElementById('settingsView');
    const historyView = document.getElementById('historyView');
    const monitoringView = document.getElementById('monitoringView');
    const hipaaView = document.getElementById('hipaaView');

    const allViews = [dashboardView, settingsView, historyView, monitoringView, hipaaView];
    const allBtns = [dashboardBtn, settingsBtn, historyBtn, monitoringBtn, hipaaBtn];

    function setActiveTab(activeBtn) {
        allBtns.forEach(btn => { if (btn) btn.classList.remove('active'); });
        if (activeBtn) activeBtn.classList.add('active');
        closeSidebar();
    }

    function hideAllViews() {
        allViews.forEach(v => { if (v) v.classList.add('hidden'); });
    }

    function handleNavKeydown(e, actionObj) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            actionObj.click();
        }
    }

    if (dashboardBtn) {
        dashboardBtn.addEventListener('click', () => {
            setActiveTab(dashboardBtn);
            hideAllViews();
            if (dashboardView) dashboardView.classList.remove('hidden');
        });
        dashboardBtn.addEventListener('keydown', (e) => handleNavKeydown(e, dashboardBtn));
    }

    if (historyBtn) {
        historyBtn.addEventListener('click', () => {
            setActiveTab(historyBtn);
            hideAllViews();
            if (historyView) historyView.classList.remove('hidden');
            renderHistoryView();
        });
        historyBtn.addEventListener('keydown', (e) => handleNavKeydown(e, historyBtn));
    }

    if (settingsBtn) {
        settingsBtn.addEventListener('click', () => {
            setActiveTab(settingsBtn);
            hideAllViews();
            if (settingsView) settingsView.classList.remove('hidden');
            setupNeuralGraph();
        });
        settingsBtn.addEventListener('keydown', (e) => handleNavKeydown(e, settingsBtn));
    }

    if (monitoringBtn) {
        monitoringBtn.addEventListener('click', () => {
            setActiveTab(monitoringBtn);
            hideAllViews();
            if (monitoringView) monitoringView.classList.remove('hidden');
            loadMonitoringDashboard();
        });
        monitoringBtn.addEventListener('keydown', (e) => handleNavKeydown(e, monitoringBtn));
    }

    if (hipaaBtn) {
        hipaaBtn.addEventListener('click', () => {
            setActiveTab(hipaaBtn);
            hideAllViews();
            if (hipaaView) hipaaView.classList.remove('hidden');
            loadHipaaDashboard();
        });
        hipaaBtn.addEventListener('keydown', (e) => handleNavKeydown(e, hipaaBtn));
    }

    // Refresh button in monitoring view
    const refreshBtn = document.getElementById('refreshMonitoring');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadMonitoringDashboard);
    }

    // HIPAA refresh and purge buttons
    const refreshHipaaBtn = document.getElementById('refreshHipaa');
    if (refreshHipaaBtn) {
        refreshHipaaBtn.addEventListener('click', loadHipaaDashboard);
    }

    const purgeBtn = document.getElementById('hipaaPurgeBtn');
    if (purgeBtn) {
        purgeBtn.addEventListener('click', runHipaaPurge);
    }
}

function renderHistoryView() {
    const historyGrid = document.getElementById('historyGrid');
    const emptyState = document.getElementById('historyEmptyState');
    if (!historyGrid || !emptyState) return;

    if (!state.sessionHistory || state.sessionHistory.length === 0) {
        historyGrid.innerHTML = '';
        historyGrid.classList.add('hidden');
        emptyState.classList.remove('hidden');
        return;
    }

    emptyState.classList.add('hidden');
    historyGrid.classList.remove('hidden');

    historyGrid.innerHTML = state.sessionHistory.map(session => {
        const date = new Date(session.timestamp);
        const displayDate = date.toLocaleDateString(undefined, { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
        const displayTime = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

        return `
        <div class="history-card" data-id="${session.id}" role="button" tabindex="0">
            <div class="history-card-header">
                <div>
                    <h4>${escapeHTML(truncate(session.chiefComplaint, 40))}</h4>
                    <span class="history-date">${displayDate} at ${displayTime}</span>
                </div>
                <div class="doc-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                        <line x1="16" y1="13" x2="8" y2="13" />
                        <line x1="16" y1="17" x2="8" y2="17" />
                        <polyline points="10 9 9 9 8 9" />
                    </svg>
                </div>
            </div>
            <div class="history-card-body">
                <p><strong>Subjective:</strong> ${escapeHTML(truncate(session.soapS || '', 80))}</p>
                <p><strong>Assessment:</strong> ${escapeHTML(truncate(session.soapA || '', 80))}</p>
            </div>
            <div class="history-card-footer">
                <button class="load-session-btn" data-id="${session.id}">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
                        <polyline points="9 18 15 12 9 6" />
                    </svg>
                    View Details
                </button>
            </div>
        </div>
        `;
    }).join('');

    // Attach click listeners to load session
    document.querySelectorAll('.history-card').forEach(card => {
        const id = card.getAttribute('data-id');
        card.addEventListener('click', (e) => loadSessionIntoDashboard(id));
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                loadSessionIntoDashboard(id);
            }
        });
    });
}

async function loadSessionIntoDashboard(sessionId) {
    try {
        if (!requireAuthentication()) return;
        const response = await apiFetch(`/api/sessions/${sessionId}`, { method: 'GET' });
        if (!response.ok) throw new Error('Failed to fetch session');
        
        const session = await response.json();
        
        // Populate UI
        elements.transcriptionText.textContent = session.transcript || 'N/A';
        
        // Mock documentation object shape for displayResults
        const mockData = {
            transcript: session.transcript || 'N/A',
            detected_language: session.detected_language || 'en',
            documentation: {
                chief_complaint: session.chief_complaint || 'N/A',
                symptom_details: {
                    symptoms_mentioned: ["Loaded from history"],
                    onset: "N/A", duration: "N/A", location: "N/A", aggravating_factors: "N/A", severity_description: "N/A"
                },
                field_confidence: {
                    chief_complaint: { score: 0.45, color: "yellow", verification_text: "Needs quick verification" },
                    symptom_details: {
                        symptoms_mentioned: { score: 0.45, color: "yellow", verification_text: "Needs quick verification" },
                        onset: { score: 0.30, color: "red", verification_text: "Needs verification" },
                        duration: { score: 0.30, color: "red", verification_text: "Needs verification" },
                        location: { score: 0.30, color: "red", verification_text: "Needs verification" },
                        aggravating_factors: { score: 0.30, color: "red", verification_text: "Needs verification" },
                        severity_description: { score: 0.25, color: "red", verification_text: "Needs verification" }
                    }
                },
                soap_note_subjective: session.soap_subjective || '',
                soap_note_objective: session.soap_objective || '',
                soap_note_assessment: session.soap_assessment || '',
                soap_note_plan: session.soap_plan || ''
            },
            extracted_entities: { conditions: [], medications: [] },
            compliance_metadata: {
                hipaa: { minimum_necessary_mode: true },
                medgemma_terms: { acknowledged: true }
            }
        };
        
        state.currentDocumentation = mockData;
        displayResults(mockData);
        
        // Switch to dashboard view
        const dashboardBtn = document.querySelector('[data-tab="dashboard"]');
        if (dashboardBtn) dashboardBtn.click();
        
    } catch (e) {
        console.error("Failed to load session into dashboard", e);
        alert("Failed to load session details.");
    }
}

function openSidebar() {
    elements.sidebar?.classList.add('open');
    elements.sidebarOverlay?.classList.add('active');
    elements.openSidebarBtn?.setAttribute('aria-expanded', 'true');
    // Focus management for accessibility
    document.querySelector('[data-tab="dashboard"]')?.focus();
}

function closeSidebar() {
    elements.sidebar?.classList.remove('open');
    elements.sidebarOverlay?.classList.remove('active');
    elements.openSidebarBtn?.setAttribute('aria-expanded', 'false');
    // Return focus if on mobile
    if (window.innerWidth < 1024) {
        elements.openSidebarBtn?.focus();
    }
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
        if (!requireAuthentication()) return;
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
        elements.recordBtn?.setAttribute('aria-pressed', 'true');
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
        elements.recordBtn?.setAttribute('aria-pressed', 'false');
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
        elements.recordingTime.textContent = `${ minutes }: ${ seconds }`;
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

// =====================================================
// IMAGE UPLOAD
// =====================================================
function setupImageUpload() {
    if (!elements.imageDropZone || !elements.imageFileInput) return;

    // Click to open file dialog
    elements.imageDropZone.addEventListener('click', (e) => {
        // Prevent click if clicking the remove button
        if (!e.target.closest('.remove-image-btn')) {
            elements.imageFileInput.click();
        }
    });

    // Keyboard space/enter to open file dialog
    elements.imageDropZone.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (!e.target.closest('.remove-image-btn')) {
                elements.imageFileInput.click();
            }
        }
    });

    // File input change
    elements.imageFileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            handleImageSelection(e.target.files[0]);
        }
    });

    // Drag and Drop
    elements.imageDropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        elements.imageDropZone.classList.add('drag-over');
    });

    elements.imageDropZone.addEventListener('dragleave', () => {
        elements.imageDropZone.classList.remove('drag-over');
    });

    elements.imageDropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        elements.imageDropZone.classList.remove('drag-over');

        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            handleImageSelection(e.dataTransfer.files[0]);
        }
    });

    // Remove Image
    elements.removeImageBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        clearImageSelection();
    });
}

function handleImageSelection(file) {
    // Validate file type
    const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/jpg'];
    if (!validTypes.includes(file.type)) {
        alert('Please select a valid image file (JPEG, PNG, WebP).');
        return;
    }

    // Validate file size (10MB max)
    const maxSize = 10 * 1024 * 1024;
    if (file.size > maxSize) {
        alert(`File is too large(${(file.size / (1024 * 1024)).toFixed(1)}MB). Max allowed size is 10MB.`);
        return;
    }

    state.uploadedImageFile = file;

    // Update UI
    const reader = new FileReader();
    reader.onload = (e) => {
        elements.imagePreview.src = e.target.result;
        elements.imageFilename.textContent = file.name;
        elements.imageFilesize.textContent = formatBytes(file.size);

        elements.dropZoneContent.classList.add('hidden');
        elements.imagePreviewContainer.classList.remove('hidden');

        updateSubmitButton();
    };
    reader.readAsDataURL(file);
}

function clearImageSelection() {
    state.uploadedImageFile = null;
    state.imageAnalysis = null;

    // Reset file input
    elements.imageFileInput.value = '';

    // Update UI
    elements.dropZoneContent.classList.remove('hidden');
    elements.imagePreviewContainer.classList.add('hidden');
    elements.imagePreview.src = '';

    updateSubmitButton();
}

function formatBytes(bytes, decimals = 1) {
    if (!+bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${ parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) } ${ sizes[i] } `;
}

function updateSubmitButton() {
    const hasAudio = state.audioBlob !== null;
    const textContent = elements.textInput?.value.trim();
    const hasLiveTranscript = state.liveTranscript && state.liveTranscript.trim().length > 0;
    const hasImage = state.uploadedImageFile !== null;

    if (elements.submitBtn) {
        elements.submitBtn.disabled = !(hasAudio || textContent || hasLiveTranscript || hasImage);
    }
}

// =====================================================
// SUBMIT & PROCESSING
// =====================================================
function setupSubmit() {
    elements.submitBtn?.addEventListener('click', processInput);

    // Follow-up questions: submit answers
    elements.followupSubmitBtn?.addEventListener('click', async () => {
        const qa = collectFollowupAnswers();
        const payload = { ...state.pendingDocPayload };
        if (qa.length > 0) {
            payload.followup_qa = qa;
        }
        await generateDocumentation(payload, state.pendingHasAudio);
    });

    // Follow-up questions: skip
    elements.followupSkipBtn?.addEventListener('click', async () => {
        await generateDocumentation(state.pendingDocPayload, state.pendingHasAudio);
    });
}

async function processInput() {
    const hasAudio = state.audioBlob !== null;
    const textContent = elements.textInput?.value.trim();
    const hasLiveTranscript = state.liveTranscript && state.liveTranscript.trim().length > 0;
    const hasImage = state.uploadedImageFile !== null;

    if (!hasAudio && !textContent && !hasLiveTranscript && !hasImage) return;
    if (!requireAuthentication()) return;

    // Hide live transcript and show loading
    hideLiveTranscript();
    showLoading();

    // Update loading text
    if (hasImage) {
        elements.imagePreviewContainer.classList.add('hidden');
        elements.imageAnalyzingState.classList.remove('hidden');
        elements.transcriptTitle.textContent = 'Analyzing Image...';
    }

    try {
        let response;
        let imageFindingsData = null;

        // 1. Process image first if present
        if (hasImage) {
            const imageFormData = new FormData();
            imageFormData.append('image', state.uploadedImageFile);

            const imgResponse = await apiFetch('/api/analyze-image', {
                method: 'POST',
                body: imageFormData
            });

            if (!imgResponse.ok) {
                const errorData = await imgResponse.json();
                throw new Error(`Image analysis failed: ${ errorData.detail || 'Unknown error' } `);
            }

            const imgResult = await imgResponse.json();
            imageFindingsData = imgResult.image_analysis;
            state.imageAnalysis = imageFindingsData;

            elements.imageAnalyzingState.classList.add('hidden');
            elements.imagePreviewContainer.classList.remove('hidden');
            elements.transcriptTitle.textContent = 'Generating Documentation...';
        }

        // 2. Determine what transcript to use for documentation
        let documentPayload = {};

        if (hasLiveTranscript && state.streamingMode) {
            documentPayload = { transcript: state.liveTranscript };
        } else if (hasAudio && !state.streamingMode) {
            // Transcribe audio first via voice-intake
            const formData = new FormData();
            formData.append('audio', state.audioBlob, 'recording.webm');

            try {
                response = await apiFetch('/api/voice-intake', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || 'Processing failed');
                }

                const data = await response.json();
                documentPayload = { transcript: data.transcript };
            } catch (error) {
                console.error('Audio processing error:', error);
                if (state.isOffline || error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
                    await saveToOfflineQueue('audio', { blob: state.audioBlob });
                    showError('You are offline. Audio saved locally and will sync when reconnected.');
                    return;
                } else {
                    throw error;
                }
            }
        } else if (textContent) {
            documentPayload = { transcript: textContent };
        } else if (hasImage) {
            // Image-only: use image findings as the transcript context
            const findingsText = imageFindingsData?.visual_findings_text || '';
            documentPayload = { transcript: `Patient uploaded a medical image. Visual findings: ${findingsText}` };
        }

        // Add image findings to the document payload if available
        if (imageFindingsData) {
            documentPayload.image_findings = imageFindingsData.visual_findings_text;
        }

        // 3. Ask follow-up questions before generating documentation
        if (Object.keys(documentPayload).length > 0) {
            // Store payload for later use by follow-up handlers
            state.pendingDocPayload = documentPayload;
            state.pendingHasAudio = hasAudio;

            // Build transcript context for follow-up questions
            // Include image findings so questions are relevant to visual findings too
            let followupTranscript = documentPayload.transcript;
            if (imageFindingsData?.visual_findings_text && !followupTranscript.includes(imageFindingsData.visual_findings_text)) {
                followupTranscript += ` Visual findings from uploaded image: ${imageFindingsData.visual_findings_text}`;
            }

            try {
                const fqResponse = await apiFetch('/api/intake/questions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ transcript: followupTranscript })
                });

                if (fqResponse.ok) {
                    const fqData = await fqResponse.json();
                    if (fqData.questions && fqData.questions.length > 0) {
                        renderFollowupQuestions(fqData.questions);
                        showFollowup();
                        return; // Wait for user to submit or skip
                    }
                }
            } catch (err) {
                console.warn('Follow-up questions unavailable, proceeding directly:', err.message);
            }

            // If follow-up questions failed or returned none, generate directly
            await generateDocumentation(documentPayload, hasAudio);
        }

    } catch (error) {
        console.error('Processing error:', error);

        // Reset image UI on error
        if (state.uploadedImageFile) {
            elements.imageAnalyzingState?.classList.add('hidden');
            elements.imagePreviewContainer?.classList.remove('hidden');
        }

        showError(error.message);
    }
}

function renderFollowupQuestions(questions) {
    if (!elements.followupQuestions) return;
    elements.followupQuestions.innerHTML = questions.map((q, i) => `
        <div class="followup-question-item">
            <label for="followupAnswer${i}">${i + 1}. ${q}</label>
            <textarea id="followupAnswer${i}" rows="2" placeholder="Type your answer..."></textarea>
        </div>
    `).join('');
}

function collectFollowupAnswers() {
    const items = elements.followupQuestions?.querySelectorAll('.followup-question-item') || [];
    const qa = [];
    items.forEach((item, i) => {
        const question = item.querySelector('label')?.textContent?.replace(/^\d+\.\s*/, '') || '';
        const answer = item.querySelector('textarea')?.value?.trim() || '';
        if (question) {
            qa.push({ question, answer });
        }
    });
    return qa;
}

async function generateDocumentation(payload, hasAudio) {
    showLoading();
    try {
        const response = await apiFetch('/api/document', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Documentation generation failed: ${errorData.detail || 'Unknown error'}`);
        }

        let data = await response.json();

        data.transcript = payload.transcript;
        data.duration_seconds = state.recordingStartTime && hasAudio
            ? (Date.now() - state.recordingStartTime) / 1000
            : 0;

        state.currentDocumentation = data;
        displayResults(data);
    } catch (error) {
        console.error('Documentation generation error:', error);
        if (state.isOffline || error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
            showError('You are offline. Could not generate documentation. Please try again when online.');
        } else {
            showError(error.message);
        }
    }
}

// =====================================================
// UI STATE MANAGEMENT
// =====================================================
function hideAllStates() {
    elements.emptyState?.classList.add('hidden');
    elements.resultsContainer?.classList.add('hidden');
    elements.liveTranscriptState?.classList.add('hidden');
    elements.loadingState?.classList.add('hidden');
    elements.followupState?.classList.add('hidden');
}

function showLoading() {
    hideAllStates();
    elements.loadingState?.classList.remove('hidden');
    elements.transcriptTitle.textContent = 'Processing...';
    const msgEl = document.getElementById('loadingMessage');
    if (msgEl) msgEl.textContent = 'Processing and generating documentation...';
    startQueuePolling();
}

function showFollowup() {
    hideAllStates();
    elements.followupState?.classList.remove('hidden');
    elements.transcriptTitle.textContent = 'Follow-up Questions';
    hideQueueStatus();
}

function showResults() {
    hideAllStates();
    elements.resultsContainer?.classList.remove('hidden');
    elements.transcriptTitle.textContent = 'Documentation Results';
    hideQueueStatus();
}

function showError(message) {
    hideAllStates();
    elements.transcriptTitle.textContent = 'Error';
    hideQueueStatus();

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

    // Detected Language Badge
    const langBadge = document.getElementById('detectedLanguageBadge');
    if (langBadge) {
        if (data.detected_language && data.detected_language !== 'en') {
            langBadge.textContent = 'Detected: ' + data.detected_language.toUpperCase();
            langBadge.classList.remove('hidden');
        } else {
            langBadge.classList.add('hidden');
        }
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
    const doc = data.documentation || {};
    renderComplianceNotice(data, doc);

    if (elements.chiefComplaint) {
        elements.chiefComplaint.textContent = doc.chief_complaint || 'N/A';
    }

    // Symptom Details with field-level extraction confidence
    if (elements.symptomDetails && doc.symptom_details) {
        elements.symptomDetails.innerHTML = buildSymptomDetailsHtml(doc);
    }

    // SOAP Notes + CC/CD/VI — populate and store originals
    let soapMap = {
        soapS: doc.soap_note_subjective || 'Patient describes symptoms.',
        soapO: doc.soap_note_objective || 'Pending clinician assessment.',
        soapA: doc.soap_note_assessment || 'Pending clinician assessment.',
        soapP: doc.soap_note_plan || 'Pending clinician assessment.',
        chiefComplaint: doc.chief_complaint || 'N/A',
        symptomDetails: elements.symptomDetails?.innerHTML || 'N/A',
    };

    // Handle Image Analysis Display
    if (state.imageAnalysis && elements.imageFindingsCard && elements.visualFindings) {
        const viText = state.imageAnalysis.visual_findings_text || state.imageAnalysis.description;

        elements.imageFindingsCard.classList.remove('hidden');
        elements.visualFindings.textContent = viText;
        soapMap.visualFindings = viText;

        // Show thumbnail
        if (elements.imageFindingsThumbnailContainer && state.uploadedImageFile) {
            const reader = new FileReader();
            reader.onload = (e) => {
                elements.imageFindingsThumbnailContainer.innerHTML = `
        <img src="${e.target.result}" class="findings-thumbnail" alt="Uploaded finding">
            <div class="findings-meta">
                <strong>Uploaded Document</strong>
                <span>Body Area: ${state.imageAnalysis.body_area || 'Not specified'}</span><br>
                    <span>Size: ${formatBytes(state.uploadedImageFile.size)}</span>
            </div>
    `;
                elements.imageFindingsThumbnailContainer.classList.add('active');
            };
            reader.readAsDataURL(state.uploadedImageFile);
        }
    } else if (elements.imageFindingsCard) {
        elements.imageFindingsCard.classList.add('hidden');
        if (elements.imageFindingsThumbnailContainer) {
            elements.imageFindingsThumbnailContainer.classList.remove('active');
        }
    }

    for (const [id, text] of Object.entries(soapMap)) {
        if (elements[id] && id !== 'visualFindings') {
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
        clinical_details: { status: 'pending', edited: false, originalText: soapMap.symptomDetails, history: [] },
        visual_findings: { status: 'pending', edited: false, originalText: soapMap.visualFindings || '', history: [] }
    };

    // Log initial generation event
    for (const section of Object.keys(state.soapApprovals)) {
        logSOAPHistory(section, 'generated', 'AI-generated content');
    }

    resetSOAPCardStates();

    // Display NER Extracted Entities
    displayNEREntities(data.extracted_entities);
}

function renderComplianceNotice(data, doc) {
    const complianceEl = document.getElementById('complianceMetaNotice');
    if (!complianceEl) return;

    const metadata = data.compliance_metadata || doc.compliance_metadata || {};
    const hipaa = metadata.hipaa || {};
    const medgemmaTerms = metadata.medgemma_terms || {};

    const hipaaText = hipaa.minimum_necessary_mode === false
        ? 'PHI persistence is enabled. Validate BAA, encryption, and audit controls.'
        : 'HIPAA minimum-necessary mode active (PHI persistence disabled).';
    const termsText = medgemmaTerms.acknowledged
        ? 'MedGemma terms acknowledged.'
        : 'MedGemma terms acknowledgement pending.';

    complianceEl.textContent = `${hipaaText} ${termsText}`;
}

function buildSymptomDetailsHtml(doc) {
    const details = doc.symptom_details || {};
    const confidenceMap = doc.field_confidence?.symptom_details || {};
    const chiefComplaintConfidence = doc.field_confidence?.chief_complaint;

    const rows = [
        {
            label: 'Chief Complaint',
            value: doc.chief_complaint || 'not specified',
            confidence: chiefComplaintConfidence
        },
        {
            label: 'Symptoms',
            value: formatSymptomFieldValue(details.symptoms_mentioned),
            confidence: confidenceMap.symptoms_mentioned
        },
        {
            label: 'Onset',
            value: formatSymptomFieldValue(details.onset),
            confidence: confidenceMap.onset
        },
        {
            label: 'Duration',
            value: formatSymptomFieldValue(details.duration),
            confidence: confidenceMap.duration
        },
        {
            label: 'Location',
            value: formatSymptomFieldValue(details.location),
            confidence: confidenceMap.location
        },
        {
            label: 'Aggravating Factors',
            value: formatSymptomFieldValue(details.aggravating_factors),
            confidence: confidenceMap.aggravating_factors
        },
        {
            label: 'Severity Description',
            value: formatSymptomFieldValue(details.severity_description),
            confidence: confidenceMap.severity_description
        }
    ];

    return `<ul class="confidence-list">${rows.map(renderConfidenceRow).join('')}</ul>`;
}

function formatSymptomFieldValue(value) {
    if (Array.isArray(value)) {
        return value.length ? value.join(', ') : 'not specified';
    }

    if (value === null || value === undefined) {
        return 'not specified';
    }

    const strValue = String(value).trim();
    return strValue.length > 0 ? strValue : 'not specified';
}

function renderConfidenceRow(row) {
    const confidence = normalizeConfidenceRecord(row.confidence);
    const badge = buildConfidenceBadge(confidence);

    return `
        <li class="confidence-row">
            <div class="confidence-field"><strong>${escapeHTML(row.label)}:</strong> ${escapeHTML(row.value)}</div>
            ${badge}
        </li>
    `;
}

function normalizeConfidenceRecord(record) {
    const defaultScore = 0.30;
    const rawScore = typeof record?.score === 'number' ? record.score : defaultScore;
    const score = Math.max(0, Math.min(1, rawScore));

    let color = record?.color;
    if (!color) {
        color = score >= 0.8 ? 'green' : (score >= 0.55 ? 'yellow' : 'red');
    }

    const verificationText = record?.verification_text
        || (color === 'green' ? 'High confidence' : color === 'yellow' ? 'Needs quick verification' : 'Needs verification');

    return {
        score,
        color,
        verificationText,
        rationale: record?.rationale || 'No confidence metadata provided.'
    };
}

function buildConfidenceBadge(confidence) {
    const percent = Math.round(confidence.score * 100);
    const colorClass = confidence.color === 'green'
        ? 'confidence-green'
        : confidence.color === 'yellow'
            ? 'confidence-yellow'
            : 'confidence-red';

    return `
        <span class="confidence-pill ${colorClass}" title="${escapeHTML(confidence.rationale)}">
            ${escapeHTML(confidence.verificationText)} (${percent}%)
        </span>
    `;
}

/**
 * Render extracted NER entities as styled badges.
 * @param {Object} entities - { conditions: [...], medications: [...] }
 */
function displayNEREntities(entities) {
    if (!entities || (!entities.conditions?.length && !entities.medications?.length)) {
        // Hide the card if no entities
        elements.nerEntitiesCard?.classList.add('hidden');
        return;
    }

    elements.nerEntitiesCard?.classList.remove('hidden');

    const totalCount = (entities.conditions?.length || 0) + (entities.medications?.length || 0);
    if (elements.nerEntityCount) {
        elements.nerEntityCount.textContent = `${ totalCount } ${ totalCount === 1 ? 'entity' : 'entities' } `;
    }

    // Render Conditions
    if (elements.nerConditionBadges) {
        if (entities.conditions && entities.conditions.length > 0) {
            elements.nerConditionBadges.innerHTML = entities.conditions.map(ent =>
                `<span class="entity-badge entity-condition" title="${ent.system}: ${ent.code}">
                    <span class="entity-name">${escapeHTML(ent.text)}</span>
                    <span class="entity-code">${ent.system}: ${ent.code}</span>
                </span>`
            ).join('');
            document.getElementById('nerConditions')?.classList.remove('hidden');
        } else {
            elements.nerConditionBadges.innerHTML = '<span class="ner-empty-state">None detected</span>';
        }
    }

    // Render Medications
    if (elements.nerMedicationBadges) {
        if (entities.medications && entities.medications.length > 0) {
            elements.nerMedicationBadges.innerHTML = entities.medications.map(ent =>
                `<span class="entity-badge entity-medication" title="${ent.system}: ${ent.code}">
                    <span class="entity-name">${escapeHTML(ent.text)}</span>
                    <span class="entity-code">${ent.system}: ${ent.code}</span>
                </span>`
            ).join('');
            document.getElementById('nerMedications')?.classList.remove('hidden');
        } else {
            elements.nerMedicationBadges.innerHTML = '<span class="ner-empty-state">None detected</span>';
        }
    }
}

// =====================================================
// ACTIONS (Copy, Export)
// =====================================================
function setupActions() {
    elements.copyBtn?.addEventListener('click', copyToClipboard);
    elements.exportBtn?.addEventListener('click', exportJSON);
    elements.fhirExportBtn?.addEventListener('click', downloadFHIRBundle);
    elements.ehrPushBtn?.addEventListener('click', () => {
        elements.ehrModal?.classList.remove('hidden');
    });
    elements.ehrModalClose?.addEventListener('click', () => {
        elements.ehrModal?.classList.add('hidden');
    });
    elements.ehrModalCancel?.addEventListener('click', () => {
        elements.ehrModal?.classList.add('hidden');
    });
    elements.ehrModal?.querySelector('.ehr-modal-backdrop')?.addEventListener('click', () => {
        elements.ehrModal?.classList.add('hidden');
    });
    elements.ehrModalSubmit?.addEventListener('click', pushToEHR);

    // EHR preset buttons
    document.querySelectorAll('.ehr-preset-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            if (elements.ehrServerUrl) {
                elements.ehrServerUrl.value = btn.dataset.url;
            }
        });
    });
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
CHIEF COMPLAINT: ${ doc.chief_complaint }

SYMPTOM DETAILS:
    - Symptoms: ${ Array.isArray(doc.symptom_details?.symptoms_mentioned) ? doc.symptom_details.symptoms_mentioned.join(', ') : (doc.symptom_details?.symptoms || 'N/A') }
    - Onset: ${ doc.symptom_details?.onset || 'N/A' }
    - Duration: ${ doc.symptom_details?.duration || 'N/A' }
    - Location: ${ doc.symptom_details?.location || 'N/A' }

SOAP NOTE:

    S(Subjective)[${ state.soapApprovals.subjective.status }]:
${ soapS }

    O(Objective)[${ state.soapApprovals.objective.status }]:
${ soapO }

    A(Assessment)[${ state.soapApprovals.assessment.status }]:
${ soapA }

    P(Plan)[${ state.soapApprovals.plan.status }]:
${ soapP }
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
    a.download = `voxdoc_${ new Date().toISOString().slice(0, 10) }.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

async function downloadFHIRBundle() {
    if (!state.currentDocumentation) return;
    if (!requireAuthentication()) return;

    try {
        elements.fhirExportBtn.classList.add('loading');

        const response = await apiFetch('/api/fhir/export', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                documentation: state.currentDocumentation.documentation,
                extracted_entities: state.currentDocumentation.extracted_entities
            })
        });

        if (!response.ok) throw new Error('FHIR export failed');

        const bundle = await response.json();
        const dataStr = JSON.stringify(bundle, null, 2);
        const blob = new Blob([dataStr], { type: 'application/fhir+json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `fhir_bundle_${ new Date().toISOString().slice(0, 10) }.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (error) {
        console.error('FHIR Download error:', error);
        alert('Failed to generate FHIR Bundle. Please check the console.');
    } finally {
        elements.fhirExportBtn.classList.remove('loading');
    }
}

async function pushToEHR() {
    if (!state.currentDocumentation) return;
    if (!requireAuthentication()) return;

    const ehrUrl = elements.ehrServerUrl?.value;
    if (!ehrUrl) {
        alert("Please enter a valid FHIR Server URL.");
        return;
    }

    try {
        elements.ehrModalSubmit.disabled = true;
        elements.ehrModalSubmit.innerHTML = '<div class="spinner"></div> Pushing...';

        const response = await apiFetch('/api/fhir/push', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                documentation: state.currentDocumentation.documentation,
                extracted_entities: state.currentDocumentation.extracted_entities,
                ehr_url: ehrUrl,
                auth_token: elements.ehrAuthToken?.value || null
            })
        });

        const result = await response.json();

        if (result.success) {
            alert(`Success! Bundle pushed to EHR(Status: ${ result.status_code })`);
            elements.ehrModal?.classList.add('hidden');
        } else {
            console.error(result.error);
            alert(`Failed to push to EHR: ${ result.error } `);
        }
    } catch (error) {
        console.error("EHR Push error:", error);
        alert("Network error occurred while pushing to EHR.");
    } finally {
        elements.ehrModalSubmit.disabled = false;
        elements.ehrModalSubmit.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" aria-hidden="true">
                <polyline points="16 6 12 2 8 6" />
                <line x1="12" y1="2" x2="12" y2="15" />
        </svg>
        Push Bundle
        `;
    }
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
    ['subjective', 'objective', 'assessment', 'plan', 'visual_findings'].forEach(section => {
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
        elements.soapOverallStatus.textContent = `${ rejectedCount } rejected · ${ total - approvedCount - rejectedCount } pending`;
        elements.soapOverallStatus.className = 'badge warning';
    } else {
        elements.soapOverallStatus.textContent = `${ total - approvedCount } of ${ total } pending review`;
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
    logSOAPHistory(section, 'rejected', reason ? `Rejected: ${ reason } ` : 'Rejected by clinician');

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
                detail = ` — ${ escapeHTML(truncate(plainText, 120)) } `;
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

    if (!confirm(`Are you sure you want to restore the original ${ section.replace('_', ' ') }? Current edits will be lost.`)) {
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
        clinical_details: 'symptomDetails',
        visual_findings: 'visualFindings'
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
        clinical_details: 'soapStatusCD',
        visual_findings: 'soapStatusVI'
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
        clinical_details: 'soapHistoryCD',
        visual_findings: 'soapHistoryVI'
    };
    return document.getElementById(map[section]) || null;
}

// =====================================================
// SESSION HISTORY & PDF EXPORT
// =====================================================

async function loadSessionHistory() {
    try {
        const response = await apiFetch('/api/sessions', { method: 'GET' });
        if (response.ok) {
            const data = await response.json();
            // Map the DB fields to what the UI expects
            state.sessionHistory = data.map(session => ({
                id: session.id,
                timestamp: session.created_at,
                patientName: session.patient_name || "Patient",
                chiefComplaint: session.chief_complaint || "N/A",
                clinicalDetails: "N/A", // This is not stored directly, could extract from SOAP
                visualFindings: "",
                soapS: session.soap_subjective || "",
                soapO: session.soap_objective || "",
                soapA: session.soap_assessment || "",
                soapP: session.soap_plan || ""
            }));
            updateRecentDocsUI();
            if (typeof renderHistoryView === 'function') {
                renderHistoryView();
            }
        } else {
            state.sessionHistory = [];
            updateRecentDocsUI();
            renderHistoryView();
        }
    } catch (e) {
        console.error('Failed to load session history', e);
    }
}

async function saveSessionToHistory() {
    if (!state.currentDocumentation) return;

    const doc = state.currentDocumentation.documentation;
    const sessionData = {
        patient_name: "Patient " + Math.floor(Math.random() * 1000), // Placeholder
        transcript: elements.transcriptionText ? elements.transcriptionText.textContent : 'N/A',
        detected_language: state.currentDocumentation.detected_language || 'en',
        chief_complaint: doc.chief_complaint || 'N/A',
        soap_subjective: elements.soapS ? elements.soapS.textContent : doc.soap_note_subjective,
        soap_objective: elements.soapO ? elements.soapO.textContent : doc.soap_note_objective,
        soap_assessment: elements.soapA ? elements.soapA.textContent : doc.soap_note_assessment,
        soap_plan: elements.soapP ? elements.soapP.textContent : doc.soap_note_plan
    };

    try {
        const response = await apiFetch('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sessionData)
        });

        if (response.ok) {
            await loadSessionHistory();
        }
    } catch (e) {
        console.error('Failed to save session to history', e);
    }
}

function updateRecentDocsUI() {
    const listEl = document.getElementById('recentDocsList');
    if (!listEl) return;

    if (state.sessionHistory.length === 0) {
        listEl.innerHTML = `<div class="recent-doc-item" style="color: var(--text-muted); font-style: italic; font-size: 0.8rem; justify-content: center; border: none;">No recent sessions</div>`;
        return;
    }

    listEl.innerHTML = state.sessionHistory.map(session => {
        const date = new Date(session.timestamp);
        const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const dateStr = date.toLocaleDateString();
        const displayTime = date.toDateString() === new Date().toDateString() ? `Today, ${ timeStr } ` : `${ dateStr }, ${ timeStr } `;

        return `
        <div class="recent-doc-item" data-id="${session.id}" role="button" tabindex="0" onclick="loadSessionIntoDashboard('${session.id}')" onkeydown="if(event.key==='Enter'||event.key===' ') { event.preventDefault(); loadSessionIntoDashboard('${session.id}'); }">
            <div class="doc-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="16" y1="13" x2="8" y2="13" />
                    <line x1="16" y1="17" x2="8" y2="17" />
                    <polyline points="10 9 9 9 8 9" />
                </svg>
            </div>
            <div class="doc-info">
                <div class="doc-title">${truncate(session.chiefComplaint, 25)}</div>
                <div class="doc-date">${displayTime}</div>
            </div>
        </div>
        `;
    }).join('');
}

function setupPDFExport() {
    if (elements.exportPdfBtn) {
        elements.exportPdfBtn.addEventListener('click', () => {
            if (!state.currentDocumentation) return;
            // Update the session in history before exporting to capture any edits
            saveSessionToHistory();
            exportSinglePDF(state.sessionHistory[0]);
        });
    }

    if (elements.batchExportBtn) {
        const handleBatchExport = () => {
            if (state.sessionHistory.length === 0) {
                alert('No sessions found in history to export.');
                return;
            }
            batchExportPDF();
        };

        elements.batchExportBtn.addEventListener('click', handleBatchExport);
        elements.batchExportBtn.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                handleBatchExport();
            }
        });
    }
}

function populatePDFTemplate(session) {
    const d = new Date(session.timestamp);
    document.getElementById('pdfDate').textContent = d.toLocaleDateString();
    document.getElementById('pdfTime').textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    document.getElementById('pdfChiefComplaint').textContent = session.chiefComplaint;
    document.getElementById('pdfClinicalDetails').innerHTML = session.clinicalDetails;

    if (session.visualFindings) {
        document.getElementById('pdfVisualFindingsContainer').style.display = 'block';
        document.getElementById('pdfVisualFindings').textContent = session.visualFindings;
    } else {
        document.getElementById('pdfVisualFindingsContainer').style.display = 'none';
    }

    document.getElementById('pdfSubjective').textContent = session.soapS;
    document.getElementById('pdfObjective').textContent = session.soapO;
    document.getElementById('pdfAssessment').textContent = session.soapA;
    document.getElementById('pdfPlan').textContent = session.soapP;
}

function exportSinglePDF(session) {
    const template = document.getElementById('pdfPrintTemplate');
    if (!template) return;

    populatePDFTemplate(session);

    template.parentElement.style.display = 'block';

    const opt = {
        margin: 0,
        filename: `VoxDoc_Report_${ session.id }.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2 },
        jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
    };

    html2pdf().set(opt).from(template).save().then(() => {
        template.parentElement.style.display = 'none';
    });
}

function batchExportPDF() {
    const containerItem = document.createElement('div');
    const template = document.getElementById('pdfPrintTemplate');

    // We clone the template for each session
    state.sessionHistory.forEach((session, index) => {
        populatePDFTemplate(session);
        const clone = template.cloneNode(true);
        clone.id = ''; // remove id duplicate

        containerItem.appendChild(clone);

        // Add page break if it's not the last item
        if (index < state.sessionHistory.length - 1) {
            const pageBreak = document.createElement('div');
            pageBreak.className = 'html2pdf__page-break';
            containerItem.appendChild(pageBreak);
        }
    });

    // Temporarily attach to DOM for html2pdf to render
    containerItem.style.display = 'none';
    document.body.appendChild(containerItem);

    const opt = {
        margin: 0,
        filename: `VoxDoc_Batch_Reports_${ Date.now() }.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2 },
        jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
    };

    html2pdf().set(opt).from(containerItem).save().then(() => {
        document.body.removeChild(containerItem);
    });
}

// =====================================================
// HIPAA COMPLIANCE DASHBOARD
// =====================================================

let hipaaAutoRefresh = null;

async function loadHipaaDashboard() {
    try {
        const [summaryResp, exportResp] = await Promise.all([
            apiFetch('/api/hipaa/audit-summary'),
            apiFetch('/api/hipaa/export-logs?limit=20'),
        ]);

        if (summaryResp.ok) {
            const data = await summaryResp.json();
            renderHipaaSummary(data);
        } else if (summaryResp.status === 403) {
            const hv = document.getElementById('hipaaView');
            if (hv) hv.innerHTML = '<p style="padding:20px;color:var(--text-secondary);">Admin access required for HIPAA dashboard.</p>';
            return;
        }

        if (exportResp.ok) {
            const logs = await exportResp.json();
            renderExportLogs(logs);
        }

        // Auto-refresh every 15s while on hipaa tab
        if (hipaaAutoRefresh) clearInterval(hipaaAutoRefresh);
        hipaaAutoRefresh = setInterval(async () => {
            const hv = document.getElementById('hipaaView');
            if (hv && !hv.classList.contains('hidden')) {
                try {
                    const r = await apiFetch('/api/hipaa/audit-summary');
                    if (r.ok) renderHipaaSummary(await r.json());
                } catch { /* ignore */ }
            } else {
                clearInterval(hipaaAutoRefresh);
                hipaaAutoRefresh = null;
            }
        }, 15000);
    } catch (e) {
        console.error('Failed to load HIPAA dashboard:', e);
    }
}

function renderHipaaSummary(data) {
    const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

    // Audit trail
    setTxt('hipaaTotalAudit', data.total_audit_logs || 0);
    setTxt('hipaaPhiAccess', data.phi_access_count || 0);
    setTxt('hipaaPhiRecent', data.recent_phi_accesses_24h || 0);
    setTxt('hipaaExports', data.total_exports || 0);

    // Encryption status
    const encStatus = document.getElementById('hipaaEncryptionStatus');
    if (encStatus) {
        encStatus.className = 'monitor-status-dot ' + (data.encryption_at_rest ? 'ready' : 'not-ready');
    }
    setTxt('hipaaEncryptionAtRest', data.encryption_at_rest ? 'Enabled' : 'Disabled');

    const meta = data.compliance_metadata || {};
    const hipaa = meta.hipaa || {};
    setTxt('hipaaPhiPersistence', hipaa.phi_persistence_enabled ? 'Enabled' : 'Disabled');
    setTxt('hipaaPhiLogging', hipaa.phi_logging_enabled ? 'Enabled' : 'Disabled');
    setTxt('hipaaMinNecessary', hipaa.minimum_necessary_mode ? 'Active' : 'Inactive');

    // Retention stats
    const ret = data.retention || {};
    const sessions = ret.sessions || {};
    const audits = ret.audit_logs || {};
    setTxt('hipaaSessionsTotal', sessions.total || 0);
    setTxt('hipaaSessionsExpired', sessions.expired || 0);
    setTxt('hipaaSessionRetention', sessions.retention_days > 0 ? sessions.retention_days : 'Forever');
    setTxt('hipaaAutoPurge', ret.auto_purge_enabled ? 'Enabled' : 'Disabled');
    setTxt('hipaaAuditTotal', audits.total || 0);
    setTxt('hipaaAuditExpired', audits.expired || 0);
    setTxt('hipaaAuditRetention', audits.retention_days > 0 ? audits.retention_days : 'Forever');
    setTxt('hipaaPurgeInterval', ret.purge_interval_hours ? ret.purge_interval_hours + 'h' : '--');
}

function renderExportLogs(logs) {
    const container = document.getElementById('hipaaExportLogs');
    if (!container) return;

    if (!logs || logs.length === 0) {
        container.innerHTML = '<p class="text-muted">No export logs found.</p>';
        return;
    }

    let html = `<div class="hipaa-export-row header">
        <span>User</span><span>Type</span><span>Destination</span><span>Timestamp</span><span>Status</span>
    </div>`;

    for (const log of logs) {
        const ts = log.timestamp ? new Date(log.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '--';
        const dest = log.destination ? (log.destination.length > 15 ? log.destination.substring(0, 15) + '...' : log.destination) : '--';
        html += `<div class="hipaa-export-row">
            <span>${log.username || 'system'}</span>
            <span>${log.export_type || '--'}</span>
            <span title="${log.destination || ''}">${dest}</span>
            <span>${ts}</span>
            <span class="hipaa-export-status ${log.status || 'success'}">${log.status || 'success'}</span>
        </div>`;
    }

    container.innerHTML = html;
}

async function runHipaaPurge() {
    const resultEl = document.getElementById('hipaaPurgeResult');
    const btn = document.getElementById('hipaaPurgeBtn');

    if (!confirm('Run data purge based on retention policies? This will permanently delete expired records.')) {
        return;
    }

    if (btn) btn.disabled = true;
    if (resultEl) resultEl.textContent = 'Running purge...';

    try {
        const resp = await apiFetch('/api/hipaa/retention/purge', { method: 'POST' });
        if (resp.ok) {
            const data = await resp.json();
            const msg = `Purged ${data.sessions_purged} sessions, ${data.audit_logs_purged} audit logs.`;
            if (resultEl) resultEl.textContent = msg;
            // Refresh dashboard after purge
            loadHipaaDashboard();
        } else {
            if (resultEl) resultEl.textContent = 'Purge failed: ' + resp.status;
        }
    } catch (e) {
        if (resultEl) resultEl.textContent = 'Purge error: ' + e.message;
    } finally {
        if (btn) btn.disabled = false;
    }
}

// =====================================================
// AI VOICE ASSISTANT INTEGRATION
// =====================================================

function initConversationMode() {
    const toggleBtn = document.getElementById('convToggleBtn');
    const panel = document.getElementById('conversationPanel');
    const modeSelect = document.getElementById('convModeSelect');
    const endBtn = document.getElementById('convEndBtn');

    if (!toggleBtn || !panel) return;

    // Initialize conversation manager
    if (typeof conversationManager !== 'undefined') {
        conversationManager.init();
    }

    let conversationActive = false;

    toggleBtn.addEventListener('click', () => {
        conversationActive = !conversationActive;

        if (conversationActive) {
            toggleBtn.classList.add('active');
            panel.classList.add('active');
            modeSelect.style.display = 'block';

            // Start conversation
            const mode = modeSelect.value;
            if (typeof conversationManager !== 'undefined') {
                conversationManager.start(mode);
            }
        } else {
            toggleBtn.classList.remove('active');
            panel.classList.remove('active');
            modeSelect.style.display = 'none';

            // Disconnect
            if (typeof conversationManager !== 'undefined') {
                conversationManager.disconnect();
            }
        }
    });

    if (modeSelect) {
        modeSelect.addEventListener('change', () => {
            if (conversationActive && typeof conversationManager !== 'undefined') {
                conversationManager.disconnect();
                conversationManager.start(modeSelect.value);
            }
        });
    }

    if (endBtn) {
        endBtn.addEventListener('click', () => {
            if (typeof conversationManager !== 'undefined') {
                conversationManager.endConversation();
            }
        });
    }
}

// =====================================================
// INITIALIZE

// =====================================================
document.addEventListener('DOMContentLoaded', () => {
    init().catch((error) => {
        console.error('Initialization failed', error);
    });
    initConversationMode();
});
