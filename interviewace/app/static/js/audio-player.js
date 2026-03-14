/**
 * audio-player.js — Plays back PCM audio received from the Gemini Live agent.
 * Receives base64-encoded PCM audio chunks and plays them through the speakers.
 */

class AudioPlayer {
    constructor(audioContext) {
        this.context = audioContext;
        this.queue = [];
        this.isPlaying = false;
        this.currentSource = null;
    }

    /**
     * Play a base64-encoded PCM audio chunk from the agent.
     * The Gemini Live API returns audio as base64 PCM 24kHz mono.
     */
    playBase64(base64Data) {
        try {
            const binaryString = atob(base64Data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // Convert PCM Int16 to Float32 for Web Audio
            const int16 = new Int16Array(bytes.buffer);
            const float32 = new Float32Array(int16.length);
            for (let i = 0; i < int16.length; i++) {
                float32[i] = int16[i] / 32768.0;
            }

            // The Gemini native audio output is 24kHz
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
        source.connect(this.context.destination);
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
