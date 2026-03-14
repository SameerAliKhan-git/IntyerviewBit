/**
 * app.js
 * Main application orchestration logic.
 * Handles WebSocket connection to the FastAPI backend, coordinates
 * the camera and audio systems, and updates the UI via Dashboard.
 */

// Generate a random user and session ID for this demo
const userId = 'user_' + Math.random().toString(36).substr(2, 9);
const sessionId = 'session_' + Math.random().toString(36).substr(2, 9);

document.addEventListener('DOMContentLoaded', async () => {
    console.log("🚀 InterviewAce initializing...");

    // ── Controllers ──
    const dashboard = new window.Dashboard();
    const camera = new window.CameraManager();
    
    // Audio controllers (from ADK samples)
    let audioRecorder = null;
    let audioPlayer = null;
    let audioContext = null;

    // ── UI Elements ──
    const statusDot = document.getElementById('connectionStatus');
    const statusText = document.getElementById('statusText');
    const transcriptArea = document.getElementById('transcriptArea');
    const coachVisualizer = document.getElementById('coachVisualizer');
    
    // Buttons
    const micBtn = document.getElementById('micBtn');
    const cameraBtn = document.getElementById('cameraBtn');
    const endBtn = document.getElementById('endBtn');

    // ── WebSocket ──
    let ws = null;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/${userId}/${sessionId}`;

    /**
     * Initializes the entire application flow
     */
    async function initApp() {
        try {
            // 1. Initialize Audio Context (must be done after user interaction in some browsers, 
            // but we try here first)
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            
            // 2. Initialize ADK Audio Player and Recorder
            if (window.AudioPlayer) audioPlayer = new window.AudioPlayer(audioContext);
            if (window.AudioRecorder) audioRecorder = new window.AudioRecorder(audioContext);
            
            // 3. Start Camera (Video only)
            const camSuccess = await camera.start();
            if (camSuccess) {
                // Setup frame extraction to send to WebSocket
                camera.startFrameExtraction((base64Data) => {
                    sendWsMessage({
                        type: "image",
                        mimeType: "image/jpeg",
                        data: base64Data
                    });
                });
            }

            // 4. Connect WebSocket
            connectWebSocket();

        } catch (error) {
            console.error("❌ Initialization failed:", error);
            statusText.textContent = "Initialization Failed";
            statusDot.className = "status-dot disconnected";
        }
    }

    /**
     * Establish WebSocket connection
     */
    function connectWebSocket() {
        statusText.textContent = "Connecting...";
        
        ws = new WebSocket(wsUrl);

        ws.onopen = async () => {
            console.log("✅ WebSocket connected");
            statusText.textContent = "Connected";
            statusDot.className = "status-dot connected";
            
            // Send initial setup/config if needed
            sendWsMessage({
                type: "audio_config",
                config: { sample_rate: 16000 }
            });

            // Start Audio Recording (after WS is open so we can send data)
            if (audioRecorder) {
                try {
                    await audioRecorder.start((pcmData) => {
                        // Send binary PCM chunk over WebSocket
                        if (ws.readyState === WebSocket.OPEN) {
                            ws.send(pcmData);
                        }
                    });
                    console.log("🎤 Audio recording started");
                } catch (e) {
                    console.error("❌ Failed to start audio recorder:", e);
                }
            }
        };

        ws.onmessage = async (event) => {
            try {
                // Determine format
                if (typeof event.data === 'string') {
                    // JSON Message
                    const msg = JSON.parse(event.data);
                    handleJsonMessage(msg);
                } else if (event.data instanceof Blob) {
                    // Binary Message (unlikely in ADK setup, but possible)
                    console.log("Received Binary WS message");
                }
            } catch (error) {
                console.error("❌ Error parsing WS message:", error);
            }
        };

        ws.onclose = () => {
            console.log("🔌 WebSocket disconnected");
            statusText.textContent = "Disconnected";
            statusDot.className = "status-dot disconnected";
            cleanup();
        };

        ws.onerror = (error) => {
            console.error("❌ WebSocket error:", error);
        };
    }

    /**
     * Handle incoming JSON messages from the backend
     */
    function handleJsonMessage(msg) {
        switch (msg.type) {
            case 'audio':
                // Base64 audio chunk from agent
                if (msg.data && audioPlayer) {
                    audioPlayer.playBase64(msg.data);
                    coachVisualizer.classList.add('active');
                }
                break;
                
            case 'text':
                // Text chunk from agent
                appendTranscript(msg.content, 'coach');
                break;
                
            case 'input_transcription':
                // Text transcript of what the USER said
                appendTranscript(msg.content, 'user');
                break;
                
            case 'output_transcription':
                 // Text transcript of what the AGENT said (alternative to 'text')
                 // Often useful if using native audio models that don't emit 'text' parts
                 appendTranscript(msg.content, 'coach');
                 break;
                 
            case 'score_update':
                // Live dashboard update from tool calls
                if (msg.data) dashboard.updateScores(msg.data);
                break;
                
            case 'turn_complete':
                coachVisualizer.classList.remove('active');
                break;
                
            default:
                console.log("Unknown message type:", msg.type);
        }
    }

    /**
     * Send JSON message to backend
     */
    function sendWsMessage(payload) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(payload));
        }
    }

    /**
     * Helper to append messages to the chat transcript area
     */
    function appendTranscript(text, role) {
        if (!text.trim()) return;
        
        let lastMsg = transcriptArea.lastElementChild;
        // If the last message was from the same role, append to it (unless it's been a while)
        if (lastMsg && lastMsg.classList.contains(role)) {
            // Check if it's the exact same text (sometimes happens with partial transcripts)
            if (!lastMsg.textContent.includes(text)) {
                lastMsg.textContent += ' ' + text;
            }
        } else {
            const el = document.createElement('div');
            el.className = `msg ${role}`;
            el.textContent = text;
            transcriptArea.appendChild(el);
        }
        
        // Auto scroll
        transcriptArea.scrollTop = transcriptArea.scrollHeight;
    }

    /**
     * Full application cleanup
     */
    function cleanup() {
        if (camera) camera.stop();
        if (audioRecorder) audioRecorder.stop();
        if (audioPlayer) audioPlayer.stop();
        if (ws) ws.close();
    }

    // ── Event Listeners ──

    micBtn.addEventListener('click', () => {
        if (!audioRecorder) return;
        const isEnabled = audioRecorder.toggleMute();
        micBtn.classList.toggle('active', isEnabled);
        micBtn.innerHTML = isEnabled 
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>'
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"></line><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"></path><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>';
    });

    cameraBtn.addEventListener('click', () => {
        if (!camera) return;
        const isEnabled = camera.toggle();
        cameraBtn.classList.toggle('active', isEnabled);
        
        // Show/hide indicator based on camera state
        if (isEnabled && camera.onFrameCaptured) {
            camera.startFrameExtraction(camera.onFrameCaptured);
        } else {
            camera.stopFrameExtraction();
        }
    });

    endBtn.addEventListener('click', () => {
        if (confirm("Are you sure you want to end this interview session?")) {
            cleanup();
            statusText.textContent = "Session Ended";
            statusDot.className = "status-dot disconnected";
            
            // Add final system message
            const finalMsg = document.createElement('div');
            finalMsg.className = 'system-msg';
            finalMsg.textContent = 'Session ended. Review your scores on the dashboard.';
            transcriptArea.appendChild(finalMsg);
            
            // Disable buttons
            micBtn.disabled = true;
            cameraBtn.disabled = true;
            endBtn.disabled = true;
        }
    });

    // ── Start Everything ──
    initApp();
});
