/**
 * dashboard.js
 * Renders live analytics widgets without external charting libraries.
 */

class Dashboard {
    constructor() {
        this.summary = {};
        this.previousSession = this._loadPreviousSession();
        this.elements = {
            connectionStatus: document.getElementById('connectionStatus'),
            networkStatus: document.getElementById('networkStatus'),
            trendChart: document.getElementById('trendChart'),
            radarChart: document.getElementById('radarChart'),
            comparison: document.getElementById('sessionComparison'),
            heatmap: document.getElementById('heatmapGrid'),
            milestones: document.getElementById('milestoneBadges'),
            learningPath: document.getElementById('learningPath'),
            industryCoaching: document.getElementById('industryCoaching'),
            fillerCount: document.getElementById('fillerCount'),
            fillerWords: document.getElementById('fillerWords'),
            fillerTip: document.getElementById('fillerTip'),
        };

        this.renderComparison();
    }

    handleToolResult(name, data) {
        if (!data) return;

        if (name === 'save_session_feedback') {
            this._updateMetric('mConfidence', 'bConfidence', data.confidence);
            this._updateMetric('mClarity', 'bClarity', data.clarity);
            this._updateMetric('mStar', 'bStar', data.star_score);
            this._updateMetric('mBody', 'bBody', data.body_language);
        }

        if (name === 'detect_filler_words') {
            const fillers = data.detected_fillers ? Object.keys(data.detected_fillers).join(', ') : 'None';
            if (this.elements.fillerCount) this.elements.fillerCount.textContent = String(data.total_filler_words || 0);
            if (this.elements.fillerWords) this.elements.fillerWords.textContent = fillers;
            if (this.elements.fillerTip) this.elements.fillerTip.textContent = data.coaching_tip || '';
        }

        if (data.dashboard) {
            this.applyDashboard(data.dashboard);
        }

        if (name === 'generate_session_report') {
            this.summary = { ...this.summary, ...data };
            this.storeSessionSummary();
            this.renderComparison(data);
        }
    }

    applyDashboard(dashboard) {
        if (!dashboard) return;
        this.summary = { ...this.summary, ...dashboard };
        this.renderTrend(dashboard.trend_points || []);
        this.renderRadar(dashboard.competency_radar || {});
        this.renderHeatmap(dashboard.heatmap || []);
        this.renderMilestones(dashboard.milestones || []);
        this.renderLearningPath(dashboard.learning_path || []);
        this.renderIndustryCoaching(dashboard.industry_specific_coaching || []);
    }

    setConnectionStatus(status, label) {
        const el = this.elements.connectionStatus;
        if (!el) return;
        el.textContent = label;
        el.className = `status-pill ${status}`;
    }

    setNetworkStatus(label) {
        const el = this.elements.networkStatus;
        if (!el) return;
        el.textContent = label;
    }

    storeSessionSummary(summary = this.summary) {
        if (!summary) return;
        const snapshot = {
            average_score: summary.average_score || summary.history_snapshot?.average_score || 0,
            confidence: summary.confidence || 0,
            clarity: summary.clarity || 0,
            body_language: summary.body_language || 0,
            content: summary.content || 0,
            star_score: summary.star_score || 0,
            performance_tier: summary.performance_tier || '',
            timestamp: Date.now(),
        };
        try {
            localStorage.setItem('ia_last_scores', JSON.stringify(snapshot));
            this.previousSession = snapshot;
        } catch (error) {
            console.warn('Unable to store session snapshot', error);
        }
    }

    renderComparison(current = this.summary) {
        const el = this.elements.comparison;
        if (!el) return;

        if (!this.previousSession || !current || !current.average_score) {
            el.innerHTML = '<div class="session-note">Complete a session to compare against your previous run.</div>';
            return;
        }

        const delta = current.average_score - this.previousSession.average_score;
        const trend = delta > 0 ? 'Up' : delta < 0 ? 'Down' : 'Flat';
        el.innerHTML = `
            <div class="comparison-row">
                <div class="comparison-item">
                    <span class="comparison-label">Current</span>
                    <strong>${current.average_score}</strong>
                </div>
                <div class="comparison-item">
                    <span class="comparison-label">Previous</span>
                    <strong>${this.previousSession.average_score}</strong>
                </div>
                <div class="comparison-item">
                    <span class="comparison-label">Trend</span>
                    <strong>${trend} ${delta === 0 ? '' : `${delta > 0 ? '+' : ''}${delta}`}</strong>
                </div>
            </div>
        `;
    }

    renderTrend(points) {
        const svg = this.elements.trendChart;
        if (!svg) return;
        if (!points.length) {
            svg.innerHTML = '<text x="20" y="55" class="chart-placeholder">No score trend yet</text>';
            return;
        }

        const width = 260;
        const height = 110;
        const padding = 16;
        const maxScore = Math.max(100, ...points.map(point => point.overall));
        const step = points.length > 1 ? (width - padding * 2) / (points.length - 1) : 0;

        const coords = points.map((point, index) => {
            const x = padding + step * index;
            const y = height - padding - ((point.overall / maxScore) * (height - padding * 2));
            return `${x},${y}`;
        }).join(' ');

        svg.innerHTML = `
            <line x1="${padding}" y1="${height - padding}" x2="${width - padding}" y2="${height - padding}" class="chart-axis"></line>
            <polyline points="${coords}" class="trend-line"></polyline>
            ${points.map((point, index) => {
                const x = padding + step * index;
                const y = height - padding - ((point.overall / maxScore) * (height - padding * 2));
                return `<circle cx="${x}" cy="${y}" r="4" class="trend-point"></circle>`;
            }).join('')}
        `;
    }

    renderRadar(radar) {
        const svg = this.elements.radarChart;
        if (!svg) return;
        const labels = ['confidence', 'clarity', 'body_language', 'content', 'star', 'voice', 'engagement'];
        const centerX = 130;
        const centerY = 110;
        const radius = 70;

        if (!labels.some(label => radar[label])) {
            svg.innerHTML = '<text x="50" y="110" class="chart-placeholder">Radar fills in as scores arrive</text>';
            return;
        }

        const polygon = labels.map((label, index) => {
            const angle = (-Math.PI / 2) + (Math.PI * 2 * index / labels.length);
            const score = (radar[label] || 0) / 100;
            const x = centerX + Math.cos(angle) * radius * score;
            const y = centerY + Math.sin(angle) * radius * score;
            return `${x},${y}`;
        }).join(' ');

        const grid = [0.25, 0.5, 0.75, 1].map(scale => {
            const points = labels.map((_, index) => {
                const angle = (-Math.PI / 2) + (Math.PI * 2 * index / labels.length);
                const x = centerX + Math.cos(angle) * radius * scale;
                const y = centerY + Math.sin(angle) * radius * scale;
                return `${x},${y}`;
            }).join(' ');
            return `<polygon points="${points}" class="radar-grid"></polygon>`;
        }).join('');

        const spokes = labels.map((_, index) => {
            const angle = (-Math.PI / 2) + (Math.PI * 2 * index / labels.length);
            const x = centerX + Math.cos(angle) * radius;
            const y = centerY + Math.sin(angle) * radius;
            return `<line x1="${centerX}" y1="${centerY}" x2="${x}" y2="${y}" class="radar-spoke"></line>`;
        }).join('');

        const text = labels.map((label, index) => {
            const angle = (-Math.PI / 2) + (Math.PI * 2 * index / labels.length);
            const x = centerX + Math.cos(angle) * (radius + 20);
            const y = centerY + Math.sin(angle) * (radius + 20);
            return `<text x="${x}" y="${y}" class="radar-label">${label.replace('_', ' ')}</text>`;
        }).join('');

        svg.innerHTML = `${grid}${spokes}<polygon points="${polygon}" class="radar-area"></polygon>${text}`;
    }

    renderHeatmap(heatmap) {
        const el = this.elements.heatmap;
        if (!el) return;
        if (!heatmap.length) {
            el.innerHTML = '<div class="session-note">Heatmap appears after the first scored answer.</div>';
            return;
        }
        el.innerHTML = heatmap.map(item => `
            <div class="heat-cell ${item.intensity}">
                <strong>Q${item.question_number}</strong>
                <span>${item.focus_area.replace('_', ' ')}</span>
                <em>${item.overall}</em>
            </div>
        `).join('');
    }

    renderMilestones(milestones) {
        const el = this.elements.milestones;
        if (!el) return;
        if (!milestones.length) {
            el.innerHTML = '<span class="session-note">Badges unlock as you practice.</span>';
            return;
        }
        el.innerHTML = milestones.map(item => `
            <span class="mini-pill" title="${item.description}">${item.badge}</span>
        `).join('');
    }

    renderLearningPath(items) {
        const el = this.elements.learningPath;
        if (!el) return;
        if (!items.length) {
            el.innerHTML = '<div class="session-note">Your next drills will appear here.</div>';
            return;
        }
        el.innerHTML = items.map(item => `
            <div class="learning-item">
                <strong>${item.area}</strong>
                <span>${item.goal}</span>
                <em>${item.drill}</em>
            </div>
        `).join('');
    }

    renderIndustryCoaching(items) {
        const el = this.elements.industryCoaching;
        if (!el) return;
        if (!items.length) {
            el.innerHTML = '<div class="session-note">Role-specific tips will appear once the session context is known.</div>';
            return;
        }
        el.innerHTML = items.map(item => `
            <div class="learning-item compact">
                <span>${item}</span>
            </div>
        `).join('');
    }

    _updateMetric(valueId, barId, value) {
        if (value === undefined || value === null) return;
        const valueEl = document.getElementById(valueId);
        const barEl = document.getElementById(barId);
        if (valueEl) valueEl.textContent = value;
        if (barEl) barEl.style.width = `${value}%`;
    }

    _loadPreviousSession() {
        try {
            const raw = localStorage.getItem('ia_last_scores');
            return raw ? JSON.parse(raw) : null;
        } catch (error) {
            console.warn('Unable to read previous session snapshot', error);
            return null;
        }
    }
}

window.Dashboard = Dashboard;
