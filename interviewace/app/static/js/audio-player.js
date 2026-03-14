/**
 * audio-player.js — Plays back PCM audio received from the Gemini Live agent.
 */

class AudioPlayer {
    constructor(audioContext) {
        this.context = audioContext;
        this.nextPlayTime = 0;
        
        // Add analyser for visualizer rings
        this.analyser = this.context.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.connect(this.context.destination);
    }

    getAnalyser() {
        return this.analyser;
    }

    playBase64(base64Data) {
        if (!base64Data) return;
        try {
            // Google Gemini sends Base64Url encoded strings. window.atob requires standard Base64.
            let standardB64 = base64Data.replace(/-/g, '+').replace(/_/g, '/');
            // Pad to multiple of 4
            while (standardB64.length % 4) {
                standardB64 += '=';
            }

            const binaryString = window.atob(standardB64);
            const rawLen = binaryString.length;
            // CRITICAL: Live API streams can chunk randomly. 
            // If bytes are odd, Int16Array will crash the entire player!
            const len = rawLen % 2 === 0 ? rawLen : rawLen - 1; 
            
            if (len === 0) return;

            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            const int16 = new Int16Array(bytes.buffer);
            const float32 = new Float32Array(int16.length);
            for (let i = 0; i < int16.length; i++) {
                float32[i] = int16[i] / 32768.0;
            }

            // Gemini Native Audio is perfectly 24000Hz
            // The browser will natively resample this to 16000Hz output to match the microphone!
            const sampleRate = 24000;
            const audioBuffer = this.context.createBuffer(1, float32.length, sampleRate);
            audioBuffer.getChannelData(0).set(float32);

            const source = this.context.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.analyser);
            
            // Sequential gapless playback scheduling
            const currentTime = this.context.currentTime;
            if (this.nextPlayTime < currentTime) {
                // Buffer by 50ms to prevent micro-stutter drops
                this.nextPlayTime = currentTime + 0.05; 
            }
            
            source.start(this.nextPlayTime);
            this.nextPlayTime += audioBuffer.duration;
            
        } catch (e) {
            console.error("Audio chunk playback skipped due to parse error:", e);
        }
    }

    stop() {
        this.nextPlayTime = this.context.currentTime;
    }
}

window.AudioPlayer = AudioPlayer;
