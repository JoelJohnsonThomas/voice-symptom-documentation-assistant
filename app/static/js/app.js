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
    batchExportBtn: document.getElementById('batchExportBtn')
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
    sessionHistory: []
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
    setupImageUpload();
    setupSubmit();
    setupActions();
    setupSOAPActions();
    setupSettings();
    loadSessionHistory();
    setupPDFExport();
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
        alert(`File is too large (${(file.size / (1024 * 1024)).toFixed(1)}MB). Max allowed size is 10MB.`);
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
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

function updateSubmitButton() {
    const hasAudio = state.audioBlob !== null;
    const hasText = elements.textInput?.value.trim().length > 0;
    const hasLiveTranscript = state.liveTranscript && state.liveTranscript.trim().length > 0;
    const hasImage = state.uploadedImageFile !== null;

    if (elements.submitBtn) {
        elements.submitBtn.disabled = !(hasAudio || hasText || hasLiveTranscript || hasImage);
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
    const hasImage = state.uploadedImageFile !== null;

    if (!hasAudio && !textContent && !hasLiveTranscript && !hasImage) return;

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

            const imgResponse = await fetch('/api/analyze-image', {
                method: 'POST',
                body: imageFormData
            });

            if (!imgResponse.ok) {
                const errorData = await imgResponse.json();
                throw new Error(`Image analysis failed: ${errorData.detail || 'Unknown error'}`);
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
            // Special handling for legacy audio
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

            // If we also had image findings, we need to run another generation pass
            // since /api/voice-intake doesn't accept image_findings directly yet
            if (imageFindingsData) {
                documentPayload = {
                    transcript: data.transcript,
                    image_findings: imageFindingsData.visual_findings_text
                };
            } else {
                state.currentDocumentation = data;
                displayResults(data);
                return;
            }
        } else if (textContent) {
            documentPayload = { transcript: textContent };
        } else if (hasImage) {
            // Case where ONLY an image is provided
            documentPayload = { transcript: "Patient uploaded an image only." };
        }

        // Add image findings to the document payload if available
        if (imageFindingsData) {
            documentPayload.image_findings = imageFindingsData.visual_findings_text;
        }

        // 3. Generate documentation
        if (Object.keys(documentPayload).length > 0) {
            response = await fetch('/api/document', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(documentPayload)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(`Documentation generation failed: ${errorData.detail || 'Unknown error'}`);
            }

            let data = await response.json();

            // Normalize response format depending on input source
            data.transcript = documentPayload.transcript;
            data.duration_seconds = state.recordingStartTime && hasAudio
                ? (Date.now() - state.recordingStartTime) / 1000
                : 0;

            state.currentDocumentation = data;
            displayResults(data);
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

function loadSessionHistory() {
    try {
        const stored = localStorage.getItem('voxdoc_sessions');
        if (stored) {
            state.sessionHistory = JSON.parse(stored);
            updateRecentDocsUI();
        }
    } catch (e) {
        console.error('Failed to load session history', e);
    }
}

function saveSessionToHistory() {
    if (!state.currentDocumentation) return;

    const doc = state.currentDocumentation.documentation;
    const sessionData = {
        id: Date.now().toString(),
        timestamp: new Date().toISOString(),
        patientName: "Patient " + Math.floor(Math.random() * 1000), // Placeholder
        chiefComplaint: doc.chief_complaint || 'N/A',
        clinicalDetails: elements.symptomDetails?.innerHTML || 'N/A',
        visualFindings: elements.visualFindings ? elements.visualFindings.textContent : '',
        soapS: elements.soapS ? elements.soapS.textContent : doc.soap_note_subjective,
        soapO: elements.soapO ? elements.soapO.textContent : doc.soap_note_objective,
        soapA: elements.soapA ? elements.soapA.textContent : doc.soap_note_assessment,
        soapP: elements.soapP ? elements.soapP.textContent : doc.soap_note_plan
    };

    // Prepend to history, max 15 items
    state.sessionHistory.unshift(sessionData);
    if (state.sessionHistory.length > 15) {
        state.sessionHistory.pop();
    }

    try {
        localStorage.setItem('voxdoc_sessions', JSON.stringify(state.sessionHistory));
        updateRecentDocsUI();
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
        const displayTime = date.toDateString() === new Date().toDateString() ? `Today, ${timeStr}` : `${dateStr}, ${timeStr}`;

        return `
        <div class="recent-doc-item" data-id="${session.id}">
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
        elements.batchExportBtn.addEventListener('click', () => {
            if (state.sessionHistory.length === 0) {
                alert('No sessions found in history to export.');
                return;
            }
            batchExportPDF();
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
        filename: `VoxDoc_Report_${session.id}.pdf`,
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
        filename: `VoxDoc_Batch_Reports_${Date.now()}.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2 },
        jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' }
    };

    html2pdf().set(opt).from(containerItem).save().then(() => {
        document.body.removeChild(containerItem);
    });
}

// =====================================================
// INITIALIZE

// =====================================================
document.addEventListener('DOMContentLoaded', init);
