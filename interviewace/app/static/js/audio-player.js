/**
 * audio-player.js — Plays back PCM audio received from the Gemini Live agent.
 *
 * Barge-in correctness: every scheduled AudioBufferSourceNode is tracked, because
 * stopping playback has to actually stop the buffers that are already queued. Resetting
 * only the scheduling cursor lets the agent keep talking over the candidate for the
 * whole length of the buffered audio.
 */

const GEMINI_OUTPUT_SAMPLE_RATE = 24000;

class AudioPlayer {
    constructor(audioContext) {
        this.context = audioContext;
        this.nextPlayTime = 0;
        this.sources = new Set();

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
            // Gemini may use base64url; atob only accepts standard base64.
            let standardB64 = base64Data.replace(/-/g, '+').replace(/_/g, '/');
            while (standardB64.length % 4) {
                standardB64 += '=';
            }

            const binaryString = window.atob(standardB64);
            const rawLen = binaryString.length;
            // Live API chunks can split mid-sample; an odd byte count would throw when
            // viewed as Int16.
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

            const audioBuffer = this.context.createBuffer(
                1,
                float32.length,
                GEMINI_OUTPUT_SAMPLE_RATE,
            );
            audioBuffer.getChannelData(0).set(float32);

            const source = this.context.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(this.analyser);

            this.sources.add(source);
            source.onended = () => this.sources.delete(source);

            // Sequential gapless scheduling with a small cushion against underrun.
            const currentTime = this.context.currentTime;
            if (this.nextPlayTime < currentTime) {
                this.nextPlayTime = currentTime + 0.05;
            }

            source.start(this.nextPlayTime);
            this.nextPlayTime += audioBuffer.duration;
        } catch (error) {
            console.error('Audio chunk playback skipped due to parse error:', error);
        }
    }

    /** Immediately silences the agent — used on barge-in and when the call ends. */
    stop() {
        for (const source of this.sources) {
            try {
                source.onended = null;
                source.stop();
                source.disconnect();
            } catch (error) {
                // Already stopped or never started; nothing to do.
            }
        }
        this.sources.clear();
        this.nextPlayTime = this.context.currentTime;
    }
}

window.AudioPlayer = AudioPlayer;
