// Global state for analysis history
const analysisHistory = [];

// Form submission handler
document.addEventListener('DOMContentLoaded', function() {
    const analyzeForm = document.getElementById('analyzeForm');
    if (analyzeForm) {
        analyzeForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const textContent = document.getElementById('text_content').value;
            const imageFile = document.getElementById('image_file').files[0];

            if (!textContent.trim() && !imageFile) {
                alert('Please enter some text or upload an image to analyze.');
                return;
            }

            // Show analyzing state
            showAnalyzingState();

            try {
                const formData = new FormData();
                formData.append('text', textContent);
                if (imageFile) {
                    formData.append('image', imageFile);
                }

                console.log('Sending analysis request...');
                const response = await fetch('/analyze', {
                    method: 'POST',
                    body: formData,
                });

                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.error || 'Server error');
                }

                const data = await response.json();
                console.log('Analysis data received:', data);

                updateUI(data);
                addToHistory(textContent, data);

            } catch (error) {
                console.error('Analysis Error:', error);
                alert('Analysis failed: ' + error.message);
                showIdleState();
            }
        });
    }
    showIdleState();
});

// Show analyzing state
function showAnalyzingState() {
    const idle = document.getElementById('idleState');
    const analyzing = document.getElementById('analyzingState');
    const safe = document.getElementById('safeState');
    const risk = document.getElementById('riskState');
    const empty = document.getElementById('resultsEmpty');
    const content = document.getElementById('resultsContent');
    const btn = document.getElementById('analyzeBtn');

    if (idle) idle.style.display = 'none';
    if (analyzing) analyzing.style.display = 'block';
    if (safe) safe.style.display = 'none';
    if (risk) risk.style.display = 'none';
    if (empty) empty.style.display = 'none';
    if (content) content.classList.remove('active');
    if (btn) btn.disabled = true;
}

// Show idle state
function showIdleState() {
    const idle = document.getElementById('idleState');
    const analyzing = document.getElementById('analyzingState');
    const safe = document.getElementById('safeState');
    const risk = document.getElementById('riskState');
    const empty = document.getElementById('resultsEmpty');
    const content = document.getElementById('resultsContent');
    const btn = document.getElementById('analyzeBtn');

    if (idle) idle.style.display = 'block';
    if (analyzing) analyzing.style.display = 'none';
    if (safe) safe.style.display = 'none';
    if (risk) risk.style.display = 'none';
    if (empty) empty.style.display = 'block';
    if (content) content.classList.remove('active');
    if (btn) btn.disabled = false;
}

// Show analysis state
function updateUI(data) {
    const score = data.toxicity_score || 0;
    const severity = data.severity_level || 'Unknown';
    
    // Update Gauge
    const needle = document.getElementById('gaugeNeedle');
    if (needle) {
        // Map 0-100 score to -90 to 90 degrees
        const rotation = (score * 1.8) - 90;
        needle.style.transform = `translateX(-50%) rotate(${rotation}deg)`;
    }

    // Update risk bar in results
    const riskBar = document.getElementById('riskBar');
    if (riskBar) {
        riskBar.style.width = score + '%';
        // Add color based on score
        if (score > 70) riskBar.style.background = 'var(--risk-color)';
        else if (score > 30) riskBar.style.background = 'var(--warning-color)';
        else riskBar.style.background = 'var(--safe-color)';
    }

    // Update risk section
    const riskScore = document.getElementById('riskScore');
    if (riskScore) riskScore.textContent = score;
    
    const riskStatus = document.getElementById('riskStatus');
    if (riskStatus) {
        riskStatus.textContent = severity;
        riskStatus.className = 'risk-status ' + (score > 60 ? 'risk' : (score > 30 ? 'warning' : 'safe'));
    }

    // Update state display
    const safeState = document.getElementById('safeState');
    const riskState = document.getElementById('riskState');
    const idleState = document.getElementById('idleState');
    const analyzingState = document.getElementById('analyzingState');

    if (idleState) idleState.style.display = 'none';
    if (analyzingState) analyzingState.style.display = 'none';

    if (score > 60) {
        if (safeState) safeState.style.display = 'none';
        if (riskState) riskState.style.display = 'block';
    } else {
        if (safeState) safeState.style.display = 'block';
        if (riskState) riskState.style.display = 'none';
    }

    // Update analysis explanation
    const expText = document.getElementById('explanationText');
    if (expText) expText.textContent = data.explanation || 'Analysis completed.';

    // Render detection labels
    renderLabels(data.detected_labels || {});

    // Update sections
    const victimSection = document.getElementById('victimSupportSection');
    const victimText = document.getElementById('victimSupportText');
    if (data.victim_support_message && victimSection && victimText) {
        victimText.textContent = data.victim_support_message;
        victimSection.style.display = 'block';
    }

    const responsesSection = document.getElementById('safeResponsesSection');
    if (data.safe_response_steps && Array.isArray(data.safe_response_steps) && responsesSection) {
        renderSafeResponses(data.safe_response_steps);
        responsesSection.style.display = 'block';
    }

    const alertInfo = document.getElementById('alertInfo');
    if (alertInfo) alertInfo.style.display = data.parent_alert_required ? 'block' : 'none';

    // Update Dynamic Support Panel
    updateSupportPanel(data.support_panel_content);

    document.getElementById('resultsEmpty').style.display = 'none';
    document.getElementById('resultsContent').classList.add('active');
    document.getElementById('analyzeBtn').disabled = false;
}

function updateSupportPanel(content) {
    if (!content) return;

    const supportSummary = document.getElementById('supportSummary');
    const studentGuidance = document.getElementById('studentGuidance');
    const parentGuidance = document.getElementById('parentGuidance');
    const supportNextSteps = document.getElementById('supportNextSteps');

    if (supportSummary) supportSummary.textContent = content.context_summary || '';
    if (studentGuidance) studentGuidance.textContent = content.student_guidance || '';
    if (parentGuidance) parentGuidance.textContent = content.parent_guidance || '';
    
    if (supportNextSteps && Array.isArray(content.next_steps)) {
        supportNextSteps.innerHTML = content.next_steps.map(step => `
            <div class="support-step">
                <h4>Recommended Action</h4>
                <p>${step}</p>
            </div>
        `).join('');
    }
}

function renderSafeResponses(steps) {
    const list = document.getElementById('safeResponsesList');
    if (!list) return;
    
    list.innerHTML = Array.isArray(steps) ? steps.map(step => `
        <div class="response-item">${step}</div>
    `).join('') : '';
}

function renderLabels(labels) {
    const container = document.getElementById('labelsContainer');
    if (!container) return;
    
    const labelMap = {
        'harassment': 'Harassment',
        'hate_speech': 'Hate Speech',
        'threats': 'Threats',
        'sexual_content': 'Inappropriate',
        'emotional_abuse': 'Emotional Abuse',
        'cyberbullying': 'Cyberbullying'
    };
    
    container.innerHTML = Object.entries(labelMap).map(([key, label]) => {
        const isDetected = labels[key] === true;
        return `
            <div class="label-minimal ${isDetected ? 'detected' : 'safe'}">
                ${isDetected ? '⚠️' : '✓'} ${label}
            </div>
        `;
    }).join('');
}

function showHistoryDetail(explanation) {
    const modal = document.getElementById('reasonModal');
    const text = document.getElementById('modalExplanation');
    if (modal && text) {
        text.textContent = explanation;
        modal.classList.add('active');
    }
}

function closeReasonModal() {
    const modal = document.getElementById('reasonModal');
    if (modal) modal.classList.remove('active');
}

// Update insights panel
function updateInsightsPanel() {
    const panel = document.getElementById('insightsPanel');
    if (!panel) return;
    
    if (analysisHistory.length === 0) {
        return;
    }

    const newHtml = analysisHistory.map(item => `
        <div class="history-item" onclick="showHistoryDetail('${item.explanation.replace(/'/g, "\\'")}')">
            <div class="history-info">
                <span class="history-preview">${item.text}</span>
                <div class="history-meta">
                    <span>${item.time}</span>
                    <span class="severity-badge severity-${item.severity.toLowerCase()}">${item.severity}</span>
                </div>
            </div>
            <div class="history-score">${item.score}%</div>
        </div>
    `).join('');
    
    panel.innerHTML = newHtml + panel.innerHTML;
}

// Add analysis to history
function addToHistory(text, data) {
    const summary = text.substring(0, 40) + (text.length > 40 ? '...' : '');
    const severity = data.severity_level || 'Unknown';
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    analysisHistory.unshift({
        text: summary || 'Image Analysis',
        severity: severity,
        score: data.toxicity_score,
        time: timestamp,
        explanation: data.explanation
    });

    if (analysisHistory.length > 5) analysisHistory.pop();
    updateInsightsPanel();
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    showIdleState();
});
