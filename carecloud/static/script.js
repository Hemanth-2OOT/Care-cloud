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

function updateUI(data) {
    const scoreValue = document.getElementById('scoreValue');
    const severityLabel = document.getElementById('severityLabel');
    const explanationText = document.getElementById('explanationText');
    const supportMessageText = document.getElementById('supportMessageText');
    const scoreContainer = document.getElementById('scoreContainer');
    const alertInfo = document.getElementById('alertInfo');

    // Update Text
    scoreValue.textContent = data.toxicity_score;
    severityLabel.textContent = data.severity_level;
    explanationText.textContent = data.explanation;
    supportMessageText.textContent = data.victim_support_message;

    // Update Toxicity Meter
    const meterFill = document.getElementById('toxicityMeterFill');
    meterFill.style.width = `${data.toxicity_score}%`;

    // Update Meter Colors & Classes
    let severityColor = '#34d399'; // Default Safe

    if (data.severity_level === 'Low') {
        severityColor = '#34d399';
    } else if (data.severity_level === 'Medium') {
        severityColor = '#f59e0b';
    } else if (data.severity_level === 'High' || data.severity_level === 'Critical') {
        severityColor = '#ef4444';
    }
    meterFill.style.backgroundColor = severityColor;

    // Render Categories
    const categoriesDiv = document.getElementById('categoriesDiv');
    if (data.categories && data.categories.length > 0) {
        categoriesDiv.innerHTML = data.categories.map(cat => `<span class="category-badge">${cat}</span>`).join('');
        categoriesDiv.style.display = 'flex';
    } else {
        categoriesDiv.style.display = 'none';
    }

    // Show Next Steps if Harmful
    const nextSteps = document.getElementById('nextSteps');
    if (data.toxicity_score > 30) {
        nextSteps.style.display = 'block';
    } else {
        nextSteps.style.display = 'none';
    }

    // Alert Info
    if (data.parent_alert_required) {
        alertInfo.style.display = 'block';
    } else {
        alertInfo.style.display = 'none';
    }
}
