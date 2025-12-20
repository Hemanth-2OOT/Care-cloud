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
    const isRisk = score > 70;

    // Update risk section
    document.getElementById('riskScore').textContent = score;
    
    const riskStatus = document.getElementById('riskStatus');
    riskStatus.textContent = severity;
    riskStatus.className = 'risk-status ' + (isRisk ? 'risk' : 'safe');

    // Update risk bar color
    const riskBar = document.getElementById('riskBar');
    riskBar.style.width = Math.min(score, 100) + '%';
    
    if (score <= 30) {
        riskBar.style.background = 'linear-gradient(90deg, #10b981, #14b8a6)';
    } else if (score <= 60) {
        riskBar.style.background = 'linear-gradient(90deg, #f59e0b, #ec4899)';
    } else {
        riskBar.style.background = 'linear-gradient(90deg, #ef4444, #dc2626)';
    }

    // Update state display
    if (isRisk) {
        document.getElementById('idleState').style.display = 'none';
        document.getElementById('analyzingState').style.display = 'none';
        document.getElementById('safeState').style.display = 'none';
        document.getElementById('riskState').style.display = 'block';
    } else {
        document.getElementById('idleState').style.display = 'none';
        document.getElementById('analyzingState').style.display = 'none';
        document.getElementById('safeState').style.display = 'block';
        document.getElementById('riskState').style.display = 'none';
    }

    // Update analysis explanation
    document.getElementById('explanationText').textContent = data.explanation || 'Analysis completed.';

    // Render detection labels
    renderLabels(data.detected_labels || {});

    // Show/hide parent alert
    if (data.parent_alert_required) {
        document.getElementById('alertInfo').style.display = 'block';
    } else {
        document.getElementById('alertInfo').style.display = 'none';
    }

    // Show results
    document.getElementById('resultsEmpty').style.display = 'none';
    document.getElementById('resultsContent').classList.add('active');
    
    document.getElementById('analyzeBtn').disabled = false;
}

// Render minimal detection labels
function renderLabels(labels) {
    const container = document.getElementById('labelsContainer');
    container.innerHTML = '';

    const labelConfig = {
        harassment: 'Harassment',
        hate_speech: 'Hate Speech',
        threats: 'Threats',
        sexual_content: 'Inappropriate',
        emotional_abuse: 'Abuse',
        cyberbullying: 'Cyberbullying'
    };

    for (const [key, label] of Object.entries(labelConfig)) {
        const detected = labels[key] || false;
        const chip = document.createElement('div');
        chip.className = `label-minimal ${detected ? 'detected' : 'safe'}`;
        chip.textContent = label;
        container.appendChild(chip);
    }
}

// Add analysis to history
function addToHistory(text, data) {
    const summary = text.substring(0, 40) + (text.length > 40 ? '...' : '');
    const severity = data.severity_level || 'Unknown';
    const timestamp = new Date().toLocaleTimeString();
    
    analysisHistory.unshift({
        text: summary,
        severity: severity,
        score: data.toxicity_score,
        time: timestamp
    });

    // Keep only last 5 analyses
    if (analysisHistory.length > 5) {
        analysisHistory.pop();
    }

    updateInsightsPanel();
}

// Update insights panel
function updateInsightsPanel() {
    const panel = document.getElementById('insightsPanel');
    
    if (analysisHistory.length === 0) {
        panel.innerHTML = '<p class="text-muted">No recent analysis</p>';
        return;
    }

    panel.innerHTML = analysisHistory.map(item => `
        <div class="insight-item">
            <strong>${item.time}</strong> - ${item.severity} (${item.score}/100)<br>
            <em>${item.text}</em>
        </div>
    `).join('');
}

// Initialize
window.addEventListener('DOMContentLoaded', function() {
    showIdleState();
});
