/**
 * audio-recorder.js
 * Wrapper for Web Audio API to record PCM audio from the microphone.
 * Sends RAW BINARY PCM bytes over WebSocket (matching ADK bidi-demo pattern).
 */

class AudioRecorder {
    constructor(audioContext) {
        this.context = audioContext;
        this.stream = null;
        this.source = null;
        this.processor = null;
        this.isRecording = false;
        this.isMuted = false;
    }

    async start(onDataCallback) {
        try {
            console.log("🎤 Requesting microphone access...");
            this.stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });
            console.log("🎤 Microphone access granted");

            if (this.context.state === 'suspended') {
                await this.context.resume();
            }

            this.source = this.context.createMediaStreamSource(this.stream);

            await this.context.audioWorklet.addModule('/static/js/pcm-recorder-processor.js');
            this.processor = new AudioWorkletNode(this.context, 'pcm-recorder-processor');

            this.processor.port.onmessage = (e) => {
                if (this.isRecording && !this.isMuted && onDataCallback && e.data) {
                    // Convert Float32Array to Int16Array then to raw bytes
                    const pcmInt16 = this.float32ToInt16(e.data);
                    // Send as raw ArrayBuffer binary — this is what the ADK bidi-demo expects
                    onDataCallback(pcmInt16.buffer);
                }
            };

            this.source.connect(this.processor);
            this.processor.connect(this.context.destination);

            this.isRecording = true;
            return true;
        } catch (error) {
            console.error('Error starting audio recorder:', error);
            return false;
        }
    }

    stop() {
        this.isRecording = false;
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        if (this.source) {
            this.source.disconnect();
            this.source = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
    }

    toggleMute() {
        this.isMuted = !this.isMuted;
        return !this.isMuted; // return new state (true = recording, false = muted)
    }

    float32ToInt16(buffer) {
        let l = buffer.length;
        const buf = new Int16Array(l);
        while (l--) {
            buf[l] = Math.min(1, buffer[l]) * 0x7FFF;
        }
        return buf;
    }
}

window.AudioRecorder = AudioRecorder;
