/**
 * app.js
 * InterviewAce live meeting client with reconnect and analytics rendering.
 */

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
        this.smoothedVolume = 0;
    }

    start() {
        if (!this.isAnimating) {
            this.isAnimating = true;
            this.draw();
        }
    }

    stop() {
        this.isAnimating = false;
        this.rings.forEach(ring => {
            ring.style.transform = 'scale(1)';
            ring.style.opacity = '0';
        });
        this.eqBars.forEach(bar => { bar.style.height = '4px'; });
        if (this.tile) this.tile.classList.remove('tile-speaking');
        if (this.eqContainer) this.eqContainer.style.display = 'none';
        if (this.micIcon) this.micIcon.style.display = 'inline-block';
    }

    draw() {
        if (!this.isAnimating) return;
        requestAnimationFrame(() => this.draw());

        this.analyser.getByteFrequencyData(this.dataArray);
        let sum = 0;
        for (let i = 0; i < this.bufferLength; i += 1) {
            sum += this.dataArray[i];
        }

        const volume = (sum / this.bufferLength) / 128.0;
        this.smoothedVolume = this.smoothedVolume * 0.7 + volume * 0.3;
        const isSpeaking = this.smoothedVolume > 0.05;

        if (this.tile) {
            this.tile.classList.toggle('tile-speaking', isSpeaking);
        }

        if (isSpeaking && this.eqContainer) {
            this.eqContainer.style.display = 'flex';
            if (this.micIcon) this.micIcon.style.display = 'none';
        } else {
            if (this.eqContainer) this.eqContainer.style.display = 'none';
            if (this.micIcon) this.micIcon.style.display = 'inline-block';
        }

        if (this.rings.length === 3) {
            const scales = [0.3, 0.6, 1.0];
            this.rings.forEach((ring, index) => {
                ring.style.transform = isSpeaking
                    ? `scale(${Math.min(1 + this.smoothedVolume * scales[index], 2.1)})`
                    : 'scale(1)';
                ring.style.opacity = isSpeaking ? '0.35' : '0';
            });
        }

        if (isSpeaking && this.eqBars.length >= 3) {
            this.eqBars[0].style.height = `${Math.max(4, Math.min(15, this.smoothedVolume * 12 + 4))}px`;
            this.eqBars[1].style.height = `${Math.max(5, Math.min(16, this.smoothedVolume * 16 + 5))}px`;
            this.eqBars[2].style.height = `${Math.max(4, Math.min(15, this.smoothedVolume * 13 + 4))}px`;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const userId = `user_${Math.random().toString(36).slice(2, 9)}`;
    const sessionId = `session_${Math.random().toString(36).slice(2, 11)}`;
    const dashboard = new window.Dashboard();

    let ws = null;
    let reconnectTimeout = null;
    let heartbeatInterval = null;
    let reconnectAttempts = 0;
    let manualClose = false;
    let isActive = false;
    let sessionStartTime = null;
    let ccTimeout = null;
    let ccEnabled = true;
    let hasSentIntroPrompt = false;
    let audioStarted = false;
    let dialogueHistory = [];
    let finalReport = {};

    const camera = new window.CameraManager();
    let audioRecorder = null;
    let audioPlayer = null;
    let audioContext = null;
    let userVisualizer = null;
    let agentVisualizer = null;

    const setupPanel = document.getElementById('setupPanel');
    const meetingMain = document.getElementById('meetingMain');
    const bottomBar = document.getElementById('bottomBar');
    const sidebar = document.getElementById('analyticsSidebar');
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
    const companyBadge = document.getElementById('companyBadge');
    const meetingCode = document.getElementById('meetingCode');
    const feedbackPanel = document.getElementById('feedbackPanel');

    let selectedRole = 'general';
    let selectedCompany = 'general';
    let selectedDifficulty = 'medium';
    let selectedVoice = 'Kore';

    dashboard.setConnectionStatus('idle', 'Waiting');
    dashboard.setNetworkStatus('Network: Ready');

    window.toggleSidebar = function toggleSidebar() {
        sidebar.classList.toggle('hidden');
    };

    window.closeAllSidebars = function closeAllSidebars() {
        document.querySelectorAll('.right-sidebar').forEach(panel => panel.classList.remove('open'));
    };

    setInterval(() => {
        if (!clockTime) return;
        if (sessionStartTime && isActive) {
            const elapsed = Math.floor((Date.now() - sessionStartTime) / 1000);
            const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const seconds = String(elapsed % 60).padStart(2, '0');
            clockTime.textContent = `${minutes}:${seconds}`;
            return;
        }
        clockTime.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }, 1000);

    bindSidebars();
    bindControls();
    observeNetwork();

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

            const cameraReady = await camera.start();
            if (cameraReady) {
                document.getElementById('videoOverlay').style.display = 'none';
                cameraBtn.classList.remove('disabled-state');
                cameraBtn.innerHTML = '<span class="material-icons">videocam</span>';
                camera.startFrameExtraction(frame => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        sendJson({ type: 'image', mimeType: 'image/jpeg', data: frame });
                    }
                });
            } else {
                showToast('Camera unavailable. Continuing in audio-only mode.');
                dashboard.setConnectionStatus('warning', 'Audio Only');
            }

            agentVisualizer = new VolumeVisualizer(audioPlayer.getAnalyser(), 'agentRings', 'agentEqualizer', 'agentTile');
            userVisualizer = new VolumeVisualizer(audioRecorder.getAnalyser(), 'userRings', 'userEqualizer', 'userTile');
            agentVisualizer.start();
            userVisualizer.start();

            setupPanel.style.display = 'none';
            meetingMain.style.display = 'flex';
            bottomBar.style.display = 'flex';
            sidebar.classList.remove('hidden');

            companyBadge.textContent = selectedCompany === 'general'
                ? 'General'
                : selectedCompany.charAt(0).toUpperCase() + selectedCompany.slice(1);
            meetingCode.textContent = `${selectedCompany}-${selectedDifficulty}-interview`;

            connectWebSocket();
        } catch (error) {
            console.error('Initialization error:', error);
            showToast(`Initialization error: ${error.message}`);
        }
    });

    function bindSidebars() {
        const chatSidebar = document.getElementById('chatSidebar');
        const peopleSidebar = document.getElementById('peopleSidebar');
        const detailsSidebar = document.getElementById('detailsSidebar');
        const detailParams = document.getElementById('detailParams');
        const chatInput = document.getElementById('chatInput');
        const chatSendBtn = document.getElementById('chatSendBtn');
        const chatList = document.getElementById('chatList');

        document.querySelectorAll('.interaction-btn').forEach(button => {
            button.addEventListener('click', () => {
                const action = button.getAttribute('data-action');
                window.closeAllSidebars();

                if (action === 'Chat') {
                    chatSidebar.classList.add('open');
                    return;
                }
                if (action === 'People') {
                    peopleSidebar.classList.add('open');
                    return;
                }
                if (action === 'Meeting details') {
                    detailParams.innerHTML = `Role: <b style="color:#1a73e8">${selectedRole}</b><br>Company: <b style="color:#1a73e8">${selectedCompany}</b><br>Diff: <b style="color:#1a73e8">${selectedDifficulty}</b>`;
                    detailsSidebar.classList.add('open');
                    return;
                }
                if (action === 'Live Analysis') {
                    // Toggle the analytics sidebar
                    const sidebar = document.getElementById('analyticsSidebar');
                    if (sidebar) sidebar.classList.toggle('hidden');
                    return;
                }
                if (action) {
                    showToast(`"${action}" is unavailable early in the call.`);
                }
            });
        });

        if (!chatInput || !chatSendBtn || !chatList) return;
        chatInput.addEventListener('input', () => {
            chatSendBtn.disabled = chatInput.value.trim() === '';
        });
        chatInput.addEventListener('keypress', event => {
            if (event.key === 'Enter') chatSendBtn.click();
        });
        chatSendBtn.addEventListener('click', () => {
            const text = chatInput.value.trim();
            if (!text) return;

            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const node = document.createElement('div');
            node.className = 'chat-msg me';
            node.innerHTML = `<div class="chat-name">You<span class="chat-time">${time}</span></div>${text}`;
            chatList.appendChild(node);
            chatList.scrollTop = chatList.scrollHeight;

            sendJson({ type: 'text', text: `(In chat) Candidate says: ${text}` });
            chatInput.value = '';
            chatSendBtn.disabled = true;
        });
    }

    function bindControls() {
        endBtn.addEventListener('click', () => {
            if (!isActive) return;
            manualClose = true;
            sendJson({
                type: 'text',
                text: "I'd like to end the interview now. Please generate the session report.",
            });
            thinkingOverlay.style.display = 'block';
            setTimeout(() => {
                if (!finalReport.average_score) {
                    cleanup();
                    showFeedbackPanel();
                }
            }, 7000);
        });

        micBtn.addEventListener('click', () => {
            if (!audioRecorder) return;
            const isUnmuted = audioRecorder.toggleMute();
            micBtn.classList.toggle('disabled-state', !isUnmuted);
            micBtn.innerHTML = `<span class="material-icons">${isUnmuted ? 'mic' : 'mic_off'}</span>`;
            userMicIcon.textContent = isUnmuted ? 'mic' : 'mic_off';
            showToast(isUnmuted ? 'Microphone on' : 'Microphone muted');
        });

        cameraBtn.addEventListener('click', () => {
            const enabled = camera.toggle();
            cameraBtn.classList.toggle('disabled-state', !enabled);
            cameraBtn.innerHTML = `<span class="material-icons">${enabled ? 'videocam' : 'videocam_off'}</span>`;
            document.getElementById('videoOverlay').style.display = enabled ? 'none' : 'flex';
            showToast(enabled ? 'Camera on' : 'Camera off');
        });

        ccBtn.addEventListener('click', () => {
            ccEnabled = !ccEnabled;
            ccBtn.classList.toggle('active', ccEnabled);
            if (!ccEnabled) ccContainer.style.display = 'none';
            showToast(ccEnabled ? 'Captions on' : 'Captions off');
        });
    }

    function observeNetwork() {
        const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        const update = () => {
            if (!connection) {
                dashboard.setNetworkStatus('Network: Standard');
                return;
            }
            const label = `Network: ${(connection.effectiveType || 'stable').toUpperCase()}`;
            dashboard.setNetworkStatus(label);
        };
        update();
        if (connection && connection.addEventListener) {
            connection.addEventListener('change', update);
        }
    }

    function connectWebSocket() {
        clearTimeout(reconnectTimeout);
        dashboard.setConnectionStatus('connecting', reconnectAttempts > 0 ? 'Reconnecting' : 'Connecting');

        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const params = new URLSearchParams({
            voice: selectedVoice,
            role: selectedRole,
            company: selectedCompany,
            difficulty: selectedDifficulty,
        });
        ws = new WebSocket(`${protocol}//${location.host}/ws/${userId}/${sessionId}?${params}`);

        ws.onopen = async () => {
            reconnectAttempts = 0;
            isActive = true;
            sessionStartTime = sessionStartTime || Date.now();
            dashboard.setConnectionStatus('live', 'Live');
            thinkingOverlay.style.display = 'block';
            ccBtn.disabled = false;
            ccBtn.classList.add('active');

            startHeartbeat();

            if (!audioStarted && audioRecorder) {
                try {
                    await audioRecorder.start(buffer => {
                        if (ws && ws.readyState === WebSocket.OPEN) ws.send(buffer);
                    });
                    audioStarted = true;
                    micBtn.classList.remove('disabled-state');
                    micBtn.innerHTML = '<span class="material-icons">mic</span>';
                    userMicIcon.textContent = 'mic';
                } catch (error) {
                    console.error('Microphone error:', error);
                    showToast('Microphone unavailable. Text prompts still work.');
                }
            }

            // The server sends the intro prompt after the Live API connects.
            // We just show a waiting state here.
            if (!hasSentIntroPrompt) {
                hasSentIntroPrompt = true;
                showToast('Connecting to AI interviewer...');
            } else {
                showToast('Connection restored. Resuming session.');
            }
        };

        ws.onmessage = event => {
            if (typeof event.data !== 'string') return;
            try {
                handleAdkEvent(JSON.parse(event.data));
            } catch (error) {
                console.error('Event parse error:', error);
            }
        };

        ws.onclose = () => {
            stopHeartbeat();
            isActive = false;
            if (!manualClose) {
                scheduleReconnect();
            } else {
                dashboard.setConnectionStatus('idle', 'Session Ended');
            }
        };

        ws.onerror = error => {
            console.error('WebSocket error:', error);
            dashboard.setConnectionStatus('warning', 'Connection Issue');
        };
    }

    function startHeartbeat() {
        stopHeartbeat();
        heartbeatInterval = setInterval(() => {
            sendJson({ type: 'ping' });
        }, 15000);
    }

    function stopHeartbeat() {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }

    function scheduleReconnect() {
        reconnectAttempts += 1;
        const delay = Math.min(10000, 1200 * reconnectAttempts);
        dashboard.setConnectionStatus('warning', `Reconnecting ${reconnectAttempts}`);
        showToast(`Connection dropped. Reconnecting in ${Math.round(delay / 1000)}s...`);
        reconnectTimeout = setTimeout(connectWebSocket, delay);
    }

    function handleAdkEvent(event) {
        if (event.type === 'pong') {
            return;
        }

        if (event.type === 'live_ready') {
            dashboard.setConnectionStatus('live', 'Live');
            showToast('AI Interviewer connected. Interview starting...');
            return;
        }

        if (event.type === 'server_error') {
            const errStr = String(event.error);
            showToast(`Server Error: ${errStr}`, 5000);
            if (errStr.includes("403") || errStr.includes("400") || errStr.includes("API key")) {
                manualClose = true; // Stop reconnecting if it's an auth/fatal error
            }
            return;
        }

        if (event.customToolResponse) {
            processToolResult(event.customToolResponse);
        }

        if (event.content && event.content.parts) {
            thinkingOverlay.style.display = 'none';
            agentMicIcon.textContent = 'mic';
            agentMicIcon.classList.remove('red-icon');

            for (const part of event.content.parts) {
                if (part.text) {
                    dialogueHistory.push(`[Coach Ace]: ${part.text}`);
                }

                const inlineData = part.inlineData || part.inline_data;
                if (inlineData && inlineData.data && audioPlayer) {
                    audioPlayer.playBase64(inlineData.data);
                }

                const functionResponse = part.functionResponse || part.function_response;
                if (functionResponse) {
                    if (functionResponse.response && functionResponse.response.result && typeof functionResponse.response.result === 'string') {
                        functionResponse.response = JSON.parse(functionResponse.response.result);
                    }
                    processToolResult(functionResponse);
                }
            }
        }

        const inputTranscript = event.inputTranscription || event.input_transcription;
        if (inputTranscript && inputTranscript.text && inputTranscript.text.trim()) {
            const text = inputTranscript.text.trim();
            dialogueHistory.push(`[You]: ${text}`);
            thinkingOverlay.style.display = 'block';
            showCaptions('You', 'Y', 'bg-green', text);
            pulseTranscription();
        }

        const outputTranscript = event.outputTranscription || event.output_transcription;
        if (outputTranscript && outputTranscript.text && outputTranscript.text.trim()) {
            showCaptions('Coach Ace', 'C', 'bg-blue', outputTranscript.text.trim());
            pulseTranscription();
        }

        if (event.turnComplete || event.turn_complete || event.interrupted) {
            agentMicIcon.textContent = 'mic_off';
            agentMicIcon.classList.add('red-icon');
            thinkingOverlay.style.display = 'none';
            if (event.interrupted && audioPlayer) audioPlayer.stop();
        }
    }

    function processToolResult(result) {
        if (!result || !result.response) return;
        const data = typeof result.response === 'string' ? JSON.parse(result.response) : result.response;
        const name = result.name;

        dashboard.handleToolResult(name, data);

        if (name === 'analyze_body_language') {
            updateBodyIndicator('dotEye', 'lblEye', data.eye_contact);
            updateBodyIndicator('dotPosture', 'lblPosture', data.posture);
            updateBodyIndicator('dotExpression', 'lblExpression', data.expression);
        }

        if (name === 'evaluate_star_method') {
            const components = data.components_present || {};
            setStarBadge('sSituation', components.situation);
            setStarBadge('sTask', components.task);
            setStarBadge('sAction', components.action);
            setStarBadge('sResult', components.result);
        }

        if (name === 'generate_session_report') {
            finalReport = { ...finalReport, ...data };
            dashboard.storeSessionSummary(finalReport);
            cleanup();
            if (manualClose && feedbackPanel.style.display !== 'flex') {
                showFeedbackPanel();
            }
        }
    }

    function sendJson(payload) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(payload));
        }
    }

    function pulseTranscription() {
        transcribingBadge.style.display = 'flex';
        clearTimeout(ccTimeout);
        ccTimeout = setTimeout(() => {
            transcribingBadge.style.display = 'none';
        }, 3000);
    }

    function showCaptions(name, initial, colorClass, text) {
        if (!ccEnabled) return;
        ccContainer.style.display = 'flex';
        ccName.textContent = name;
        ccText.textContent = text;
        ccAvatar.className = `cc-avatar ${colorClass}`;
        ccAvatar.textContent = initial;
        clearTimeout(ccTimeout);
        ccTimeout = setTimeout(() => {
            ccContainer.style.display = 'none';
        }, 5000);
    }

    function updateBodyIndicator(dotId, labelId, rating) {
        if (!rating) return;
        const dot = document.getElementById(dotId);
        const label = document.getElementById(labelId);
        if (label) label.textContent = rating;
        if (dot) {
            dot.className = `bi-dot ${['excellent', 'good', 'confident', 'engaged', 'natural'].includes(rating) ? 'good' : 'bad'}`;
        }
    }

    function setStarBadge(id, isPresent) {
        const element = document.getElementById(id);
        if (!element) return;
        const badge = element.querySelector('.si-badge');
        if (badge) {
            badge.className = `si-badge ${isPresent ? 'on' : 'off'}`;
        }
    }

    function showFeedbackPanel() {
        feedbackPanel.style.display = 'flex';

        const overall = finalReport.average_score || finalReport.overall_score || 0;
        document.getElementById('scoreOverall').textContent = overall;
        document.getElementById('scoreConfidence').textContent = finalReport.confidence || 0;
        document.getElementById('scoreClarity').textContent = finalReport.clarity || 0;
        document.getElementById('scoreContent').textContent = finalReport.content || 0;
        document.getElementById('scoreStar').textContent = finalReport.star_score || 0;
        document.getElementById('scoreBody').textContent = finalReport.body_language || 0;

        const tierBadge = document.getElementById('tierBadge');
        tierBadge.innerHTML = `<span class="tier-pill">${finalReport.performance_tier || 'Session complete'}</span>`;

        const notes = [];
        if (finalReport.strengths) notes.push(`<p><strong>Strengths:</strong> ${finalReport.strengths}</p>`);
        if (finalReport.improvements) notes.push(`<p><strong>Growth Area:</strong> ${finalReport.improvements}</p>`);
        if (Array.isArray(finalReport.study_plan) && finalReport.study_plan.length) {
            notes.push(`<p><strong>Study Plan:</strong></p><ul>${finalReport.study_plan.map(item => `<li>${item}</li>`).join('')}</ul>`);
        }
        document.getElementById('feedbackContent').innerHTML = notes.join('') || '<p>Session analytics have been saved.</p>';

        const downloadBtn = document.getElementById('downloadTranscriptBtn');
        downloadBtn.disabled = false;
        downloadBtn.onclick = downloadTranscript;
    }

    function downloadTranscript() {
        const lines = [
            'INTERVIEWACE MOCK INTERVIEW TRANSCRIPT',
            `Date: ${new Date().toLocaleDateString()}`,
            `Company Style: ${selectedCompany}`,
            `Role: ${selectedRole}`,
            `Difficulty: ${selectedDifficulty}`,
            `Overall Score: ${finalReport.average_score || 0}`,
            '',
            '=== DIALOGUE ===',
            ...dialogueHistory,
        ];
        const blob = new Blob([lines.join('\n\n')], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `InterviewAce_Transcript_${new Date().toISOString().slice(0, 10)}.txt`;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
    }

    function cleanup() {
        manualClose = true;
        isActive = false;
        stopHeartbeat();
        clearTimeout(reconnectTimeout);
        dashboard.storeSessionSummary(finalReport);

        if (audioRecorder) audioRecorder.stop();
        if (audioPlayer) audioPlayer.stop();
        if (agentVisualizer) agentVisualizer.stop();
        if (userVisualizer) userVisualizer.stop();
        camera.stop();

        if (ws) {
            try {
                ws.close();
            } catch (error) {
                console.warn('Unable to close websocket cleanly', error);
            }
        }
    }

    function showToast(message, duration = 2600) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), duration);
    }
});
