/**
 * pcm-player-processor.js
 * AudioWorkletProcessor to play buffered raw PCM audio.
 */

class PcmPlayerProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = new Float32Array(0);
        
        this.port.onmessage = (e) => {
            const newChunk = e.data;
            if (newChunk.length === 0) {
                 // Flush signal
                 this.buffer = new Float32Array(0);
                 return;
            }
            // Append incoming chunk to existing buffer
            const newBuffer = new Float32Array(this.buffer.length + newChunk.length);
            newBuffer.set(this.buffer);
            newBuffer.set(newChunk, this.buffer.length);
            this.buffer = newBuffer;
        };
    }

    process(inputs, outputs, parameters) {
        const output = outputs[0];
        const channelData = output[0];
        const framesToOutput = channelData.length;

        if (this.buffer.length >= framesToOutput) {
            // Write from buffer to output
            channelData.set(this.buffer.subarray(0, framesToOutput));
            // Shift buffer
            this.buffer = this.buffer.subarray(framesToOutput);
            return true;
        } else {
            // Not enough data in buffer
            if (this.buffer.length > 0) {
                channelData.set(this.buffer);
                this.buffer = new Float32Array(0);
            }
            return true; // Keep processor alive
        }
    }
}

registerProcessor('pcm-player-processor', PcmPlayerProcessor);
