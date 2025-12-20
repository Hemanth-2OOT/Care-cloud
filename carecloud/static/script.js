// Form submission handler
document.getElementById('analyzeForm').addEventListener('submit', async function(e) {
    e.preventDefault();

    const textContent = document.getElementById('text_content').value;
    const imageFile = document.getElementById('image_file').files[0];

    if (!textContent.trim() && !imageFile) {
        alert('Please enter some text or upload an image to analyze.');
        return;
    }

    // UI State: Loading
    const analyzeBtn = document.getElementById('analyzeBtn');
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    const initialState = document.getElementById('initialState');

    analyzeBtn.disabled = true;
    initialState.style.display = 'none';
    results.classList.remove('active');
    loading.classList.add('active');

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
        } else {
            alert('Error: ' + (data.error || 'Something went wrong'));
        }

    } catch (error) {
        console.error('Error:', error);
        alert('Failed to connect to the server.');
    } finally {
        analyzeBtn.disabled = false;
        loading.classList.remove('active');
        results.classList.add('active');
    }
});

// Update UI with analysis results
function updateUI(data) {
    const scoreValue = document.getElementById('scoreValue');
    const severityLabel = document.getElementById('severityLabel');
    const explanationText = document.getElementById('explanationText');
    const supportMessageText = document.getElementById('supportMessageText');
    const recommendedActionText = document.getElementById('recommendedActionText');
    const scoreContainer = document.getElementById('scoreContainer');
    const alertInfo = document.getElementById('alertInfo');
    const severityMeter = document.getElementById('severityMeter');
    const labelsContainer = document.getElementById('labelsContainer');

    // Update score circle
    const score = data.toxicity_score || 0;
    scoreValue.textContent = score;
    severityLabel.textContent = data.severity_level || 'Unknown';
    explanationText.textContent = data.explanation || 'Analysis completed.';
    supportMessageText.textContent = data.victim_support_message || 'You are valued and safe.';
    recommendedActionText.textContent = data.recommended_action || 'Continue being kind online!';

    // Update severity color classes
    scoreContainer.className = 'score-display';
    if (data.severity_level === 'Low') scoreContainer.classList.add('severity-low');
    else if (data.severity_level === 'Medium') scoreContainer.classList.add('severity-medium');
    else if (data.severity_level === 'High') scoreContainer.classList.add('severity-high');
    else if (data.severity_level === 'Critical') scoreContainer.classList.add('severity-critical');

    // Update severity meter
    updateSeverityMeter(score);

    // Render detection labels
    renderLabels(data.detected_labels || {});

    // Show/hide parent alert
    if (data.parent_alert_required) {
        alertInfo.style.display = 'block';
    } else {
        alertInfo.style.display = 'none';
    }
}

// Render detection labels as chips
function renderLabels(labels) {
    const container = document.getElementById('labelsContainer');
    container.innerHTML = '';

    const labelConfig = {
        harassment: { emoji: '🚨', label: 'Harassment' },
        hate_speech: { emoji: '⚠️', label: 'Hate Speech' },
        threats: { emoji: '🔴', label: 'Threats' },
        sexual_content: { emoji: '🔒', label: 'Inappropriate' },
        emotional_abuse: { emoji: '💔', label: 'Emotional Abuse' },
        cyberbullying: { emoji: '📱', label: 'Cyberbullying' }
    };

    let hasDetections = false;
    for (const [key, config] of Object.entries(labelConfig)) {
        const detected = labels[key] || false;
        const chip = document.createElement('div');
        chip.className = `label-chip ${detected ? 'detected' : 'safe'}`;
        chip.innerHTML = `
            <span class="label-emoji">${config.emoji}</span>
            <span class="label-text">${config.label}</span>
            <span class="label-status">${detected ? '⚠️ Detected' : '✓ Safe'}</span>
        `;
        container.appendChild(chip);
        if (detected) hasDetections = true;
    }

    if (!hasDetections) {
        const safeMessage = document.createElement('p');
        safeMessage.className = 'safe-message';
        safeMessage.textContent = '✨ No harmful content detected!';
        container.insertBefore(safeMessage, container.firstChild);
    }
}

// Update severity meter based on score
function updateSeverityMeter(score) {
    const meter = document.getElementById('severityMeter');
    meter.style.width = Math.min(score, 100) + '%';
    
    // Color based on severity
    if (score <= 30) meter.style.background = 'linear-gradient(90deg, #10b981, #06b6d4)';
    else if (score <= 60) meter.style.background = 'linear-gradient(90deg, #f59e0b, #ec4899)';
    else meter.style.background = 'linear-gradient(90deg, #ff006e, #dc2626)';
}
