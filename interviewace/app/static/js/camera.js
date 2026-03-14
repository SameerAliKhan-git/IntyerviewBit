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
        
        // Target 1 frame per second for body language analysis
        this.frameIntervalMs = 1000; 
        this.frameIntervalId = null;
        this.onFrameCaptured = null; // Callback for app.js
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
