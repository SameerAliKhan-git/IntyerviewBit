/**
 * audio-player.js
 * Wrapper for Web Audio API to play base64-encoded PCM audio.
 * Adapted from Google ADK bidi-demo.
 */

class AudioPlayer {
    constructor(audioContext) {
        this.context = audioContext;
        this.processor = null;
        this.isPlaying = false;
        this.playbackSpeed = 1.0;
        this.initPromise = this.initWorklet();
    }

    async initWorklet() {
        try {
            await this.context.audioWorklet.addModule('/static/js/pcm-player-processor.js');
            this.processor = new AudioWorkletNode(this.context, 'pcm-player-processor');
            this.processor.connect(this.context.destination);
            console.log("🔊 Audio player initialized");
        } catch (e) {
            console.error("Error initializing audio player worklet:", e);
        }
    }

    async playBase64(base64Data) {
        await this.initPromise; // Wait for initialization if needed
        
        if (this.context.state === 'suspended') {
            await this.context.resume();
        }

        try {
            const binaryString = window.atob(base64Data);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            
            // Expected audio format from gemini native is 24kHz PCM
            // The Float32 conversion handles playback
            const float32Data = this.int16ToFloat32(new Int16Array(bytes.buffer));
            
            // Adjust speech speed using naive interpolation
            let finalData = float32Data;
            if (this.playbackSpeed && this.playbackSpeed !== 1.0) {
                const speed = this.playbackSpeed;
                const newLen = Math.floor(float32Data.length / speed);
                finalData = new Float32Array(newLen);
                for (let i = 0; i < newLen; i++) {
                    finalData[i] = float32Data[Math.floor(i * speed)];
                }
            }
            
            if (this.processor) {
                this.processor.port.postMessage(finalData);
                this.isPlaying = true;
            }
        } catch (e) {
            console.error("Error playing audio chunk:", e);
        }
    }

    stop() {
        if (this.processor) {
            // Send empty buffer to flush
            this.processor.port.postMessage(new Float32Array(0));
            this.isPlaying = false;
        }
    }

    int16ToFloat32(buffer) {
        let l = buffer.length;
        const buf = new Float32Array(l);
        while (l--) {
            buf[l] = buffer[l] / 0x7FFF;
        }
        return buf;
    }
}

window.AudioPlayer = AudioPlayer;
