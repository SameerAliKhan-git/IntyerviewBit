/**
 * dashboard.js
 * Handles real-time UI updates for the analytics dashboard
 */

class Dashboard {
    constructor() {
        this.cacheDOM();
        this.scoreHistory = [];
        this.currentOverallScore = 0;
        this.questionsAnswered = 0;

        // Start session duration timer
        this.sessionStartTime = Date.now();
        this.durationIntervalId = setInterval(() => this.updateDuration(), 1000);
    }

    updateDuration() {
        const elapsedMs = Date.now() - this.sessionStartTime;
        const totalSeconds = Math.floor(elapsedMs / 1000);
        const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
        const seconds = String(totalSeconds % 60).padStart(2, '0');
        if (this.statDuration) {
            this.statDuration.textContent = `${minutes}:${seconds}`;
        }
    }

    destroy() {
        if (this.durationIntervalId) {
            clearInterval(this.durationIntervalId);
            this.durationIntervalId = null;
        }
    }

    cacheDOM() {
        // Overall Score
        this.scoreOverall = document.getElementById('scoreOverall');
        this.trendOverall = document.getElementById('trendOverall');
        
        // Metrics Bars
        this.bars = {
            confidence: document.getElementById('barConfidence'),
            clarity: document.getElementById('barClarity'),
            body: document.getElementById('barBody'),
            content: document.getElementById('barContent')
        };
        
        // Metrics Values
        this.vals = {
            confidence: document.getElementById('valConfidence'),
            clarity: document.getElementById('valClarity'),
            body: document.getElementById('valBody'),
            content: document.getElementById('valContent')
        };
        
        // Stats
        this.statQuestions = document.getElementById('statQuestions');
        this.statDuration = document.getElementById('statDuration');
        
        // Feedback Panel
        this.sectionStrengths = document.getElementById('sectionStrengths');
        this.textStrengths = document.getElementById('textStrengths');
        this.sectionImprovements = document.getElementById('sectionImprovements');
        this.textImprovements = document.getElementById('textImprovements');
        this.feedbackPlaceholder = document.querySelector('.placeholder-text');
    }

    /**
     * Updates the main dashboard with new scores from the agent
     * @param {Object} data Score data payload
     */
    updateScores(data) {
        console.log("📊 Updating dashboard scores:", data);
        
        // Update Individual Metrics
        this.updateMetric('confidence', data.confidence_score);
        this.updateMetric('clarity', data.clarity_score);
        this.updateMetric('body', data.body_language_score);
        this.updateMetric('content', data.content_score);

        // Update Overall Score (Average)
        const newOverall = Math.round(
            (data.confidence_score * 0.25) + 
            (data.clarity_score * 0.25) + 
            (data.body_language_score * 0.25) + 
            (data.content_score * 0.25)
        );

        // Handle Trend
        let trendIndicator = '↑ 0%';
        let trendClass = 'up';
        
        if (this.currentOverallScore > 0) {
            const diff = newOverall - this.currentOverallScore;
            if (diff > 0) {
                trendIndicator = `↑ ${diff}%`;
                trendClass = 'up';
            } else if (diff < 0) {
                trendIndicator = `↓ ${Math.abs(diff)}%`;
                trendClass = 'down';
            } else {
                trendIndicator = '→ 0%';
                trendClass = 'up'; // neutral green
            }
        }
        
        this.currentOverallScore = newOverall;
        this.scoreHistory.push(newOverall);
        
        this.scoreOverall.innerHTML = `${newOverall}<span>/100</span>`;
        this.trendOverall.textContent = trendIndicator;
        this.trendOverall.className = `trend ${trendClass}`;

        // Update Feedback Text
        if (data.strengths || data.improvements) {
            this.updateFeedback(data.strengths, data.improvements);
        }

        // Increment Question Count
        this.questionsAnswered++;
        this.statQuestions.textContent = this.questionsAnswered;
    }

    updateMetric(key, value) {
        if (value === undefined || value === null) return;
        
        const safeVal = Math.max(0, Math.min(100, Math.round(value)));
        
        // Update text
        this.vals[key].textContent = `${safeVal}%`;
        
        // Update bar width
        const bar = this.bars[key];
        bar.style.width = `${safeVal}%`;
        
        // Update color
        bar.className = 'progress-fill'; // reset
        if (safeVal >= 80) bar.classList.add('fill-excellent');
        else if (safeVal >= 60) bar.classList.add('fill-good');
        else if (safeVal >= 40) bar.classList.add('fill-average');
        else bar.classList.add('fill-poor');
    }

    updateFeedback(strengths, improvements) {
        if (this.feedbackPlaceholder) {
            this.feedbackPlaceholder.style.display = 'none';
        }
        
        if (strengths) {
            this.sectionStrengths.classList.remove('d-none');
            this.textStrengths.textContent = strengths;
        }
        
        if (improvements) {
            this.sectionImprovements.classList.remove('d-none');
            this.textImprovements.textContent = improvements;
        }
    }
}

// Export for app.js
window.Dashboard = Dashboard;
