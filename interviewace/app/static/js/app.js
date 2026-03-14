/**
 * app.js - InterviewAce Google Meet Clone Engine (3-Tier Edition)
 * All speech and vision only - no text generation fallback.
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
        this.eqContainer = eqContainer;
        this.micIcon = this.tile ? this.tile.querySelector('.mic-icon') : null;
        this.isAnimating = false;
        this.smoothedVol = 0;
    }
    start() { if (!this.isAnimating) { this.isAnimating = true; this.draw(); } }
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
        let sum = 0;
        for (let i = 0; i < this.bufferLength; i++) sum += this.dataArray[i];
        const vol = (sum / this.bufferLength) / 128.0;
        this.smoothedVol = this.smoothedVol * 0.7 + vol * 0.3;
        const isSpeaking = this.smoothedVol > 0.05;

        if (this.tile) {
            if (isSpeaking) this.tile.classList.add('tile-speaking');
            else this.tile.classList.remove('tile-speaking');
        }
        if (isSpeaking && this.eqContainer) {
            this.eqContainer.style.display = 'flex';
            if (this.micIcon) this.micIcon.style.display = 'none';
        } else {
            if (this.eqContainer) this.eqContainer.style.display = 'none';
            if (this.micIcon) this.micIcon.style.display = 'inline-block';
        }
        if (this.rings.length === 3) {
            if (isSpeaking) {
                this.rings[0].style.transform = `scale(${Math.min(1 + this.smoothedVol * 0.3, 1.4)})`;
                this.rings[1].style.transform = `scale(${Math.min(1 + this.smoothedVol * 0.6, 1.8)})`;
                this.rings[2].style.transform = `scale(${Math.min(1 + this.smoothedVol * 1.0, 2.3)})`;
                this.rings.forEach(r => r.style.opacity = '0.4');
            } else {
                this.rings.forEach(r => { r.style.transform = 'scale(1)'; r.style.opacity = '0'; });
            }
        }
        if (isSpeaking && this.eqBars.length >= 3) {
            this.eqBars[0].style.height = `${Math.max(4, Math.min(14, this.smoothedVol * 15 * Math.random() + 4))}px`;
            this.eqBars[1].style.height = `${Math.max(4, Math.min(14, this.smoothedVol * 20 * Math.random() + 6))}px`;
            this.eqBars[2].style.height = `${Math.max(4, Math.min(14, this.smoothedVol * 15 * Math.random() + 4))}px`;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    console.log("InterviewAce - 3-Tier Live Agent loading...");

    // State
    const userId = 'user_' + Math.random().toString(36).substr(2, 9);
    const sessionId = 'session_' + Math.random().toString(36).substr(2, 11);
    let ws = null;
    let isActive = false;
    let dialogueHistory = [];
    let finalScores = {};
    let totalFillers = 0;
    let ccTimeout = null;
    let ccEnabled = true;
    let sidebarOpen = true;

    // Hardware
    const camera = new window.CameraManager();
    let audioRecorder = null, audioPlayer = null, audioContext = null;
    let userVis = null, agentVis = null;

    // DOM refs
    const setupPanel = document.getElementById('setupPanel');
    const meetingMain = document.getElementById('meetingMain');
    const bottomBar = document.getElementById('bottomBar');
    const setupJoinBtn = document.getElementById('setupJoinBtn');
    const endBtn = document.getElementById('endBtn');
    const micBtn = document.getElementById('micBtn');
    const cameraBtn = document.getElementById('cameraBtn');
    const ccBtn = document.getElementById('ccBtn');
    const thinkingOverlay = document.getElementById('thinkingOverlay');
    const transcribingBadge = document.getElementById('transcribingBadge');
    const agentMicIcon = document.getElementById('agentMicIcon');
    const userMicIcon = document.getElementById('userMicIcon');
    const clockTime = document.getElementById('clockTime');
    const ccContainer = document.getElementById('ccContainer');
    const ccAvatar = document.getElementById('ccAvatar');
    const ccName = document.getElementById('ccName');
    const ccText = document.getElementById('ccText');
    const sidebar = document.getElementById('analyticsSidebar');
    const companyBadge = document.getElementById('companyBadge');
    const meetingCode = document.getElementById('meetingCode');

    // Session config from setup
    let selectedRole = 'general';
    let selectedCompany = 'general';
    let selectedDifficulty = 'medium';
    let selectedVoice = 'Kore';

    // Clock
    setInterval(() => {
        const d = new Date();
        clockTime.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }, 1000);

    // Toast
    const toastContainer = document.getElementById('toastContainer');
    function showToast(msg, duration = 3000) {
        const t = document.createElement('div');
        t.className = 'toast'; t.textContent = msg;
        toastContainer.appendChild(t);
        setTimeout(() => t.remove(), duration);
    }

    // Toast interaction buttons
    document.querySelectorAll('.interaction-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const action = btn.getAttribute('data-action');
            if (action) showToast(`"${action}" is unavailable during a mock interview.`);
        });
    });

    // ==========================================
    // SETUP & JOIN
    // ==========================================
    setupJoinBtn.addEventListener('click', async () => {
        selectedRole = document.getElementById('roleSelect').value;
        selectedCompany = document.getElementById('companySelect').value;
        selectedDifficulty = document.getElementById('difficultySelect').value;
        selectedVoice = document.getElementById('voiceSelect').value;

        try {
            audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            if (audioContext.state === 'suspended') await audioContext.resume();

            audioPlayer = new window.AudioPlayer(audioContext);
            audioRecorder = new window.AudioRecorder(audioContext);

            // Camera
            const camOk = await camera.start();
            if (camOk) {
                document.getElementById('videoOverlay').style.display = 'none';
                cameraBtn.classList.remove('disabled-state');
                cameraBtn.innerHTML = '<span class="material-icons">videocam</span>';
                camera.startFrameExtraction((b64) => {
                    if (ws && ws.readyState === WebSocket.OPEN)
                        sendJson({ type: "image", mimeType: "image/jpeg", data: b64 });
                });
            }

            // Visualizers
            agentVis = new VolumeVisualizer(audioPlayer.getAnalyser(), 'agentRings', 'agentEqualizer', 'agentTile');
            userVis = new VolumeVisualizer(audioRecorder.getAnalyser(), 'userRings', 'userEqualizer', 'userTile');
            agentVis.start(); userVis.start();

            // Show meeting UI
            setupPanel.style.display = 'none';
            meetingMain.style.display = 'flex';
            bottomBar.style.display = 'flex';

            // Set company badge
            companyBadge.textContent = selectedCompany === 'general' ? 'General' : selectedCompany.charAt(0).toUpperCase() + selectedCompany.slice(1);
            meetingCode.textContent = `${selectedCompany}-${selectedDifficulty}-interview`;

            // Connect WebSocket
            connectWebSocket();

        } catch (e) {
            console.error("Init error:", e);
            showToast("Initialization error: " + e.message);
        }
    });

    endBtn.addEventListener('click', () => {
        if (!isActive) return;
        sendJson({ type: "text", text: "I'd like to end the interview now. Please finalize and generate the session report." });
        thinkingOverlay.style.display = 'block';
        setTimeout(() => { cleanup(); showFeedbackPanel(); }, 4500);
    });

    micBtn.addEventListener('click', () => {
        if (!audioRecorder) return;
        const wasUnmuted = audioRecorder.toggleMute();
        if (!wasUnmuted) {
            micBtn.classList.add('disabled-state');
            micBtn.innerHTML = '<span class="material-icons">mic_off</span>';
            userMicIcon.textContent = 'mic_off';
            showToast("Microphone muted");
        } else {
            micBtn.classList.remove('disabled-state');
            micBtn.innerHTML = '<span class="material-icons">mic</span>';
            userMicIcon.textContent = 'mic';
            showToast("Microphone on");
        }
    });

    cameraBtn.addEventListener('click', () => {
        const on = camera.toggle();
        if (on) {
            cameraBtn.classList.remove('disabled-state');
            cameraBtn.innerHTML = '<span class="material-icons">videocam</span>';
            document.getElementById('videoOverlay').style.display = 'none';
            showToast("Camera on");
        } else {
            cameraBtn.classList.add('disabled-state');
            cameraBtn.innerHTML = '<span class="material-icons">videocam_off</span>';
            document.getElementById('videoOverlay').style.display = 'flex';
            showToast("Camera off");
        }
    });

    ccBtn.addEventListener('click', () => {
        ccEnabled = !ccEnabled;
        ccBtn.classList.toggle('active', ccEnabled);
        if (!ccEnabled) ccContainer.style.display = 'none';
        showToast(ccEnabled ? "Captions on" : "Captions off");
    });

    // ==========================================
    // WEBSOCKET
    // ==========================================
    function connectWebSocket() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/ws/${userId}/${sessionId}?voice=${selectedVoice}`;
        ws = new WebSocket(wsUrl);

        ws.onopen = async () => {
            isActive = true;
            thinkingOverlay.style.display = 'block';
            ccBtn.disabled = false;
            ccBtn.classList.add('active');
            micBtn.classList.remove('disabled-state');
            micBtn.innerHTML = '<span class="material-icons">mic</span>';
            userMicIcon.textContent = 'mic';

            // Send greeting trigger — minimal delay for instant agent response
            setTimeout(() => {
                sendJson({ type: "text", text: "Hello, I have joined the meet." });
            }, 200);

            // Start streaming mic audio
            try {
                await audioRecorder.start((pcmBuf) => {
                    if (ws && ws.readyState === WebSocket.OPEN) ws.send(pcmBuf);
                });
            } catch (e) { console.error("Mic error:", e); }
        };

        ws.onmessage = (event) => {
            if (typeof event.data === 'string') {
                try { handleAdkEvent(JSON.parse(event.data)); } catch(e) {}
            }
        };

        ws.onclose = () => { isActive = false; };
        ws.onerror = (e) => console.error("WS error:", e);
    }

    // ==========================================
    // ADK EVENT HANDLER
    // ==========================================
    function handleAdkEvent(evt) {
        // Find tools and audio inside parts
        if (evt.content && evt.content.parts) {
            thinkingOverlay.style.display = 'none';
            agentMicIcon.textContent = 'mic';
            agentMicIcon.classList.remove('red-icon');

            for (const part of evt.content.parts) {
                // Spoken text fragment
                if (part.text) dialogueHistory.push(`[Coach Ace]: ${part.text}`);
                
                // Audio data
                const inlineData = part.inlineData || part.inline_data;
                if (inlineData && inlineData.data) {
                    if (audioPlayer) audioPlayer.playBase64(inlineData.data);
                }

                // Tool Call Request (Agent wants to use a tool)
                let fc = part.functionCall || part.function_call;
                if (fc) processFunctionCall(fc);

                // Tool Call Response (Runner finished executing the tool locally)
                let fr = part.functionResponse || part.function_response;
                if (fr) {
                    // Normalize the response object format if ADK nests it in {result: string}
                    if (fr.response && fr.response.result && typeof fr.response.result === 'string') {
                        fr.response = JSON.parse(fr.response.result);
                    }
                    processToolResult(fr);
                }
            }
        }

        // Transcriptions (CC + History)
        const inTrans = evt.inputTranscription || evt.input_transcription;
        if (inTrans && inTrans.text && inTrans.text.trim()) {
            const userText = inTrans.text.trim();
            dialogueHistory.push(`[You]: ${userText}`);
            thinkingOverlay.style.display = 'block';
            showCC('You', 'Y', 'bg-green', userText);
            pulseElena();
        }

        const outTrans = evt.outputTranscription || evt.output_transcription;
        if (outTrans && outTrans.text && outTrans.text.trim()) {
            showCC('Coach Ace', 'C', 'bg-blue', outTrans.text.trim());
            pulseElena();
        }

        // Turn completion tracking
        if (evt.turnComplete || evt.turn_complete || evt.interrupted) {
            agentMicIcon.textContent = 'mic_off';
            agentMicIcon.classList.add('red-icon');
            thinkingOverlay.style.display = 'none';
            if (evt.interrupted && audioPlayer) audioPlayer.stop();
        }
    }

    function processFunctionCall(fc) {
        pulseElena();
        console.log("Tool call:", fc.name, fc.args);
    }

    function processToolResult(fr) {
        if (!fr || !fr.response) return;
        const data = typeof fr.response === 'string' ? JSON.parse(fr.response) : fr.response;
        const name = fr.name;

        if (name === 'save_session_feedback') {
            updateMetric('mConfidence', 'bConfidence', data.confidence);
            updateMetric('mClarity', 'bClarity', data.clarity);
            updateMetric('mBody', 'bBody', data.body_language);
            updateMetric('mStar', 'bStar', data.star_score);
            finalScores = { ...finalScores, ...data };
        }

        if (name === 'detect_filler_words') {
            totalFillers += (data.total_filler_words || 0);
            document.getElementById('fillerCount').textContent = totalFillers;
            const words = data.detected_fillers ? Object.keys(data.detected_fillers).join(', ') : '—';
            document.getElementById('fillerWords').textContent = words || '—';
            document.getElementById('fillerTip').textContent = data.coaching_tip || '';
        }

        if (name === 'analyze_body_language') {
            updateBodyIndicator('dotEye', 'lblEye', data.eye_contact);
            updateBodyIndicator('dotPosture', 'lblPosture', data.posture);
            updateBodyIndicator('dotExpression', 'lblExpression', data.expression);
        }

        if (name === 'evaluate_star_method') {
            const comps = data.components_present || {};
            setStarBadge('sSituation', comps.situation);
            setStarBadge('sTask', comps.task);
            setStarBadge('sAction', comps.action);
            setStarBadge('sResult', comps.result);
        }

        if (name === 'generate_session_report') {
            finalScores = { ...finalScores, ...data };
        }
    }

    // ==========================================
    // UI HELPERS
    // ==========================================
    function sendJson(obj) {
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
    }

    function pulseElena() {
        transcribingBadge.style.display = 'flex';
        clearTimeout(ccTimeout);
        ccTimeout = setTimeout(() => transcribingBadge.style.display = 'none', 3000);
    }

    function showCC(name, initial, colorClass, text) {
        if (!ccEnabled) return;
        ccContainer.style.display = 'flex';
        ccName.textContent = name;
        ccText.textContent = text;
        ccAvatar.className = `cc-avatar ${colorClass}`;
        ccAvatar.textContent = initial;
        clearTimeout(ccTimeout);
        ccTimeout = setTimeout(() => ccContainer.style.display = 'none', 6000);
    }

    function updateMetric(valId, barId, value) {
        if (value === undefined || value === null) return;
        document.getElementById(valId).textContent = value;
        const bar = document.getElementById(barId);
        if (bar) bar.style.width = `${value}%`;
    }

    function updateBodyIndicator(dotId, lblId, rating) {
        if (!rating) return;
        const dot = document.getElementById(dotId);
        const lbl = document.getElementById(lblId);
        lbl.textContent = rating;
        dot.className = 'bi-dot ' + (['excellent', 'good', 'confident', 'natural', 'engaged'].includes(rating) ? 'good' : 'bad');
    }

    function setStarBadge(id, isPresent) {
        const el = document.getElementById(id);
        if (!el) return;
        const badge = el.querySelector('.si-badge');
        if (badge) {
            badge.className = `si-badge ${isPresent ? 'on' : 'off'}`;
        }
    }

    function showFeedbackPanel() {
        // Reveal the analytics sidebar now that the interview is done
        sidebarOpen = true;
        sidebar.classList.remove('hidden');

        const panel = document.getElementById('feedbackPanel');
        panel.style.display = 'flex';

        const scores = [
            finalScores.confidence || 0,
            finalScores.clarity || 0,
            finalScores.body_language || 0,
            finalScores.content || 0,
            finalScores.star_score || 0,
        ];
        const ovr = finalScores.average_score || (scores.length ? Math.round(scores.reduce((a,b)=>a+b,0)/scores.length) : 0);

        document.getElementById('scoreOverall').textContent = ovr;
        document.getElementById('scoreConfidence').textContent = finalScores.confidence || 0;
        document.getElementById('scoreClarity').textContent = finalScores.clarity || 0;
        document.getElementById('scoreContent').textContent = finalScores.content || 0;
        document.getElementById('scoreStar').textContent = finalScores.star_score || 0;
        document.getElementById('scoreBody').textContent = finalScores.body_language || 0;

        const tier = finalScores.performance_tier || (
            ovr >= 85 ? 'Excellent - Interview Ready' :
            ovr >= 70 ? 'Good - Minor Refinements Needed' :
            ovr >= 55 ? 'Developing - Focused Practice Recommended' :
            'Building Foundation - Keep Practicing'
        );
        document.getElementById('tierBadge').innerHTML = `<span class="tier-pill">${tier}</span>`;

        let html = '';
        if (finalScores.strengths) html += `<p><strong>Strengths:</strong> ${finalScores.strengths}</p><br>`;
        if (finalScores.improvements) html += `<p><strong>Growth Areas:</strong> ${finalScores.improvements}</p><br>`;
        if (totalFillers > 0) html += `<p><strong>Filler Words:</strong> ${totalFillers} total detected. ${totalFillers > 10 ? 'Practice pausing instead of filling.' : 'Good control overall.'}</p><br>`;
        if (finalScores.recommendations) {
            html += `<p><strong>Recommendations:</strong></p><ul style="margin-top:8px;padding-left:20px;">`;
            for (const r of finalScores.recommendations) html += `<li>${r}</li>`;
            html += `</ul>`;
        }
        document.getElementById('feedbackContent').innerHTML = html || '<p>Your interview data is ready. Download the transcript for a full breakdown.</p>';

        const dlBtn = document.getElementById('downloadTranscriptBtn');
        dlBtn.disabled = false;
        dlBtn.onclick = downloadTranscript;
    }

    function downloadTranscript() {
        const lines = [
            `INTERVIEWACE MOCK INTERVIEW TRANSCRIPT`,
            `Date: ${new Date().toLocaleDateString()}`,
            `Company Style: ${selectedCompany}  |  Role: ${selectedRole}  |  Difficulty: ${selectedDifficulty}`,
            `Overall Score: ${finalScores.average_score || document.getElementById('scoreOverall').textContent}`,
            `Filler Words Detected: ${totalFillers}`,
            ``,
            `=== DIALOGUE ===`,
            ...dialogueHistory,
        ];
        const blob = new Blob([lines.join('\n\n')], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `InterviewAce_Transcript_${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    function cleanup() {
        isActive = false;
        if (audioRecorder) audioRecorder.stop();
        if (audioPlayer) audioPlayer.stop();
        if (agentVis) agentVis.stop();
        if (userVis) userVis.stop();
        if (camera) camera.stop();
        setTimeout(() => { if (ws) ws.close(); }, 1000);
    }
});
