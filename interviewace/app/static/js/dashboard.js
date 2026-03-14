/**
 * dashboard.js — Live Performance Dashboard
 * Updates score bars and values in real-time from tool call data.
 * Scores are updated silently during the interview.
 */

class Dashboard {
    constructor() {
        this.scores = { confidence: 0, clarity: 0, body_language: 0, content: 0 };
        this.history = [];
    }

    updateScores(data) {
        const { confidence, clarity, body_language, content } = data;

        this.scores = { confidence, clarity, body_language, content };
        this.history.push({ ...this.scores, timestamp: Date.now() });

        const overall = Math.round((confidence + clarity + body_language + content) / 4);

        // Update bars with animation
        this._animateBar('barConfidence', 'valConfidence', confidence);
        this._animateBar('barClarity', 'valClarity', clarity);
        this._animateBar('barBody', 'valBody', body_language);
        this._animateBar('barContent', 'valContent', content);

        // Update overall score
        const scoreEl = document.getElementById('overallScore');
        scoreEl.textContent = overall;
        scoreEl.style.color = this._getScoreColor(overall);

        // Update trend
        const trendEl = document.getElementById('overallTrend');
        if (this.history.length > 1) {
            const prev = this.history[this.history.length - 2];
            const prevOverall = Math.round((prev.confidence + prev.clarity + prev.body_language + prev.content) / 4);
            const diff = overall - prevOverall;
            if (diff > 0) {
                trendEl.textContent = `↑ +${diff}`;
                trendEl.className = 'trend-badge trend-up';
            } else if (diff < 0) {
                trendEl.textContent = `↓ ${diff}`;
                trendEl.className = 'trend-badge trend-down';
            } else {
                trendEl.textContent = `→ 0`;
                trendEl.className = 'trend-badge trend-same';
            }
        }
    }

    _animateBar(barId, valId, value) {
        const bar = document.getElementById(barId);
        const val = document.getElementById(valId);
        if (bar) {
            bar.style.width = `${value}%`;
            bar.style.backgroundColor = this._getScoreColor(value);
        }
        if (val) val.textContent = value;
    }

    _getScoreColor(score) {
        if (score >= 80) return '#00e676';      // Green - excellent
        if (score >= 60) return '#ffab40';      // Orange - good
        if (score >= 40) return '#ff9100';      // Deep orange - developing
        return '#ff5252';                        // Red - needs work
    }
}

window.Dashboard = Dashboard;
