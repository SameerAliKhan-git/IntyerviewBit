/**
 * audio-player.js — Plays back PCM audio received from the Gemini Live agent.
 * Exposes AnalyserNode for visualization and uses AudioWorklet for flawless playback.
 */

class AudioPlayer {
    constructor(audioContext) {
        this.context = audioContext;
        this.isPlaying = false;
        this.processor = null;
        
        // Custom Google Meet Visualizer Analyser
        this.analyser = this.context.createAnalyser();
        this.analyser.fftSize = 256;

        this.initPromise = this.initWorklet();
    }

    async initWorklet() {
        try {
            await this.context.audioWorklet.addModule('/static/js/pcm-player-processor.js');
            this.processor = new window.AudioWorkletNode(this.context, 'pcm-player-processor');
            
            // Connect Worklet -> Analyser -> Speakers
            this.processor.connect(this.analyser);
            this.analyser.connect(this.context.destination);
            
            console.log("🔊 3-Tier Audio Worklet initialized properly");
        } catch (e) {
            console.error("Error initializing audio player worklet:", e);
        }
    }

    getAnalyser() {
        return this.analyser;
    }

    async playBase64(base64Data) {
        await this.initPromise; 
        
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
            const float32Data = this.int16ToFloat32(new Int16Array(bytes.buffer));
            
            if (this.processor) {
                this.processor.port.postMessage(float32Data);
                this.isPlaying = true;
            }
        } catch (e) {
            console.error("Error playing audio chunk:", e);
        }
    }

    stop() {
        if (this.processor) {
            // Send empty buffer to flush/kill current audio chunk
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
