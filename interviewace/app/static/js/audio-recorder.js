/**
 * audio-recorder.js — Captures microphone audio, converts to raw PCM Int16, and provides AnalyserNode.
 */

class AudioRecorder {
    constructor(audioContext) {
        this.context = audioContext;
        this.stream = null;
        this.processor = null;
        this.source = null;
        this.isMuted = false;
        
        this.analyser = this.context.createAnalyser();
        this.analyser.fftSize = 256;
    }

    getAnalyser() {
        return this.analyser;
    }

    async start(onData) {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                }
            });

            this.source = this.context.createMediaStreamSource(this.stream);
            
            // Connect to visualizer analyser
            this.source.connect(this.analyser);

            this.processor = this.context.createScriptProcessor(4096, 1, 1);
            
            this.processor.onaudioprocess = (e) => {
                if (this.isMuted) return;

                const inputData = e.inputBuffer.getChannelData(0);
                // Convert Float32 to Int16 PCM payload
                const pcm16 = new Int16Array(inputData.length);
                for (let i = 0; i < inputData.length; i++) {
                    let s = Math.max(-1, Math.min(1, inputData[i]));
                    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }

                // Create the exact JSON format that ADK expects for realtime audio
                const realtimeMedia = {
                    realtimeInput: {
                        mediaChunks: [{
                            mimeType: "audio/pcm;rate=16000",
                            data: this._arrayBufferToBase64(pcm16.buffer)
                        }]
                    }
                };

                // In the bidi-demo, the frontend sends raw buffers, but ADK websocket endpoint expects JSON 
                // Wait, in my previous app.js, I was sending raw bytes `ws.send(pcmBytes)`. But ADK technically supports either if parsing is right.
                // Actually, the main.py `websocket_endpoint` uses `runner.run_live()` which expects the official client Bidi stream format if raw bytes are sent.
                // Let's stick to what worked before: raw bytes. The downstream sends JSON.
                onData(pcm16.buffer); // sending bytebuffer directly
            };

            this.source.connect(this.processor);
            this.processor.connect(this.context.destination);

        } catch (error) {
            console.error("Microphone error:", error);
            throw error;
        }
    }

    toggleMute() {
        if (!this.stream) return false;
        this.isMuted = !this.isMuted;
        this.stream.getAudioTracks().forEach(t => t.enabled = !this.isMuted);
        return !this.isMuted; // True if unmuted
    }

    stop() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        if (this.source) {
            this.source.disconnect();
            this.source = null;
        }
    }

    _arrayBufferToBase64(buffer) {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }
}

window.AudioRecorder = AudioRecorder;
