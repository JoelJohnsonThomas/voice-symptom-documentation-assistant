/**
 * AI Voice Assistant — Conversation Manager
 *
 * Handles WebSocket connection to /ws/conversation, audio recording,
 * TTS playback (with Web Speech API fallback), and chat UI rendering.
 */

class ConversationManager {
    constructor() {
        this.ws = null;
        this.isConnected = false;
        this.isRecording = false;
        this.isSpeaking = false;
        this.sessionId = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.audioQueue = [];
        this.isPlayingAudio = false;
        this.currentState = 'idle';
        this.mode = 'patient'; // 'patient' or 'clinician'

        // DOM elements (set by init)
        this.chatMessages = null;
        this.micBtn = null;
        this.textInput = null;
        this.sendBtn = null;
        this.statusText = null;
        this.statusDot = null;
        this.typingIndicator = null;
        this.entitiesPanel = null;
    }

    /**
     * Initialize the conversation manager and bind to DOM elements.
     */
    init() {
        this.chatMessages = document.getElementById('conv-chat-messages');
        this.micBtn = document.getElementById('conv-mic-btn');
        this.textInput = document.getElementById('conv-text-input');
        this.sendBtn = document.getElementById('conv-send-btn');
        this.statusText = document.getElementById('conv-status-text');
        this.statusDot = document.getElementById('conv-status-dot');
        this.typingIndicator = document.getElementById('conv-typing');
        this.entitiesPanel = document.getElementById('conv-entities');

        if (!this.chatMessages) return; // Conversation UI not in DOM

        // Bind events
        if (this.micBtn) {
            this.micBtn.addEventListener('click', () => this.toggleRecording());
        }
        if (this.sendBtn) {
            this.sendBtn.addEventListener('click', () => this.sendTextInput());
        }
        if (this.textInput) {
            this.textInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendTextInput();
                }
            });
        }
    }

    /**
     * Start a new conversation session.
     */
    start(mode = 'patient') {
        this.mode = mode;
        this.clearChat();
        this.connect();
    }

    /**
     * Connect to the WebSocket conversation endpoint.
     */
    connect() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws/conversation`;

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this.isConnected = true;
            this.setStatus('Connected', 'connected');

            // Send start action
            this.ws.send(JSON.stringify({
                action: 'start',
                mode: this.mode,
                language: 'en',
            }));
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this.handleMessage(msg);
            } catch (e) {
                console.error('Failed to parse conversation message:', e);
            }
        };

        this.ws.onclose = () => {
            this.isConnected = false;
            this.setStatus('Disconnected', 'disconnected');
        };

        this.ws.onerror = (err) => {
            console.error('Conversation WebSocket error:', err);
            this.setStatus('Connection error', 'error');
        };
    }

    /**
     * Handle incoming WebSocket messages.
     */
    handleMessage(msg) {
        switch (msg.type) {
            case 'connected':
                this.setStatus('Starting conversation...', 'connected');
                break;

            case 'assistant_text':
                this.sessionId = msg.session_id || this.sessionId;
                this.hideTyping();
                this.addBubble('assistant', msg.text, {
                    isEmergency: msg.is_emergency,
                    ragGrounded: msg.rag_grounded,
                });
                this.currentState = msg.state;

                if (msg.is_final && msg.documentation) {
                    this.showSummary(msg.documentation);
                }
                break;

            case 'assistant_audio':
                if (msg.audio) {
                    this.queueAudio(msg.audio, msg.format, msg.sample_rate);
                } else if (msg.text) {
                    // No audio from server — use Web Speech API fallback
                    this.speakWithBrowserTTS(msg.text);
                }
                break;

            case 'user_transcript':
                if (msg.is_final) {
                    this.addBubble('user', msg.text);
                    this.showTyping();
                }
                break;

            case 'entities_update':
                this.updateEntities(msg.entities);
                break;

            case 'state_change':
                this.setStatus(this.stateLabel(msg.to_state), 'connected');
                break;

            case 'summary':
                this.showSummary(msg.documentation);
                break;

            case 'error':
                this.addBubble('assistant', `Error: ${msg.message}`, { isEmergency: true });
                break;
        }
    }

    /**
     * Toggle microphone recording.
     */
    async toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            await this.startRecording();
        }
    }

    /**
     * Start recording audio from microphone.
     */
    async startRecording() {
        if (!this.isConnected) {
            this.start(this.mode);
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm;codecs=opus',
            });

            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0 && this.ws && this.ws.readyState === WebSocket.OPEN) {
                    this.ws.send(event.data);
                }
            };

            this.mediaRecorder.onstop = () => {
                stream.getTracks().forEach(t => t.stop());
            };

            this.mediaRecorder.start(250); // Send chunks every 250ms
            this.isRecording = true;
            this.micBtn.classList.add('recording');
            this.setStatus('Listening...', 'listening');
        } catch (err) {
            console.error('Microphone access failed:', err);
            this.addBubble('assistant', 'Microphone access denied. Please type your response below.');
        }
    }

    /**
     * Stop recording and trigger ASR finalization.
     */
    stopRecording() {
        if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
            this.mediaRecorder.stop();
        }
        this.isRecording = false;
        this.micBtn.classList.remove('recording');
        this.setStatus('Processing...', 'connected');

        // Tell server to finalize ASR
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action: 'stop' }));
        }
    }

    /**
     * Send text input as fallback.
     */
    sendTextInput() {
        const text = this.textInput.value.trim();
        if (!text) return;

        if (!this.isConnected) {
            this.start(this.mode);
            return;
        }

        this.addBubble('user', text);
        this.showTyping();
        this.textInput.value = '';

        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({
                action: 'text_input',
                text: text,
            }));
        }
    }

    /**
     * End the conversation.
     */
    endConversation() {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify({ action: 'end' }));
        }
    }

    /**
     * Disconnect and clean up.
     */
    disconnect() {
        if (this.isRecording) this.stopRecording();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.isConnected = false;
        this.sessionId = null;
    }

    // =====================================================
    // Audio Playback
    // =====================================================

    /**
     * Queue audio for sequential playback.
     */
    queueAudio(base64Audio, format, sampleRate) {
        this.audioQueue.push({ base64Audio, format, sampleRate });
        if (!this.isPlayingAudio) {
            this.playNextAudio();
        }
    }

    /**
     * Play next audio in queue.
     */
    async playNextAudio() {
        if (this.audioQueue.length === 0) {
            this.isPlayingAudio = false;
            this.isSpeaking = false;
            this.setStatus('Ready', 'connected');
            return;
        }

        this.isPlayingAudio = true;
        this.isSpeaking = true;
        this.setStatus('Assistant speaking...', 'speaking');

        const { base64Audio } = this.audioQueue.shift();

        try {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }

            const binaryString = atob(base64Audio);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            const audioBuffer = await this.audioContext.decodeAudioData(bytes.buffer);
            const source = this.audioContext.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.audioContext.destination);

            source.onended = () => {
                this.playNextAudio();
            };

            source.start(0);
        } catch (err) {
            console.error('Audio playback failed:', err);
            this.playNextAudio(); // Skip to next
        }
    }

    /**
     * Web Speech API fallback for TTS.
     */
    speakWithBrowserTTS(text) {
        if (!('speechSynthesis' in window)) return;

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 0.9;
        utterance.pitch = 1.0;
        utterance.onstart = () => {
            this.isSpeaking = true;
            this.setStatus('Assistant speaking...', 'speaking');
        };
        utterance.onend = () => {
            this.isSpeaking = false;
            this.setStatus('Ready', 'connected');
        };
        window.speechSynthesis.speak(utterance);
    }

    // =====================================================
    // Chat UI
    // =====================================================

    /**
     * Add a chat bubble to the conversation panel.
     */
    addBubble(role, text, options = {}) {
        if (!this.chatMessages) return;

        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role}`;

        if (options.isEmergency) {
            bubble.classList.add('emergency');
        }

        bubble.textContent = text;

        if (options.ragGrounded) {
            const badge = document.createElement('span');
            badge.className = 'rag-badge';
            badge.textContent = 'Evidence-based';
            bubble.appendChild(document.createElement('br'));
            bubble.appendChild(badge);
        }

        this.chatMessages.appendChild(bubble);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    showTyping() {
        if (this.typingIndicator) {
            this.typingIndicator.classList.add('active');
        }
    }

    hideTyping() {
        if (this.typingIndicator) {
            this.typingIndicator.classList.remove('active');
        }
    }

    clearChat() {
        if (this.chatMessages) {
            this.chatMessages.innerHTML = '';
        }
        if (this.entitiesPanel) {
            this.entitiesPanel.innerHTML = '';
        }
    }

    /**
     * Update extracted entities display.
     */
    updateEntities(entities) {
        if (!this.entitiesPanel) return;

        this.entitiesPanel.innerHTML = '';

        const conditions = entities.conditions || [];
        const medications = entities.medications || [];

        conditions.forEach(c => {
            const tag = document.createElement('span');
            tag.className = 'entity-tag condition';
            tag.textContent = c.text || c.name || c;
            this.entitiesPanel.appendChild(tag);
        });

        medications.forEach(m => {
            const tag = document.createElement('span');
            tag.className = 'entity-tag medication';
            tag.textContent = m.text || m.name || m;
            this.entitiesPanel.appendChild(tag);
        });
    }

    /**
     * Show SOAP summary card.
     */
    showSummary(documentation) {
        if (!this.chatMessages || !documentation) return;

        const card = document.createElement('div');
        card.className = 'chat-bubble assistant';
        card.style.maxWidth = '95%';

        let html = '<strong>Documentation Summary</strong><br>';
        if (documentation.chief_complaint) {
            html += `<br><em>Chief Complaint:</em> ${documentation.chief_complaint}`;
        }
        if (documentation.subjective) {
            html += `<br><em>Subjective:</em> ${documentation.subjective}`;
        }
        if (documentation.objective) {
            html += `<br><em>Objective:</em> ${documentation.objective}`;
        }
        if (documentation.assessment) {
            html += `<br><em>Assessment:</em> ${documentation.assessment}`;
        }
        if (documentation.plan) {
            html += `<br><em>Plan:</em> ${documentation.plan}`;
        }
        if (documentation.red_flags && documentation.red_flags.length > 0) {
            html += `<br><br><span style="color: #ff4757;">RED FLAGS: ${documentation.red_flags.join(', ')}</span>`;
        }

        card.innerHTML = html;
        this.chatMessages.appendChild(card);
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    // =====================================================
    // Status
    // =====================================================

    setStatus(text, state) {
        if (this.statusText) {
            this.statusText.textContent = text;
        }
        if (this.statusDot) {
            this.statusDot.className = 'status-dot';
            if (state === 'speaking') this.statusDot.classList.add('speaking');
            else if (state === 'listening') this.statusDot.classList.add('listening');
        }
    }

    stateLabel(state) {
        const labels = {
            greeting: 'Greeting',
            chief_complaint: 'Listening for chief complaint',
            symptom_details: 'Gathering symptom details',
            follow_up: 'Follow-up questions',
            summary: 'Generating summary',
            emergency_escalation: 'Emergency',
            ended: 'Conversation ended',
        };
        return labels[state] || state;
    }
}

// Global instance
const conversationManager = new ConversationManager();
