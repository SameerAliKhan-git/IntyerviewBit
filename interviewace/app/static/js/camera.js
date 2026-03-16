/**
 * camera.js
 * Handles WebRTC camera access, video display, and extracting base64 frames
 */

class CameraManager {
    constructor() {
        this.videoElement = document.getElementById('videoPreview');
        this.canvas = document.createElement('canvas');
        this.ctx = this.canvas.getContext('2d');
        this.stream = null;
        this.isRecording = false;
        
        // Adaptive frame rate based on bandwidth/connection
        this.frameIntervalMs = 1000; // Default 1 fps
        this.frameIntervalId = null;
        this.onFrameCaptured = null; // Callback for app.js
        this.bandwidthCheckInterval = null;
        this.lowBandwidthMode = false;
    }

    async start() {
        try {
            console.log("📷 Requesting camera access...");
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: "user"
                },
                audio: false // Handled separately by audio-recorder.js
            });
            
            this.videoElement.srcObject = this.stream;
            
            // Wait for video metadata to set canvas size
            await new Promise(resolve => {
                this.videoElement.onloadedmetadata = () => {
                    this.canvas.width = this.videoElement.videoWidth;
                    this.canvas.height = this.videoElement.videoHeight;
                    resolve();
                };
            });
            
            // Start bandwidth monitoring
            this.startBandwidthMonitoring();
            
            console.log("📷 Camera started successfully");
            return true;
        } catch (error) {
            console.error("❌ Camera error:", error);
            return false;
        }
    }

    stop() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
            if (this.videoElement) this.videoElement.srcObject = null;
        }
        this.stopFrameExtraction();
        this.stopBandwidthMonitoring();
    }

    startBandwidthMonitoring() {
        // Check connection every 30 seconds
        this.bandwidthCheckInterval = setInterval(() => {
            this.checkBandwidthAndAdapt();
        }, 30000);
    }

    stopBandwidthMonitoring() {
        if (this.bandwidthCheckInterval) {
            clearInterval(this.bandwidthCheckInterval);
            this.bandwidthCheckInterval = null;
        }
    }

    async checkBandwidthAndAdapt() {
        try {
            // Simple bandwidth estimation using navigator.connection if available
            const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
            
            if (connection) {
                const effectiveType = connection.effectiveType; // 'slow-2g', '2g', '3g', '4g'
                const downlink = connection.downlink; // Mbps
                
                // Adapt frame rate based on connection
                if (effectiveType === 'slow-2g' || effectiveType === '2g' || downlink < 1) {
                    if (!this.lowBandwidthMode) {
                        this.lowBandwidthMode = true;
                        this.frameIntervalMs = 3000; // 0.33 fps
                        console.log("📶 Low bandwidth detected, reducing frame rate to 0.33 fps");
                        this.restartFrameExtraction();
                    }
                } else if (effectiveType === '3g' || downlink < 5) {
                    if (!this.lowBandwidthMode) {
                        this.lowBandwidthMode = true;
                        this.frameIntervalMs = 2000; // 0.5 fps
                        console.log("📶 Moderate bandwidth, reducing frame rate to 0.5 fps");
                        this.restartFrameExtraction();
                    }
                } else {
                    if (this.lowBandwidthMode) {
                        this.lowBandwidthMode = false;
                        this.frameIntervalMs = 1000; // 1 fps
                        console.log("📶 Good bandwidth, using normal 1 fps");
                        this.restartFrameExtraction();
                    }
                }
            }
        } catch (error) {
            console.warn("Bandwidth check failed:", error);
        }
    }

    restartFrameExtraction() {
        if (this.isRecording) {
            this.stopFrameExtraction();
            this.startFrameExtraction(this.onFrameCaptured);
        }
    }

    startFrameExtraction(callback) {
        this.onFrameCaptured = callback;
        if (!this.stream) return;
        
        this.isRecording = true;
        
        this.frameIntervalId = setInterval(() => {
            if (this.isRecording) this.captureAndConvertFrame();
        }, this.frameIntervalMs);
    }

    stopFrameExtraction() {
        this.isRecording = false;
        if (this.frameIntervalId) {
            clearInterval(this.frameIntervalId);
            this.frameIntervalId = null;
        }
    }

    captureAndConvertFrame() {
        if (!this.videoElement || !this.videoElement.videoWidth) return;
        
        // Draw video frame to canvas
        this.ctx.drawImage(this.videoElement, 0, 0, this.canvas.width, this.canvas.height);
        
        // Convert to base64 JPEG (lower quality to save bandwidth)
        const frameDataUrl = this.canvas.toDataURL('image/jpeg', 0.6);
        const base64Data = frameDataUrl.split(',')[1];
        
        if (this.onFrameCaptured && base64Data) {
            this.onFrameCaptured(base64Data);
        }
    }

    toggle() {
        if (!this.stream) return false;
        const videoTrack = this.stream.getVideoTracks()[0];
        if (videoTrack) {
            videoTrack.enabled = !videoTrack.enabled;
            return videoTrack.enabled; // Return new state
        }
        return false;
    }
}

// Export for app.js
window.CameraManager = CameraManager;
