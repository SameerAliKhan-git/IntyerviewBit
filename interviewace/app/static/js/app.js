/**
 * app.js - InterviewAce Google Meet Clone Engine
 * Manages WebSocket, WebRTC, Visualizers, Transcripts (CC), and Multi-Agent UI.
 */

// -- Google Meet Volume Visualizer --
class VolumeVisualizer {
    constructor(analyserNode, ringsId, equalizerId, tileId) {
        this.analyser = analyserNode;
        this.bufferLength = this.analyser.frequencyBinCount;
        this.dataArray = new Uint8Array(this.bufferLength);
        
        this.tile = document.getElementById(tileId);
        
        const ringsContainer = document.getElementById(ringsId);
        this.rings = ringsContainer ? Array.from(ringsContainer.querySelectorAll('.ring')) : [];
        
        const eqContainer = document.getElementById(equalizerId);
        this.eqBars = eqContainer ? Array.from(eqContainer.querySelectorAll('.bar')) : [];
        if (eqContainer) this.eqContainer = eqContainer;
        
        // Hide mic icon if eq exists
        this.micIcon = this.tile ? this.tile.querySelector('.mic-icon') : null;
        
        this.isAnimating = false;
        this.smoothedVol = 0;
    }

    start() {
        if (!this.isAnimating) {
            this.isAnimating = true;
            this.draw();
        }
    }

    stop() {
        this.isAnimating = false;
        
        this.rings.forEach(r => { r.style.transform = 'scale(1)'; r.style.opacity = '0'; });
        this.eqBars.forEach(b => b.style.height = '4px');
        
        if (this.tile) this.tile.classList.remove('tile-speaking');
        if (this.eqContainer) this.eqContainer.style.display = 'none';
        if (this.micIcon) this.micIcon.style.display = 'inline-block';
    }

    draw() {
        if (!this.isAnimating) return;
        requestAnimationFrame(() => this.draw());

        this.analyser.getByteFrequencyData(this.dataArray);
        
        // Calculate RMS volume
        let sum = 0;
        for (let i = 0; i < this.bufferLength; i++) {
            sum += this.dataArray[i];
        }
        let avg = sum / this.bufferLength;
        let vol = avg / 128.0; // roughly 0.0 to 1.5+
        
        // Smooth changes
        this.smoothedVol = this.smoothedVol * 0.7 + vol * 0.3;
        
        // Threshold for speaking
        const isSpeaking = this.smoothedVol > 0.05;

        // Tile glow
        if (this.tile) {
            if (isSpeaking) this.tile.classList.add('tile-speaking');
            else this.tile.classList.remove('tile-speaking');
        }

        // Toggle mic icon / equalizer
        if (isSpeaking && this.eqContainer) {
            this.eqContainer.style.display = 'flex';
            if (this.micIcon) this.micIcon.style.display = 'none';
        } else {
            if (this.eqContainer) this.eqContainer.style.display = 'none';
            if (this.micIcon) this.micIcon.style.display = 'inline-block';
        }

        // Scale Rings (Avatar halo)
        if (this.rings.length === 3) {
            if (isSpeaking) {
                const s1 = Math.min(1 + this.smoothedVol * 0.3, 1.4);
                const s2 = Math.min(1 + this.smoothedVol * 0.6, 1.8);
                const s3 = Math.min(1 + this.smoothedVol * 1.0, 2.3);
                
                this.rings[0].style.transform = `scale(${s1})`;
                this.rings[1].style.transform = `scale(${s2})`;
                this.rings[2].style.transform = `scale(${s3})`;
                
                this.rings.forEach(r => r.style.opacity = '0.4');
            } else {
                this.rings.forEach(r => {
                    r.style.transform = 'scale(1)';
                    r.style.opacity = '0';
                });
            }
        }

        // Jiggle Equalizer bars
        if (isSpeaking && this.eqBars.length === 3) {
            this.eqBars[0].style.height = `${Math.max(4, Math.min(14, this.smoothedVol * 15 * Math.random() + 4))}px`;
            this.eqBars[1].style.height = `${Math.max(4, Math.min(14, this.smoothedVol * 20 * Math.random() + 6))}px`;
            this.eqBars[2].style.height = `${Math.max(4, Math.min(14, this.smoothedVol * 15 * Math.random() + 4))}px`;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log("🚀 InterviewAce Meet Mode initializing...");

    const userId = 'user_' + Math.random().toString(36).substr(2, 9);
    const sessionId = 'session_' + Math.random().toString(36).substr(2, 11);

    // Hardware state
    const camera = new window.CameraManager();
    let audioRecorder = null;
    let audioPlayer = null;
    let audioContext = null;
    let userVisualizer = null;
    let agentVisualizer = null;

    // Conneciton state
    let ws = null;
    let isInterviewActive = false;
    let dialogueHistory = [];
    let finalScores = {};
    let ccTimeout = null;

    // DOM Elements
    const startBtn = document.getElementById('startBtn');
    const endBtn = document.getElementById('endBtn');
    const micBtn = document.getElementById('micBtn');
    const cameraBtn = document.getElementById('cameraBtn');
    const ccBtn = document.getElementById('ccBtn');
    
    // Status Elements
    const thinkingOverlay = document.getElementById('thinkingOverlay');
    const transcribingBadge = document.getElementById('transcribingBadge');
    const agentMicIcon = document.getElementById('agentMicIcon');
    const userMicIcon = document.getElementById('userMicIcon');
    const clockTime = document.getElementById('clockTime');

    // Captions Elements
    const ccContainer = document.getElementById('ccContainer');
    const ccAvatar = document.getElementById('ccAvatar');
    const ccName = document.getElementById('ccName');
    const ccText = document.getElementById('ccText');
    let ccEnabled = true;

    // Update real clock
    setInterval(() => {
        const d = new Date();
        clockTime.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }, 1000);

    // TOAST NOTIFICATIONS
    const toastContainer = document.getElementById('toastContainer');
    function showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }

    // Attach Toast to all interaction buttons
    document.querySelectorAll('.interaction-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.getAttribute('data-action');
            if (action) showToast(`"${action}" is disabled during a mock interview.`);
        });
    });

    // ==========================================
    // EVENT LISTENERS
    // ==========================================
    
    startBtn.addEventListener('click', async () => {
        if (isInterviewActive) return;
        
        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            if (audioContext.state === 'suspended') await audioContext.resume();

            audioPlayer = new window.AudioPlayer(audioContext);
            audioRecorder = new window.AudioRecorder(audioContext);

            // Start hardware
            const camOk = await camera.start();
            if (camOk) {
                document.getElementById('videoOverlay').style.display = 'none';
                cameraBtn.classList.remove('disabled-state');
                cameraBtn.innerHTML = '<span class="material-icons">videocam</span>';
                camera.startFrameExtraction((b64) => {
                    sendJson({ type: "image", mimeType: "image/jpeg", data: b64 });
                });
            }

            // Visualizers setup (Google Meet Volume Rings)
            agentVisualizer = new VolumeVisualizer(audioPlayer.getAnalyser(), 'agentRings', 'agentEqualizer', 'agentTile');
            userVisualizer = new VolumeVisualizer(audioRecorder.getAnalyser(), 'userRings', 'userEqualizer', 'userTile');
            agentVisualizer.start();
            userVisualizer.start();

            // Connect
            connectWebSocket('Kore');

            startBtn.style.display = 'none';
            endBtn.style.display = 'flex';
        } catch (e) {
            console.error("❌ Init error:", e);
        }
    });

    endBtn.addEventListener('click', () => {
        if (!isInterviewActive) return;
        
        // Clean wrap-up
        sendJson({ type: "text", text: "I'd like to end the interview now. Please finalize the score." });
        thinkingOverlay.style.display = 'block';

        // Wait for final functions, then show Modal
        setTimeout(() => {
            cleanup();
            showFeedbackPanel();
        }, 4000);
    });

    micBtn.addEventListener('click', () => {
        if (!audioRecorder) return;
        const isMuted = !audioRecorder.toggleMute();
        
        if (isMuted) {
            micBtn.classList.add('disabled-state');
            micBtn.innerHTML = '<span class="material-icons">mic_off</span>';
            userMicIcon.textContent = 'mic_off';
            userMicIcon.classList.add('red-icon');
            showToast("Microphone muted");
        } else {
            micBtn.classList.remove('disabled-state');
            micBtn.innerHTML = '<span class="material-icons">mic</span>';
            userMicIcon.textContent = 'mic';
            userMicIcon.classList.remove('red-icon');
            showToast("Microphone turned on");
        }
    });

    cameraBtn.addEventListener('click', () => {
        const isOn = camera.toggle();
        if (isOn) {
            cameraBtn.classList.remove('disabled-state');
            cameraBtn.innerHTML = '<span class="material-icons">videocam</span>';
            document.getElementById('videoOverlay').style.display = 'none';
            showToast("Camera turned on");
        } else {
            cameraBtn.classList.add('disabled-state');
            cameraBtn.innerHTML = '<span class="material-icons">videocam_off</span>';
            document.getElementById('videoOverlay').style.display = 'flex';
            showToast("Camera turned off");
        }
    });

    ccBtn.addEventListener('click', () => {
        ccEnabled = !ccEnabled;
        if (ccEnabled) {
            ccBtn.classList.add('active');
            showToast("Captions turned on");
        } else {
            ccBtn.classList.remove('active');
            ccContainer.style.display = 'none';
            showToast("Captions turned off");
        }
    });

    // ==========================================
    // WEBSOCKET LOGIC
    // ==========================================
    function connectWebSocket(voiceName) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${userId}/${sessionId}?voice=${voiceName}`;
        ws = new WebSocket(wsUrl);

        ws.onopen = async () => {
            isInterviewActive = true;
            thinkingOverlay.style.display = 'block';
            
            // Enable buttons
            ccBtn.disabled = false;
            ccBtn.classList.add('active'); // Default ON

            // Setup mic defaults
            micBtn.classList.remove('disabled-state');
            micBtn.innerHTML = '<span class="material-icons">mic</span>';
            userMicIcon.textContent = 'mic';
            userMicIcon.classList.remove('red-icon');

            // Trigger Agent
            setTimeout(() => {
                sendJson({ type: "text", text: "Hello, I have joined the meet." });
            }, 500);

            try {
                await audioRecorder.start((pcmBytes) => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(pcmBytes);
                    }
                });
            } catch (e) {}
        };

        ws.onmessage = (event) => {
            if (typeof event.data === 'string') {
                try {
                    const adkEvent = JSON.parse(event.data);
                    handleAdkEvent(adkEvent);
                } catch (e) {
                    console.error("Parse error:", e);
                }
            }
        };

        ws.onclose = () => { isInterviewActive = false; };
    }

    // ==========================================
    // EVENT HANDLING & MULTI-AGENT SIM
    // ==========================================
    function handleAdkEvent(evt) {
        // Agent speaking
        if (evt.content && evt.content.parts) {
            thinkingOverlay.style.display = 'none';
            agentMicIcon.textContent = 'mic';
            agentMicIcon.classList.remove('red-icon');

            for (const part of evt.content.parts) {
                if (part.text) dialogueHistory.push(`[Coach Ace]: ${part.text}`);
                if (part.inline_data && part.inline_data.data) {
                    if (audioPlayer) audioPlayer.playBase64(part.inline_data.data);
                }
            }
        }

        // Transcriptions / CC (Elena - Notetaker actions)
        if (evt.server_content) {
            const sc = evt.server_content;
            
            if (sc.input_transcription && sc.input_transcription.trim()) {
                dialogueHistory.push(`[You]: ${sc.input_transcription}`);
                thinkingOverlay.style.display = 'block';
                showCaption('You', 'Y', 'bg-green', sc.input_transcription);
                pulseNotetaker();
            }
            if (sc.output_transcription && sc.output_transcription.trim()) {
                showCaption('Coach Ace', 'C', 'bg-blue', sc.output_transcription);
                pulseNotetaker();
            }
        }

        // Tool execution
        if (evt.actions && evt.actions.function_calls) {
            for (const fc of evt.actions.function_calls) {
                pulseNotetaker(); // Simulate Elena typing out the scores silently
                
                if (fc.name === "save_session_feedback" && fc.args) {
                    finalScores = {
                        confidence: fc.args.confidence_score || finalScores.confidence,
                        clarity: fc.args.clarity_score || finalScores.clarity,
                        body_language: fc.args.body_language_score || finalScores.body_language,
                        content: fc.args.content_score || finalScores.content,
                        strengths: fc.args.strengths || finalScores.strengths,
                        improvements: fc.args.improvements || finalScores.improvements,
                    };
                }
            }
        }

        if (evt.turn_complete || evt.interrupted) {
            agentMicIcon.textContent = 'mic_off';
            agentMicIcon.classList.add('red-icon');
            thinkingOverlay.style.display = 'none';
            if (evt.interrupted && audioPlayer) audioPlayer.stop();
        }
    }

    // ==========================================
    // UI HELPERS
    // ==========================================
    function sendJson(obj) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(obj));
        }
    }

    function pulseNotetaker() {
        transcribingBadge.style.display = 'flex';
        clearTimeout(ccTimeout);
        ccTimeout = setTimeout(() => {
            transcribingBadge.style.display = 'none';
        }, 3000);
    }

    function showCaption(name, initial, colorClass, text) {
        if (!ccEnabled) return;
        ccContainer.style.display = 'flex';
        ccName.textContent = name;
        ccText.textContent = text;
        
        ccAvatar.className = `cc-avatar ${colorClass}`;
        ccAvatar.textContent = initial;

        clearTimeout(ccTimeout);
        ccTimeout = setTimeout(() => {
            ccContainer.style.display = 'none';
        }, 6000);
    }

    function showFeedbackPanel() {
        document.getElementById('feedbackPanel').style.display = 'flex';
        
        const ovr = Math.round(((finalScores.confidence||0) + (finalScores.clarity||0) + (finalScores.body_language||0) + (finalScores.content||0)) / 4) || 0;
        
        document.getElementById('scoreOverall').textContent = `${ovr}`;
        document.getElementById('scoreConfidence').textContent = finalScores.confidence || 0;
        document.getElementById('scoreClarity').textContent = finalScores.clarity || 0;
        document.getElementById('scoreContent').textContent = finalScores.content || 0;
        document.getElementById('scoreBody').textContent = finalScores.body_language || 0;
        
        let html = `<p><strong>Elena's Summary Notes:</strong></p><br>`;
        html += `<p><strong>Key Strengths:</strong><br>${finalScores.strengths || 'No data recorded yet.'}</p><br>`;
        html += `<p><strong>Areas for Improvement:</strong><br>${finalScores.improvements || 'Keep practicing!'}</p>`;
        
        document.getElementById('feedbackContent').innerHTML = html;

        // Enable download button
        const dlBtn = document.getElementById('downloadTranscriptBtn');
        dlBtn.disabled = false;
        dlBtn.onclick = downloadTranscript;
    }

    function downloadTranscript() {
        const textContent = "TECHNICAL MOCK INTERVIEW TRANSCRIPT\nTranscribed by: Elena (AI Notetaker)\n\n" + dialogueHistory.join("\n\n");
        const blob = new Blob([textContent], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Interview_Transcript_${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function cleanup() {
        isInterviewActive = false;
        if (audioRecorder) audioRecorder.stop();
        if (audioPlayer) audioPlayer.stop();
        if (agentVisualizer) agentVisualizer.stop();
        if (userVisualizer) userVisualizer.stop();
        if (camera) camera.stop();
        setTimeout(() => { if (ws) ws.close(); }, 1000);
    }
});
