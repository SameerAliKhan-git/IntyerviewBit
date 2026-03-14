/**
 * app.js — InterviewAce Main Application Logic
 * 
 * Implements the full interview flow:
 * 1. User clicks Start → WebSocket connects → Agent greets via AUDIO
 * 2. Agent asks questions via speech, user answers via speech
 * 3. Agent scores silently (tool calls update dashboard)
 * 4. User clicks End → Agent gives closing → Feedback panel shown
 * 
 * Handles the official ADK event format from event.model_dump_json().
 */

document.addEventListener('DOMContentLoaded', () => {
    console.log("🚀 InterviewAce initializing...");

    const userId = 'user_' + Math.random().toString(36).substr(2, 9);
    const sessionId = 'session_' + Math.random().toString(36).substr(2, 11);

    // ── Controllers ──
    const dashboard = new window.Dashboard();
    const camera = new window.CameraManager();
    let audioRecorder = null;
    let audioPlayer = null;
    let audioContext = null;

    // ── State ──
    let ws = null;
    let isInterviewActive = false;
    let sessionStart = null;
    let timerInterval = null;
    let questionsAsked = 0;
    let allFeedback = [];

    // ── UI Elements ──
    const statusDot = document.getElementById('connectionStatus');
    const statusText = document.getElementById('statusText');
    const transcriptArea = document.getElementById('transcriptArea');
    const coachVisualizer = document.getElementById('coachVisualizer');
    const recordingBadge = document.getElementById('recordingBadge');
    const feedbackPanel = document.getElementById('feedbackPanel');
    const feedbackContent = document.getElementById('feedbackContent');

    const startBtn = document.getElementById('startBtn');
    const micBtn = document.getElementById('micBtn');
    const cameraBtn = document.getElementById('cameraBtn');
    const endBtn = document.getElementById('endBtn');
    const voiceSelect = document.getElementById('voiceSelect');

    // ══════════════════════════════════════════
    // START INTERVIEW
    // ══════════════════════════════════════════
    startBtn.addEventListener('click', async () => {
        if (isInterviewActive) return;
        
        try {
            // Initialize audio context on user gesture (required by browsers)
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            if (audioContext.state === 'suspended') await audioContext.resume();

            audioPlayer = new window.AudioPlayer(audioContext);
            audioRecorder = new window.AudioRecorder(audioContext);

            // Start camera
            const camOk = await camera.start();
            if (camOk) {
                document.getElementById('videoOverlay').style.display = 'none';
                camera.startFrameExtraction((b64) => {
                    sendJson({ type: "image", mimeType: "image/jpeg", data: b64 });
                });
            }

            // Connect WebSocket with selected voice
            connectWebSocket(voiceSelect.value);

            // Update UI
            startBtn.disabled = true;
            startBtn.innerHTML = '<span>Connecting...</span>';
            voiceSelect.disabled = true;
        } catch (e) {
            console.error("❌ Failed to start:", e);
            appendTranscript("Failed to initialize. Please allow mic/camera access.", "system");
        }
    });

    // ══════════════════════════════════════════
    // END INTERVIEW
    // ══════════════════════════════════════════
    endBtn.addEventListener('click', () => {
        if (!isInterviewActive) return;
        // Tell the agent to end and generate report
        sendJson({ type: "text", text: "I'd like to end the interview now. Please give me my final assessment." });
        appendTranscript("Ending interview...", "system");
        
        // Wait a moment for the agent to respond, then show feedback
        setTimeout(() => {
            showFeedbackPanel();
            cleanup();
        }, 8000);
    });

    // ══════════════════════════════════════════
    // MIC TOGGLE
    // ══════════════════════════════════════════
    micBtn.addEventListener('click', () => {
        if (!audioRecorder) return;
        const isActive = audioRecorder.toggleMute();
        micBtn.classList.toggle('active', isActive);
        micBtn.innerHTML = isActive
            ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>'
            : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="1" y1="1" x2="23" y2="23"></line><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"></path><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>';
    });

    // ══════════════════════════════════════════
    // CAMERA TOGGLE
    // ══════════════════════════════════════════
    cameraBtn.addEventListener('click', () => {
        const isOn = camera.toggle();
        cameraBtn.classList.toggle('active', isOn);
        document.getElementById('videoOverlay').style.display = isOn ? 'none' : 'flex';
    });

    // ══════════════════════════════════════════
    // WEBSOCKET CONNECTION
    // ══════════════════════════════════════════
    function connectWebSocket(voiceName) {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${userId}/${sessionId}?voice=${voiceName}`;
        
        statusText.textContent = "Connecting...";
        ws = new WebSocket(wsUrl);

        ws.onopen = async () => {
            console.log("✅ WebSocket connected");
            statusText.textContent = "Interview Active";
            statusDot.className = "status-dot connected";
            isInterviewActive = true;

            // Update UI
            startBtn.style.display = 'none';
            micBtn.disabled = false;
            micBtn.classList.add('active');
            cameraBtn.disabled = false;
            cameraBtn.classList.add('active');
            endBtn.disabled = false;
            recordingBadge.style.display = 'inline-flex';

            // Start timer
            sessionStart = Date.now();
            timerInterval = setInterval(updateTimer, 1000);

            // Clear transcript
            transcriptArea.innerHTML = '';

            // 🚀 TRIGGER THE AGENT TO SPEAK FIRST 🚀
            setTimeout(() => {
                sendJson({ 
                    type: "text", 
                    text: "Hello, I am ready to start my mock interview." 
                });
            }, 500);

            // Start microphone — send raw binary PCM
            try {
                await audioRecorder.start((pcmBytes) => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(pcmBytes);
                    }
                });
                console.log("🎤 Microphone streaming started");
            } catch (e) {
                console.error("❌ Mic failed:", e);
            }
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

        ws.onclose = () => {
            console.log("🔌 WebSocket closed");
            if (isInterviewActive) {
                statusText.textContent = "Disconnected";
                statusDot.className = "status-dot disconnected";
            }
        };

        ws.onerror = (e) => console.error("WS error:", e);
    }

    // ══════════════════════════════════════════
    // HANDLE ADK EVENTS (official format)
    // ══════════════════════════════════════════
    function handleAdkEvent(evt) {
        // ── Agent content (text or audio parts) ──
        if (evt.content && evt.content.parts) {
            for (const part of evt.content.parts) {
                // Text response (half-cascade mode or transcription)
                if (part.text) {
                    appendTranscript(part.text, 'coach');
                }
                // Audio response (native audio mode)
                if (part.inline_data && part.inline_data.data) {
                    if (audioPlayer) {
                        audioPlayer.playBase64(part.inline_data.data);
                        coachVisualizer.classList.add('speaking');
                    }
                }
            }
        }

        // ── Transcriptions (native audio model) ──
        if (evt.server_content) {
            const sc = evt.server_content;
            if (sc.input_transcription && sc.input_transcription.trim()) {
                appendTranscript(sc.input_transcription, 'user');
            }
            if (sc.output_transcription && sc.output_transcription.trim()) {
                appendTranscript(sc.output_transcription, 'coach');
            }
        }

        // ── Tool calls (score updates from save_session_feedback) ──
        if (evt.actions && evt.actions.function_calls) {
            for (const fc of evt.actions.function_calls) {
                console.log("🔧 Tool:", fc.name, fc.args);
                if (fc.name === "save_session_feedback" && fc.args) {
                    questionsAsked = fc.args.question_number || questionsAsked + 1;
                    document.getElementById('statQuestions').textContent = questionsAsked;

                    // Update live dashboard scores
                    dashboard.updateScores({
                        confidence: fc.args.confidence_score || 0,
                        clarity: fc.args.clarity_score || 0,
                        body_language: fc.args.body_language_score || 0,
                        content: fc.args.content_score || 0,
                    });

                    // Store feedback for end panel
                    allFeedback.push({
                        q: questionsAsked,
                        strengths: fc.args.strengths || "",
                        improvements: fc.args.improvements || "",
                        summary: fc.args.feedback_summary || "",
                    });
                }

                if (fc.name === "get_interview_question") {
                    questionsAsked++;
                    document.getElementById('statQuestions').textContent = questionsAsked;
                }
            }
        }

        // ── Turn complete ──
        if (evt.turn_complete) {
            coachVisualizer.classList.remove('speaking');
        }

        // ── Interrupted (barge-in: agent stopped because user started talking) ──
        if (evt.interrupted) {
            coachVisualizer.classList.remove('speaking');
            if (audioPlayer) audioPlayer.stop();
        }
    }

    // ══════════════════════════════════════════
    // HELPERS
    // ══════════════════════════════════════════
    function sendJson(obj) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(obj));
        }
    }

    function appendTranscript(text, role) {
        if (!text || !text.trim()) return;
        const el = document.createElement('div');
        el.className = `msg ${role}`;
        if (role === 'user') el.innerHTML = `<strong>You:</strong> ${text}`;
        else if (role === 'coach') el.innerHTML = `<strong>Coach Ace:</strong> ${text}`;
        else el.innerHTML = `<em>${text}</em>`;
        transcriptArea.appendChild(el);
        transcriptArea.scrollTop = transcriptArea.scrollHeight;
    }

    function updateTimer() {
        if (!sessionStart) return;
        const elapsed = Math.floor((Date.now() - sessionStart) / 1000);
        const m = String(Math.floor(elapsed / 60)).padStart(2, '0');
        const s = String(elapsed % 60).padStart(2, '0');
        document.getElementById('statDuration').textContent = `${m}:${s}`;
    }

    function showFeedbackPanel() {
        feedbackPanel.style.display = 'block';
        let html = '';
        if (allFeedback.length === 0) {
            html = '<p>No detailed feedback available yet.</p>';
        } else {
            for (const fb of allFeedback) {
                html += `<div class="feedback-item">
                    <h4>Question ${fb.q}</h4>
                    <p><strong>Strengths:</strong> ${fb.strengths || 'N/A'}</p>
                    <p><strong>To Improve:</strong> ${fb.improvements || 'N/A'}</p>
                    ${fb.summary ? `<p>${fb.summary}</p>` : ''}
                </div>`;
            }
        }
        feedbackContent.innerHTML = html;
    }

    function cleanup() {
        isInterviewActive = false;
        if (timerInterval) clearInterval(timerInterval);
        recordingBadge.style.display = 'none';
        statusText.textContent = "Interview Ended";
        statusDot.className = "status-dot disconnected";
        if (audioRecorder) audioRecorder.stop();
        if (camera) camera.stop();
        micBtn.disabled = true;
        cameraBtn.disabled = true;
        endBtn.disabled = true;
        // Don't close WS immediately — let agent finish response
        setTimeout(() => { if (ws) ws.close(); }, 2000);
    }
});
