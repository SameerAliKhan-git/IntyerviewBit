/**
 * pcm-recorder-processor.js
 * AudioWorkletProcessor to capture mic audio as raw PCM.
 */

class PcmRecorderProcessor extends AudioWorkletProcessor {
    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input.length > 0) {
            const channelData = input[0];
            // Post the Float32Array block to the main thread
            this.port.postMessage(channelData);
        }
        return true;
    }
}

registerProcessor('pcm-recorder-processor', PcmRecorderProcessor);
