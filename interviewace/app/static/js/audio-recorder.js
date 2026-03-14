/**
 * audio-recorder.js
 * Wrapper for Web Audio API to record PCM audio from the microphone.
 * Adapted from Google ADK bidi-demo.
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

            // Load the worklet processor for PCM conversion
            await this.context.audioWorklet.addModule('/static/js/pcm-recorder-processor.js');
            this.processor = new AudioWorkletNode(this.context, 'pcm-recorder-processor');

            this.processor.port.onmessage = (e) => {
                if (this.isRecording && !this.isMuted && onDataCallback && e.data) {
                    // e.data is a Float32Array containing PCM data
                    // Convert Float32Array to Int16Array (PCM 16-bit)
                    const pcmData = this.float32ToInt16(e.data);
                    // Send raw binary ArrayBuffer — backend expects binary WS frames
                    onDataCallback(pcmData.buffer);
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

    arrayBufferToBase64(buffer) {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const len = bytes.byteLength;
        for (let i = 0; i < len; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return window.btoa(binary);
    }
}

window.AudioRecorder = AudioRecorder;
