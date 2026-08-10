/**
 * audio-recorder.js — Captures microphone audio as raw 16-bit PCM.
 *
 * Uses an AudioWorklet so conversion happens off the main thread. ScriptProcessorNode is
 * deprecated and runs on the main thread, where layout and rendering work show up as
 * audio jitter; it is kept only as a fallback for browsers without AudioWorklet.
 */

const WORKLET_URL = '/static/js/pcm-recorder-processor.js';
const FALLBACK_BUFFER_SIZE = 2048;

class AudioRecorder {
    constructor(audioContext) {
        this.context = audioContext;
        this.stream = null;
        this.source = null;
        this.workletNode = null;
        this.fallbackProcessor = null;
        this.silentGain = null;
        this.isMuted = false;

        this.analyser = this.context.createAnalyser();
        this.analyser.fftSize = 256;
    }

    getAnalyser() {
        return this.analyser;
    }

    async start(onData) {
        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });

        this.source = this.context.createMediaStreamSource(this.stream);
        this.source.connect(this.analyser);

        const emit = (float32) => {
            if (this.isMuted) return;
            onData(this._toPcm16(float32));
        };

        if (this.context.audioWorklet) {
            try {
                await this.context.audioWorklet.addModule(WORKLET_URL);
                this.workletNode = new AudioWorkletNode(this.context, 'pcm-recorder-processor', {
                    numberOfInputs: 1,
                    numberOfOutputs: 0,
                    channelCount: 1,
                });
                this.workletNode.port.onmessage = (event) => emit(event.data);
                this.source.connect(this.workletNode);
                return;
            } catch (error) {
                console.warn('AudioWorklet unavailable, falling back to ScriptProcessor:', error);
            }
        }

        this._startFallback(emit);
    }

    _startFallback(emit) {
        this.fallbackProcessor = this.context.createScriptProcessor(FALLBACK_BUFFER_SIZE, 1, 1);
        this.fallbackProcessor.onaudioprocess = (event) => {
            emit(event.inputBuffer.getChannelData(0));
        };
        this.source.connect(this.fallbackProcessor);

        // A ScriptProcessorNode only fires while connected to a destination. Route it
        // through a muted gain node so it runs without echoing the mic to the speakers.
        this.silentGain = this.context.createGain();
        this.silentGain.gain.value = 0;
        this.fallbackProcessor.connect(this.silentGain);
        this.silentGain.connect(this.context.destination);
    }

    _toPcm16(float32) {
        const pcm16 = new Int16Array(float32.length);
        for (let i = 0; i < float32.length; i++) {
            const clamped = Math.max(-1, Math.min(1, float32[i]));
            pcm16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff;
        }
        return pcm16.buffer;
    }

    /** Returns true when the mic is live after the toggle. */
    toggleMute() {
        if (!this.stream) return false;
        this.isMuted = !this.isMuted;
        this.stream.getAudioTracks().forEach((track) => {
            track.enabled = !this.isMuted;
        });
        return !this.isMuted;
    }

    stop() {
        if (this.stream) {
            this.stream.getTracks().forEach((track) => track.stop());
            this.stream = null;
        }
        if (this.workletNode) {
            this.workletNode.port.onmessage = null;
            this.workletNode.disconnect();
            this.workletNode = null;
        }
        if (this.fallbackProcessor) {
            this.fallbackProcessor.onaudioprocess = null;
            this.fallbackProcessor.disconnect();
            this.fallbackProcessor = null;
        }
        if (this.silentGain) {
            this.silentGain.disconnect();
            this.silentGain = null;
        }
        if (this.source) {
            this.source.disconnect();
            this.source = null;
        }
    }
}

window.AudioRecorder = AudioRecorder;
