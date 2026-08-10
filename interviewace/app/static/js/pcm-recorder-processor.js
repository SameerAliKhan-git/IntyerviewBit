/**
 * pcm-recorder-processor.js
 * AudioWorkletProcessor that captures mic audio and posts it in fixed-size blocks.
 *
 * The render quantum is only 128 frames, which would mean ~125 messages per second per
 * channel. Blocks are accumulated to CHUNK_SIZE (128 ms at 16 kHz) before being posted,
 * which keeps latency low without flooding the main thread or the socket.
 */

const CHUNK_SIZE = 2048;

class PcmRecorderProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._buffer = new Float32Array(CHUNK_SIZE);
        this._offset = 0;
    }

    process(inputs) {
        const input = inputs[0];
        if (!input || input.length === 0) {
            return true;
        }

        const channel = input[0];
        if (!channel) {
            return true;
        }

        for (let i = 0; i < channel.length; i++) {
            this._buffer[this._offset++] = channel[i];

            if (this._offset === CHUNK_SIZE) {
                // Transfer a copy so the worklet can keep filling its own buffer.
                const chunk = this._buffer.slice(0);
                this.port.postMessage(chunk, [chunk.buffer]);
                this._offset = 0;
            }
        }

        return true;
    }
}

registerProcessor('pcm-recorder-processor', PcmRecorderProcessor);
