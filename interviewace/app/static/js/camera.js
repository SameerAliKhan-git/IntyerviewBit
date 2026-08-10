/**
 * camera.js
 * Webcam access, preview, and periodic JPEG frame extraction for vision analysis.
 */

class CameraManager {
    constructor() {
        this.videoElement = document.getElementById('videoPreview');
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.stream = null;
        this.isCapturing = false;

        this.frameIntervalMs = 1000; // 1 fps by default
        this.frameIntervalId = null;
        this.onFrameCaptured = null;
        this.bandwidthCheckInterval = null;
        this.currentTier = 'normal';
    }

    async start() {
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user',
                },
                audio: false, // handled separately by audio-recorder.js
            });

            this.videoElement.srcObject = this.stream;

            await new Promise((resolve) => {
                if (this.videoElement.readyState >= 1) {
                    resolve();
                    return;
                }
                this.videoElement.onloadedmetadata = () => resolve();
            });

            this.canvas.width = this.videoElement.videoWidth || 640;
            this.canvas.height = this.videoElement.videoHeight || 480;

            this.startBandwidthMonitoring();
            return true;
        } catch (error) {
            console.error('Camera error:', error);
            return false;
        }
    }

    stop() {
        if (this.stream) {
            this.stream.getTracks().forEach((track) => track.stop());
            this.stream = null;
            if (this.videoElement) this.videoElement.srcObject = null;
        }
        this.stopFrameExtraction();
        this.stopBandwidthMonitoring();
    }

    startBandwidthMonitoring() {
        this.bandwidthCheckInterval = setInterval(() => this.adaptToBandwidth(), 30000);
    }

    stopBandwidthMonitoring() {
        if (this.bandwidthCheckInterval) {
            clearInterval(this.bandwidthCheckInterval);
            this.bandwidthCheckInterval = null;
        }
    }

    adaptToBandwidth() {
        const connection =
            navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        if (!connection) return;

        const effectiveType = connection.effectiveType;
        const downlink = connection.downlink;

        let tier = 'normal';
        let interval = 1000;
        if (effectiveType === 'slow-2g' || effectiveType === '2g' || downlink < 1) {
            tier = 'low';
            interval = 3000;
        } else if (effectiveType === '3g' || downlink < 5) {
            tier = 'moderate';
            interval = 2000;
        }

        // Only restart the timer when the tier actually changes. The previous version
        // latched a boolean, so it could never step back up from low to moderate.
        if (tier === this.currentTier) return;
        this.currentTier = tier;
        this.frameIntervalMs = interval;
        if (this.isCapturing) {
            this.stopFrameExtraction();
            this.startFrameExtraction(this.onFrameCaptured);
        }
    }

    startFrameExtraction(callback) {
        if (!this.stream || !callback) return;
        this.onFrameCaptured = callback;
        this.isCapturing = true;
        this.frameIntervalId = setInterval(() => this.captureFrame(), this.frameIntervalMs);
    }

    stopFrameExtraction() {
        this.isCapturing = false;
        if (this.frameIntervalId) {
            clearInterval(this.frameIntervalId);
            this.frameIntervalId = null;
        }
    }

    isEnabled() {
        const track = this.stream && this.stream.getVideoTracks()[0];
        return Boolean(track && track.enabled);
    }

    captureFrame() {
        // Guard against uploading frames the user believes are not being sent. A disabled
        // track still renders (as black), so without this the "camera off" button only
        // changes what the candidate sees, not what leaves the machine.
        if (!this.isCapturing || !this.isEnabled()) return;
        if (!this.videoElement || !this.videoElement.videoWidth) return;

        this.ctx.drawImage(this.videoElement, 0, 0, this.canvas.width, this.canvas.height);
        const base64Data = this.canvas.toDataURL('image/jpeg', 0.6).split(',')[1];
        if (this.onFrameCaptured && base64Data) {
            this.onFrameCaptured(base64Data);
        }
    }

    /** Returns the new enabled state. */
    toggle() {
        const track = this.stream && this.stream.getVideoTracks()[0];
        if (!track) return false;

        track.enabled = !track.enabled;
        if (track.enabled) {
            if (!this.isCapturing) this.startFrameExtraction(this.onFrameCaptured);
        } else {
            this.stopFrameExtraction();
        }
        return track.enabled;
    }
}

window.CameraManager = CameraManager;
