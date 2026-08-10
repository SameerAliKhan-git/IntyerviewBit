/**
 * app.js
 * InterviewAce live meeting client.
 *
 * Session identity comes from the server (POST /api/session) as an id plus a signed
 * token; the browser never chooses its own session id, and every analytics read presents
 * that token. All model-derived text is escaped before it reaches the DOM.
 */

const esc = window.escapeHtml;
const score = window.toScore;

const MAX_RECONNECT_ATTEMPTS = 6;

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
        this.frameId = null;
    }

    start() {
        if (this.isAnimating) return;
        this.isAnimating = true;
        this.draw();
    }

    stop() {
        this.isAnimating = false;
        if (this.frameId) {
            cancelAnimationFrame(this.frameId);
            this.frameId = null;
        }
        this.rings.forEach((ring) => {
            ring.style.transform = 'scale(1)';
            ring.style.opacity = '0';
        });
        this.eqBars.forEach((bar) => {
            bar.style.height = '4px';
        });
        if (this.tile) this.tile.classList.remove('tile-speaking');
        if (this.eqContainer) this.eqContainer.style.display = 'none';
        if (this.micIcon) this.micIcon.style.display = 'inline-block';
    }

    draw() {
        if (!this.isAnimating) return;
        this.frameId = requestAnimationFrame(() => this.draw());

        this.analyser.getByteFrequencyData(this.dataArray);
        let sum = 0;
        for (let i = 0; i < this.bufferLength; i += 1) {
            sum += this.dataArray[i];
        }

        const volume = sum / this.bufferLength / 128.0;
        this.smoothedVolume = this.smoothedVolume * 0.7 + volume * 0.3;
        const isSpeaking = this.smoothedVolume > 0.05;

        if (this.tile) this.tile.classList.toggle('tile-speaking', isSpeaking);

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
    const dashboard = new window.Dashboard();

    let sessionId = null;
    let sessionToken = null;
    let ws = null;
    let reconnectTimeout = null;
    let heartbeatInterval = null;
    let reconnectAttempts = 0;
    let manualClose = false;
    let isActive = false;
    let sessionStartTime = null;
    let ccTimeout = null;
    let transcribeTimeout = null;
    let ccEnabled = true;
    let audioStarted = false;
    let reportShown = false;
    const dialogueHistory = [];
    let candidateUtterance = '';
    let agentUtterance = '';
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
    const videoOverlay = document.getElementById('videoOverlay');

    let selectedRole = 'general';
    let selectedCompany = 'general';
    let selectedDifficulty = 'medium';
    let selectedVoice = 'Kore';

    dashboard.setConnectionStatus('idle', 'Waiting');
    dashboard.setNetworkStatus('Network: Ready');

    function showToast(message, duration = 2600) {
        const container = document.getElementById('toastContainer');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = 'toast';
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), duration);
    }

    // Exposed because other modules and delegated handlers call it.
    window.showToast = showToast;

    function toggleAnalyticsSidebar() {
        sidebar.classList.toggle('hidden');
    }

    function closeAllSidebars() {
        document.querySelectorAll('.right-sidebar').forEach((panel) => panel.classList.remove('open'));
    }

    setInterval(() => {
        if (!clockTime) return;
        if (sessionStartTime && isActive) {
            const elapsed = Math.floor((Date.now() - sessionStartTime) / 1000);
            const minutes = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const seconds = String(elapsed % 60).padStart(2, '0');
            clockTime.textContent = `${minutes}:${seconds}`;
            return;
        }
        clockTime.textContent = new Date().toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
        });
    }, 1000);

    bindSidebars();
    bindControls();
    bindDialogActions();
    observeNetwork();

    setupJoinBtn.addEventListener('click', async () => {
        setupJoinBtn.disabled = true;
        selectedRole = document.getElementById('roleSelect').value;
        selectedCompany = document.getElementById('companySelect').value;
        selectedDifficulty = document.getElementById('difficultySelect').value;
        selectedVoice = document.getElementById('voiceSelect').value;

        try {
            const ticket = await requestSessionTicket();
            sessionId = ticket.session_id;
            sessionToken = ticket.token;

            audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000,
            });
            if (audioContext.state === 'suspended') await audioContext.resume();

            audioPlayer = new window.AudioPlayer(audioContext);
            audioRecorder = new window.AudioRecorder(audioContext);

            const cameraReady = await camera.start();
            if (cameraReady) {
                videoOverlay.style.display = 'none';
                cameraBtn.classList.remove('disabled-state');
                cameraBtn.innerHTML = '<span class="material-icons">videocam</span>';
                camera.startFrameExtraction((frame) => {
                    sendJson({ type: 'image', mimeType: 'image/jpeg', data: frame });
                });
            } else {
                showToast('Camera unavailable. Continuing in audio-only mode.');
                dashboard.setConnectionStatus('warning', 'Audio Only');
            }

            agentVisualizer = new VolumeVisualizer(
                audioPlayer.getAnalyser(), 'agentRings', 'agentEqualizer', 'agentTile');
            userVisualizer = new VolumeVisualizer(
                audioRecorder.getAnalyser(), 'userRings', 'userEqualizer', 'userTile');
            agentVisualizer.start();
            userVisualizer.start();

            setupPanel.style.display = 'none';
            meetingMain.style.display = 'flex';
            bottomBar.style.display = 'flex';
            sidebar.classList.remove('hidden');

            companyBadge.textContent =
                selectedCompany === 'general'
                    ? 'General'
                    : selectedCompany.charAt(0).toUpperCase() + selectedCompany.slice(1);
            meetingCode.textContent = `${selectedCompany}-${selectedDifficulty}-interview`;

            connectWebSocket();
        } catch (error) {
            console.error('Initialization error:', error);
            showToast(`Could not start the interview: ${error.message}`, 6000);
            setupJoinBtn.disabled = false;
        }
    });

    async function requestSessionTicket() {
        const response = await fetch('/api/session', { method: 'POST' });
        if (response.status === 429) {
            const body = await response.json().catch(() => ({}));
            throw new Error(body.detail || 'Rate limited. Please try again shortly.');
        }
        if (!response.ok) {
            throw new Error(`Server refused the session (HTTP ${response.status})`);
        }
        return response.json();
    }

    function bindSidebars() {
        const chatSidebar = document.getElementById('chatSidebar');
        const peopleSidebar = document.getElementById('peopleSidebar');
        const detailsSidebar = document.getElementById('detailsSidebar');
        const detailParams = document.getElementById('detailParams');
        const chatInput = document.getElementById('chatInput');
        const chatSendBtn = document.getElementById('chatSendBtn');
        const chatList = document.getElementById('chatList');

        document.querySelectorAll('.sidebar-close, .close-sidebar-btn').forEach((button) => {
            button.addEventListener('click', () => {
                if (button.classList.contains('sidebar-close')) {
                    toggleAnalyticsSidebar();
                    return;
                }
                closeAllSidebars();
            });
        });

        document.querySelectorAll('.interaction-btn').forEach((button) => {
            button.addEventListener('click', () => {
                const action = button.getAttribute('data-action');
                closeAllSidebars();

                if (action === 'Chat') {
                    chatSidebar.classList.add('open');
                    return;
                }
                if (action === 'People') {
                    peopleSidebar.classList.add('open');
                    return;
                }
                if (action === 'Meeting details') {
                    detailParams.textContent =
                        `Role: ${selectedRole} · Company: ${selectedCompany} · Difficulty: ${selectedDifficulty}`;
                    detailsSidebar.classList.add('open');
                    return;
                }
                if (action === 'Live Analysis') {
                    toggleAnalyticsSidebar();
                    button.classList.toggle('active', !sidebar.classList.contains('hidden'));
                    return;
                }
                if (action) {
                    showToast(`"${action}" is not available in this mock interview.`);
                }
            });
        });

        if (!chatInput || !chatSendBtn || !chatList) return;
        chatInput.addEventListener('input', () => {
            chatSendBtn.disabled = chatInput.value.trim() === '';
        });
        chatInput.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') chatSendBtn.click();
        });
        chatSendBtn.addEventListener('click', () => {
            const text = chatInput.value.trim();
            if (!text) return;

            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const node = document.createElement('div');
            node.className = 'chat-msg me';

            // Built as nodes rather than an HTML string: this is raw user input.
            const nameRow = document.createElement('div');
            nameRow.className = 'chat-name';
            nameRow.textContent = 'You';
            const timeSpan = document.createElement('span');
            timeSpan.className = 'chat-time';
            timeSpan.textContent = time;
            nameRow.appendChild(timeSpan);
            node.appendChild(nameRow);
            node.appendChild(document.createTextNode(text));

            chatList.appendChild(node);
            chatList.scrollTop = chatList.scrollHeight;

            dialogueHistory.push(`[You - chat]: ${text}`);
            sendJson({ type: 'text', text: `(In chat) Candidate says: ${text}` });
            chatInput.value = '';
            chatSendBtn.disabled = true;
        });
    }

    function bindControls() {
        endBtn.addEventListener('click', () => {
            if (!isActive) return;
            endBtn.disabled = true;
            endInterview('ended_by_candidate');
        });

        micBtn.addEventListener('click', () => {
            if (!audioRecorder) return;
            const isUnmuted = audioRecorder.toggleMute();
            micBtn.classList.toggle('disabled-state', !isUnmuted);
            micBtn.innerHTML = `<span class="material-icons">${isUnmuted ? 'mic' : 'mic_off'}</span>`;
            micBtn.setAttribute('aria-pressed', String(!isUnmuted));
            userMicIcon.textContent = isUnmuted ? 'mic' : 'mic_off';
            showToast(isUnmuted ? 'Microphone on' : 'Microphone muted');
        });

        cameraBtn.addEventListener('click', () => {
            const enabled = camera.toggle();
            cameraBtn.classList.toggle('disabled-state', !enabled);
            cameraBtn.innerHTML = `<span class="material-icons">${enabled ? 'videocam' : 'videocam_off'}</span>`;
            cameraBtn.setAttribute('aria-pressed', String(!enabled));
            videoOverlay.style.display = enabled ? 'none' : 'flex';
            showToast(enabled ? 'Camera on' : 'Camera off — no video is being sent');
        });

        ccBtn.addEventListener('click', () => {
            ccEnabled = !ccEnabled;
            ccBtn.classList.toggle('active', ccEnabled);
            ccBtn.setAttribute('aria-pressed', String(ccEnabled));
            if (!ccEnabled) ccContainer.style.display = 'none';
            showToast(ccEnabled ? 'Captions on' : 'Captions off');
        });
    }

    function bindDialogActions() {
        const newSessionBtn = document.getElementById('newSessionBtn');
        if (newSessionBtn) {
            newSessionBtn.addEventListener('click', () => window.location.reload());
        }
        const copyBtn = document.getElementById('copyJoinInfoBtn');
        if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(window.location.origin);
                    showToast('Meeting link copied');
                } catch (error) {
                    showToast('Could not copy the link');
                }
            });
        }
    }

    function observeNetwork() {
        const connection =
            navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        const update = () => {
            if (!connection) {
                dashboard.setNetworkStatus('Network: Standard');
                return;
            }
            dashboard.setNetworkStatus(
                `Network: ${(connection.effectiveType || 'stable').toUpperCase()}`);
        };
        update();
        if (connection && connection.addEventListener) {
            connection.addEventListener('change', update);
        }
    }

    function connectWebSocket() {
        clearTimeout(reconnectTimeout);
        dashboard.setConnectionStatus(
            'connecting', reconnectAttempts > 0 ? 'Reconnecting' : 'Connecting');

        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const params = new URLSearchParams({
            token: sessionToken,
            voice: selectedVoice,
            role: selectedRole,
            company: selectedCompany,
            difficulty: selectedDifficulty,
        });
        ws = new WebSocket(`${protocol}//${location.host}/ws/${encodeURIComponent(sessionId)}?${params}`);

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
                    await audioRecorder.start((buffer) => {
                        if (ws && ws.readyState === WebSocket.OPEN) ws.send(buffer);
                    });
                    audioStarted = true;
                    micBtn.classList.remove('disabled-state');
                    micBtn.innerHTML = '<span class="material-icons">mic</span>';
                    userMicIcon.textContent = 'mic';
                } catch (error) {
                    console.error('Microphone error:', error);
                    showToast('Microphone unavailable. You can still use the chat panel.', 5000);
                }
            }
        };

        ws.onmessage = (event) => {
            if (typeof event.data !== 'string') return;
            try {
                handleAdkEvent(JSON.parse(event.data));
            } catch (error) {
                console.error('Event parse error:', error);
            }
        };

        ws.onclose = (event) => {
            stopHeartbeat();
            isActive = false;
            if (manualClose) {
                dashboard.setConnectionStatus('idle', 'Session Ended');
                return;
            }
            if (event.code === 1008) {
                // Token rejected; reconnecting cannot help.
                dashboard.setConnectionStatus('warning', 'Session expired');
                showToast('Your session expired. Start a new interview.', 6000);
                manualClose = true;
                return;
            }
            console.warn('WebSocket closed unexpectedly:', event.code, event.reason);
            scheduleReconnect();
        };

        ws.onerror = () => {
            dashboard.setConnectionStatus('warning', 'Connection Issue');
        };
    }

    function startHeartbeat() {
        stopHeartbeat();
        heartbeatInterval = setInterval(() => sendJson({ type: 'ping' }), 15000);
    }

    function stopHeartbeat() {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }

    function scheduleReconnect() {
        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            dashboard.setConnectionStatus('warning', 'Disconnected');
            showToast('Could not reconnect. Your report is still available below.', 6000);
            endInterview('connection_lost');
            return;
        }

        reconnectAttempts += 1;
        // Exponential backoff with jitter, so a server restart does not get a thundering
        // herd of clients retrying in lockstep.
        const base = Math.min(10000, 1000 * 2 ** (reconnectAttempts - 1));
        const delay = Math.round(base * (0.7 + Math.random() * 0.6));
        dashboard.setConnectionStatus('warning', `Reconnecting ${reconnectAttempts}`);
        showToast(`Connection dropped. Reconnecting in ${Math.round(delay / 1000)}s...`);
        reconnectTimeout = setTimeout(connectWebSocket, delay);
    }

    function handleAdkEvent(event) {
        if (event.type === 'pong') return;

        if (event.type === 'live_ready') {
            dashboard.setConnectionStatus('live', 'Live');
            showToast('Connected. Coach Ace is joining...');
            return;
        }

        if (event.type === 'session_expired') {
            showToast('Session time limit reached. Generating your report...', 5000);
            endInterview('time_limit');
            return;
        }

        if (event.type === 'server_error') {
            handleServerError(event);
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
                // part.text on a native-audio model is usually the model's private
                // reasoning, not speech. Recording it would put Coach Ace's internal
                // monologue into the candidate's transcript; the words actually spoken
                // arrive via outputTranscription instead.
                if (part.text && part.thought) {
                    console.debug('thought part suppressed');
                }

                const inlineData = part.inlineData || part.inline_data;
                if (inlineData && inlineData.data && audioPlayer) {
                    audioPlayer.playBase64(inlineData.data);
                }

                const functionResponse = part.functionResponse || part.function_response;
                if (functionResponse) {
                    processToolResult(functionResponse);
                }
            }
        }

        // Transcription arrives in fragments. They are accumulated per speaker and
        // committed as one line per utterance, otherwise the downloaded transcript is
        // shredded into dozens of partial words.
        const inputTranscript = event.inputTranscription || event.input_transcription;
        if (inputTranscript && inputTranscript.text) {
            flushUtterance('agent');
            candidateUtterance += inputTranscript.text;
            thinkingOverlay.style.display = 'block';
            showCaptions('You', 'Y', 'bg-green', candidateUtterance.trim());
            pulseTranscription();
        }

        const outputTranscript = event.outputTranscription || event.output_transcription;
        if (outputTranscript && outputTranscript.text) {
            flushUtterance('candidate');
            agentUtterance += outputTranscript.text;
            showCaptions('Coach Ace', 'C', 'bg-blue', agentUtterance.trim());
            pulseTranscription();
        }

        if (event.interrupted && audioPlayer) {
            // Cut the agent off the moment the candidate starts talking.
            audioPlayer.stop();
        }

        if (event.turnComplete || event.turn_complete || event.interrupted) {
            flushUtterance('all');
            agentMicIcon.textContent = 'mic_off';
            agentMicIcon.classList.add('red-icon');
            thinkingOverlay.style.display = 'none';
        }
    }

    function handleServerError(event) {
        const category = event.category || 'transient';
        const message = event.message || 'The connection to the AI was interrupted.';
        console.warn('Server error event:', category, event.error);

        // Quota exhaustion and auth failures cannot be retried away. Reconnecting into
        // them produces a loop of identical failures, so end cleanly and show the
        // candidate the scores captured up to this point.
        if (category === 'quota' || category === 'auth') {
            showToast(message, 9000);
            manualClose = true;
            dashboard.setConnectionStatus('warning', category === 'quota' ? 'Quota reached' : 'Unavailable');
            endInterview(category);
            return;
        }

        showToast(message, 3000);
    }

    function processToolResult(result) {
        if (!result || !result.response) return;

        let data = result.response;
        if (typeof data === 'string') {
            try {
                data = JSON.parse(data);
            } catch (error) {
                return;
            }
        }
        // ADK wraps plain-dict tool returns as {result: "<json string>"}.
        if (data && typeof data.result === 'string') {
            try {
                data = JSON.parse(data.result);
            } catch (error) {
                return;
            }
        }
        if (!data || typeof data !== 'object') return;

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
        }
    }

    function sendJson(payload) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify(payload));
        }
    }

    /**
     * Ends the interview deterministically.
     *
     * The report is fetched from the server rather than waiting for the model to decide
     * to call a tool, so the modal can never open with an empty scorecard.
     */
    async function endInterview(reason) {
        if (reportShown) return;
        reportShown = true;
        manualClose = true;
        thinkingOverlay.style.display = 'block';
        // Commit whatever was mid-utterance so it appears in the transcript.
        flushUtterance('all');

        if (reason === 'ended_by_candidate') {
            sendJson({
                type: 'text',
                text: "I'd like to end the interview now. Please give me a short closing summary.",
            });
        }

        try {
            const response = await fetch(
                `/api/sessions/${encodeURIComponent(sessionId)}/report?token=${encodeURIComponent(sessionToken)}`,
                { method: 'POST' },
            );
            if (response.ok) {
                finalReport = { ...finalReport, ...(await response.json()) };
            } else {
                console.warn('Report request failed:', response.status);
            }
        } catch (error) {
            console.warn('Report request failed:', error);
        }

        dashboard.handleToolResult('generate_session_report', finalReport);
        cleanup();
        showFeedbackPanel();
    }

    /** Commits any buffered speech to the transcript. */
    function flushUtterance(who) {
        if ((who === 'candidate' || who === 'all') && candidateUtterance.trim()) {
            dialogueHistory.push(`[You]: ${candidateUtterance.trim()}`);
            candidateUtterance = '';
        }
        if ((who === 'agent' || who === 'all') && agentUtterance.trim()) {
            dialogueHistory.push(`[Coach Ace]: ${agentUtterance.trim()}`);
            agentUtterance = '';
        }
    }

    function pulseTranscription() {
        transcribingBadge.style.display = 'flex';
        clearTimeout(transcribeTimeout);
        transcribeTimeout = setTimeout(() => {
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
        if (label) label.textContent = String(rating);
        if (dot) {
            const positive = ['excellent', 'good', 'confident', 'engaged', 'natural'].includes(rating);
            dot.className = `bi-dot ${positive ? 'good' : 'bad'}`;
        }
    }

    function setStarBadge(id, isPresent) {
        const element = document.getElementById(id);
        if (!element) return;
        const badge = element.querySelector('.si-badge');
        if (badge) badge.className = `si-badge ${isPresent ? 'on' : 'off'}`;
    }

    function showFeedbackPanel() {
        feedbackPanel.style.display = 'flex';

        const overall = score(finalReport.average_score || finalReport.overall_score);
        const conf = score(finalReport.confidence);
        const clar = score(finalReport.clarity);
        const cont = score(finalReport.content);
        const star = score(finalReport.star_score);
        const body = score(finalReport.body_language);

        document.getElementById('scoreOverall').textContent = String(overall);
        document.getElementById('scoreConfidence').textContent = String(conf);
        document.getElementById('scoreClarity').textContent = String(clar);
        document.getElementById('scoreContent').textContent = String(cont);
        document.getElementById('scoreStar').textContent = String(star);
        document.getElementById('scoreBody').textContent = String(body);

        const tierBadge = document.getElementById('tierBadge');
        tierBadge.innerHTML =
            `<span class="tier-pill">${esc(finalReport.performance_tier || 'Session complete')}</span>`;

        const sections = [];

        if (!finalReport.total_questions_answered) {
            sections.push(`
                <div class="fb-section">
                    <p>No answers were scored in this session, so there is nothing to chart yet.
                    Try a session with at least three answers for a full breakdown.</p>
                </div>`);
        }

        const scores = [
            { label: 'Confidence', value: conf, color: '#4285f4' },
            { label: 'Clarity', value: clar, color: '#34a853' },
            { label: 'Content', value: cont, color: '#ea4335' },
            { label: 'STAR', value: star, color: '#fbbc05' },
            { label: 'Body Lang.', value: body, color: '#a142f4' },
        ];
        if (scores.some((item) => item.value > 0)) {
            sections.push(`
                <div class="fb-section">
                    <div class="fb-section-title"><span class="material-icons">bar_chart</span> Score Breakdown</div>
                    <div class="fb-bar-chart">
                        ${scores.map((item) => `
                            <div class="fb-bar-row">
                                <span class="fb-bar-label">${esc(item.label)}</span>
                                <div class="fb-bar-track">
                                    <div class="fb-bar-fill" style="width:${item.value}%;background:${item.color}"></div>
                                </div>
                                <span class="fb-bar-value">${item.value}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>`);
        }

        const radar = finalReport.competency_radar || {};
        const radarKeys = ['confidence', 'clarity', 'body_language', 'content', 'star', 'voice', 'engagement'];
        const radarNames = ['Confidence', 'Clarity', 'Body Lang', 'Content', 'STAR', 'Voice', 'Engage'];
        if (radarKeys.some((key) => score(radar[key]) > 0)) {
            const cx = 120;
            const cy = 105;
            const r = 70;
            const angleFor = (i) => -Math.PI / 2 + (Math.PI * 2 * i) / radarKeys.length;

            const gridPolys = [0.25, 0.5, 0.75, 1].map((scale) => {
                const pts = radarKeys.map((_, i) => {
                    const a = angleFor(i);
                    return `${cx + Math.cos(a) * r * scale},${cy + Math.sin(a) * r * scale}`;
                }).join(' ');
                return `<polygon points="${pts}" fill="none" stroke="rgba(255,255,255,0.1)" stroke-width="0.5"/>`;
            }).join('');

            const dataPoly = radarKeys.map((key, i) => {
                const a = angleFor(i);
                const v = score(radar[key]) / 100;
                return `${cx + Math.cos(a) * r * v},${cy + Math.sin(a) * r * v}`;
            }).join(' ');

            const labelsHTML = radarKeys.map((_, i) => {
                const a = angleFor(i);
                const lx = cx + Math.cos(a) * (r + 18);
                const ly = cy + Math.sin(a) * (r + 18);
                return `<text x="${lx}" y="${ly}" fill="#aaa" font-size="9" text-anchor="middle" dominant-baseline="middle">${esc(radarNames[i])}</text>`;
            }).join('');

            sections.push(`
                <div class="fb-section">
                    <div class="fb-section-title"><span class="material-icons">radar</span> Competency Radar</div>
                    <svg viewBox="0 0 240 210" class="fb-radar-svg" role="img" aria-label="Competency radar">
                        ${gridPolys}
                        <polygon points="${dataPoly}" fill="rgba(66,133,244,0.25)" stroke="#4285f4" stroke-width="1.5"/>
                        ${labelsHTML}
                    </svg>
                </div>`);
        }

        const heatmap = Array.isArray(finalReport.heatmap) ? finalReport.heatmap : [];
        if (heatmap.length) {
            const heatHTML = heatmap.map((item) => {
                const bg = item.intensity === 'high' ? '#34a853'
                    : item.intensity === 'medium' ? '#fbbc05' : '#ea4335';
                return `<div class="fb-heat-cell" style="border-left:3px solid ${bg}">
                    <strong>Q${esc(item.question_number)}</strong>
                    <span>${esc(String(item.focus_area || '').replace('_', ' '))}</span>
                    <em>${score(item.overall)}/100</em>
                </div>`;
            }).join('');
            sections.push(`
                <div class="fb-section">
                    <div class="fb-section-title"><span class="material-icons">grid_view</span> Performance Heatmap</div>
                    <div class="fb-heatmap">${heatHTML}</div>
                </div>`);
        }

        const milestones = Array.isArray(finalReport.milestones) ? finalReport.milestones : [];
        if (milestones.length) {
            sections.push(`
                <div class="fb-section">
                    <div class="fb-section-title"><span class="material-icons">workspace_premium</span> Milestones Earned</div>
                    <div class="fb-badges">${milestones.map((m) =>
                        `<span class="fb-badge" title="${esc(m.description)}">${esc(m.badge)}</span>`).join('')}</div>
                </div>`);
        }

        if (finalReport.strengths || finalReport.improvements) {
            sections.push(`
                <div class="fb-section fb-cols">
                    ${finalReport.strengths ? `<div class="fb-col good"><div class="fb-col-title"><span class="material-icons">thumb_up</span> Strengths</div><p>${esc(finalReport.strengths)}</p></div>` : ''}
                    ${finalReport.improvements ? `<div class="fb-col grow"><div class="fb-col-title"><span class="material-icons">trending_up</span> Growth Area</div><p>${esc(finalReport.improvements)}</p></div>` : ''}
                </div>`);
        }

        if (Array.isArray(finalReport.study_plan) && finalReport.study_plan.length) {
            const planItems = finalReport.study_plan.map((item) => {
                if (typeof item === 'string') return `<li>${esc(item)}</li>`;
                return `<li><strong>${esc(item.area || item.focus)}:</strong> ${esc(item.goal || item.drill || item.tip)}</li>`;
            }).join('');
            sections.push(`
                <div class="fb-section">
                    <div class="fb-section-title"><span class="material-icons">school</span> Study Plan</div>
                    <ul class="fb-study-list">${planItems}</ul>
                </div>`);
        }

        if (Array.isArray(finalReport.recommendations) && finalReport.recommendations.length) {
            sections.push(`
                <div class="fb-section">
                    <div class="fb-section-title"><span class="material-icons">lightbulb</span> Recommendations</div>
                    <ul class="fb-study-list">${finalReport.recommendations.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
                </div>`);
        }

        const fws = finalReport.filler_word_summary;
        if (fws) {
            sections.push(`
                <div class="fb-section">
                    <div class="fb-section-title"><span class="material-icons">record_voice_over</span> Filler Words</div>
                    <p>Total: <strong>${esc(fws.total)}</strong> — Rating: <strong>${esc(fws.rating)}</strong></p>
                    <p class="fb-note">Measured from your actual speech transcript.</p>
                </div>`);
        }

        document.getElementById('feedbackContent').innerHTML =
            sections.join('') || '<p>Session analytics have been saved.</p>';

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
            `Overall Score: ${score(finalReport.average_score)}`,
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

        if (audioRecorder) audioRecorder.stop();
        if (audioPlayer) audioPlayer.stop();
        if (agentVisualizer) agentVisualizer.stop();
        if (userVisualizer) userVisualizer.stop();
        camera.stop();

        if (ws) {
            try {
                ws.close(1000, 'Session ended');
            } catch (error) {
                console.warn('Unable to close websocket cleanly', error);
            }
        }
    }

    window.addEventListener('beforeunload', () => {
        if (isActive) cleanup();
    });
});
