// Global state for analysis history
const analysisHistory = [];

// Form submission handler
document.getElementById('analyzeForm').addEventListener('submit', async function(e) {
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

        const response = await fetch('/analyze', {
            method: 'POST',
            body: formData,
        });

        const data = await response.json();

        if (response.ok) {
            updateUI(data);
            addToHistory(textContent, data);
        } else {
            alert('Error: ' + (data.error || 'Something went wrong'));
            showIdleState();
        }

    } catch (error) {
        console.error('Error:', error);
        alert('Failed to connect to the server.');
        showIdleState();
    }
});

// Show analyzing state
function showAnalyzingState() {
    document.getElementById('idleState').style.display = 'none';
    document.getElementById('analyzingState').style.display = 'block';
    document.getElementById('safeState').style.display = 'none';
    document.getElementById('riskState').style.display = 'none';
    
    document.getElementById('resultsEmpty').style.display = 'none';
    document.getElementById('resultsContent').classList.remove('active');
    
    document.getElementById('analyzeBtn').disabled = true;
}

// Show idle state
function showIdleState() {
    document.getElementById('idleState').style.display = 'block';
    document.getElementById('analyzingState').style.display = 'none';
    document.getElementById('safeState').style.display = 'none';
    document.getElementById('riskState').style.display = 'none';
    
    document.getElementById('resultsEmpty').style.display = 'block';
    document.getElementById('resultsContent').classList.remove('active');
    
    document.getElementById('analyzeBtn').disabled = false;
}

// Show analysis state
function updateUI(data) {
    const score = data.toxicity_score || 0;
    const severity = data.severity_level || 'Unknown';
    
    // Update Gauge
    const needle = document.getElementById('gaugeNeedle');
    if (needle) {
        const rotation = (score * 1.8) - 90;
        needle.style.transform = `translateX(-50%) rotate(${rotation}deg)`;
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

    document.getElementById('resultsEmpty').style.display = 'none';
    document.getElementById('resultsContent').classList.add('active');
    document.getElementById('analyzeBtn').disabled = false;
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
window.addEventListener('DOMContentLoaded', function() {
    showIdleState();
});
