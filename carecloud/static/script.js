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

    // Render Categories
    const categoriesDiv = document.getElementById('categoriesDiv');
    if (data.categories && data.categories.length > 0) {
        categoriesDiv.innerHTML = data.categories.map(cat => `<span class="category-badge">${cat}</span>`).join('');
        categoriesDiv.style.display = 'flex';
    } else {
        categoriesDiv.style.display = 'none';
    }

    // Update Classes for Colors
    scoreContainer.className = 'score-display'; // reset
    if (data.severity_level === 'Low') scoreContainer.classList.add('severity-low');
    else if (data.severity_level === 'Medium') scoreContainer.classList.add('severity-medium');
    else if (data.severity_level === 'High') scoreContainer.classList.add('severity-high');
    else if (data.severity_level === 'Critical') scoreContainer.classList.add('severity-critical');

    // Alert Info
    if (data.parent_alert_required) {
        alertInfo.style.display = 'block';
    } else {
        alertInfo.style.display = 'none';
    }
}
