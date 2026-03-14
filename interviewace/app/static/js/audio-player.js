/**
 * audio-player.js — Plays back PCM audio received from the Gemini Live agent.
 * Exposes AnalyserNode for visualization.
 */

class AudioPlayer {
    constructor(audioContext) {
        this.context = audioContext;
        this.queue = [];
        this.isPlaying = false;
        this.currentSource = null;
        
        // Add analyser for visualizer
        this.analyser = this.context.createAnalyser();
        this.analyser.fftSize = 256;
        this.analyser.connect(this.context.destination);
    }

    getAnalyser() {
        return this.analyser;
    }

    playBase64(base64Data) {
        try {
            const binaryString = atob(base64Data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            const int16 = new Int16Array(bytes.buffer);
            const float32 = new Float32Array(int16.length);
            for (let i = 0; i < int16.length; i++) {
                float32[i] = int16[i] / 32768.0;
            }

            const sampleRate = 24000;
            const audioBuffer = this.context.createBuffer(1, float32.length, sampleRate);
            audioBuffer.getChannelData(0).set(float32);

            this.queue.push(audioBuffer);
            if (!this.isPlaying) {
                this._playNext();
            }
        } catch (e) {
            console.error("Audio playback error:", e);
        }
    }

    _playNext() {
        if (this.queue.length === 0) {
            this.isPlaying = false;
            return;
        }

        this.isPlaying = true;
        const buffer = this.queue.shift();
        const source = this.context.createBufferSource();
        source.buffer = buffer;
        
        // Connect source to analyser (which is connected to destination)
        source.connect(this.analyser);
        
        source.onended = () => this._playNext();
        source.start(0);
        this.currentSource = source;
    }

    stop() {
        this.queue = [];
        this.isPlaying = false;
        if (this.currentSource) {
            try { this.currentSource.stop(); } catch (e) {}
            this.currentSource = null;
        }
    }
}

window.AudioPlayer = AudioPlayer;
