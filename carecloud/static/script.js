// ==============================
// INIT
// ==============================
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("analyzeForm");
    if (form) {
        form.addEventListener("submit", handleAnalyze);
    }
    showIdleState();
});

// ==============================
// FORM HANDLER
// ==============================
async function handleAnalyze(e) {
    e.preventDefault();

    const text = document.getElementById("text_content")?.value || "";
    const image = document.getElementById("image_file")?.files[0];

    if (!text.trim() && !image) {
        alert("Please enter text or upload an image.");
        return;
    }

    showAnalyzingState();

    try {
        const fd = new FormData();
        fd.append("text", text);
        if (image) fd.append("image", image);

        const res = await fetch("/analyze", {
            method: "POST",
            body: fd
        });

        const data = await res.json();
        updateUI(data);

    } catch (err) {
        console.error(err);
        alert("Analysis failed. Please try again.");
        showIdleState();
    }
}

// ==============================
// STATES
// ==============================
function showAnalyzingState() {
    toggle("analyzingState", true);
    toggle("safeState", false);
    toggle("riskState", false);
    toggle("resultsEmpty", false);
    toggle("resultsContent", false);
    disableAnalyze(true);
}

function showIdleState() {
    toggle("analyzingState", false);
    toggle("safeState", false);
    toggle("riskState", false);
    toggle("resultsEmpty", true);
    toggle("resultsContent", false);
    disableAnalyze(false);
}

function disableAnalyze(disabled) {
    const btn = document.getElementById("analyzeBtn");
    if (btn) btn.disabled = disabled;
}

function toggle(id, show) {
    const el = document.getElementById(id);
    if (el) el.style.display = show ? "block" : "none";
}

// ==============================
// MAIN UI UPDATE
// ==============================
function updateUI(data) {
    const score = Number(data.toxicity_score || 0);
    const severity = data.severity_level || "Low";

    updateGauge(score);
    updateRiskBar(score);

    document.getElementById("riskScore").textContent = `${score}%`;
    document.getElementById("riskStatus").textContent = severity;

    document.getElementById("explanationText").textContent =
        data.explanation || "This content may be harmful.";

    renderLabels(data.detected_labels || {}, score);
    renderVictimSupport(data.victim_support_message);
    renderSafeSteps(data.safe_response_steps || []);

    toggle("alertInfo", !!data.parent_alert_required);
    toggle("analyzingState", false);
    toggle("resultsEmpty", false);
    toggle("resultsContent", true);

    // Strict UI State Logic
    const hasLabels = Object.values(data.detected_labels || {}).some(val => val === true);
    const isRisk = score >= 40 || hasLabels;

    if (isRisk) {
        toggle("riskState", true);
        toggle("safeState", false);
    } else {
        toggle("riskState", false);
        toggle("safeState", true);
    }

    disableAnalyze(false);
    addToHistory(data);
}

// ==============================
// VISUALS
// ==============================
function updateGauge(score) {
    const needle = document.getElementById("gaugeNeedle");
    if (!needle) return;
    const rotation = score * 1.8 - 90;
    needle.style.transform = `translateX(-50%) rotate(${rotation}deg)`;
}

function updateRiskBar(score) {
    const bar = document.getElementById("riskBar");
    if (!bar) return;

    bar.style.width = `${score}%`;
    bar.style.background =
        score >= 70 ? "#ef4444" :
        score >= 40 ? "#f59e0b" :
        "#10b981";
}

// ==============================
// LABELS (GEMINI-BASED)
// ==============================
function renderLabels(labels, score) {
    const container = document.getElementById("labelsContainer");
    if (!container) return;

    container.innerHTML = "";

    const LABEL_MAP = {
        sexual_content: "Sexual Content",
        grooming: "Grooming",
        harassment: "Harassment",
        manipulation: "Manipulation",
        emotional_abuse: "Emotional Abuse",
        violence: "Violence",
        self_harm_risk: "Self-Harm Risk"
    };

    let found = false;

    Object.entries(LABEL_MAP).forEach(([key, label]) => {
        if (labels[key]) {
            found = true;
            container.innerHTML +=
                `<span class="label-minimal detected">⚠ ${label}</span>`;
        }
    });

    if (!found) {
        if (score >= 40) {
            // Safety Consistency: High score but no specific labels
            container.innerHTML = `<span class="label-minimal detected">⚠ Unsafe content detected</span>`;
        } else {
            container.innerHTML = `<span class="label-minimal safe">✓ No major risks detected</span>`;
        }
    }
}

// ==============================
// SUPPORT
// ==============================
function renderVictimSupport(text) {
    const section = document.getElementById("victimSupportSection");
    const el = document.getElementById("victimSupportText");

    if (!section || !el) return;

    el.textContent = text || "You are not alone. Please talk to someone you trust.";
    section.style.display = "block";
}

function renderSafeSteps(steps) {
    const list = document.getElementById("safeResponsesList");
    if (!list) return;

    list.innerHTML = steps.length
        ? steps.map(s => `<li class="response-item">${s}</li>`).join("")
        : "<li>Talk to a trusted adult.</li>";
}

// ==============================
// HISTORY & MODAL
// ==============================
let analysisHistory = [];

function addToHistory(data) {
    analysisHistory.unshift(data);
    renderHistory();
}

function renderHistory() {
    const list = document.getElementById("historyList");
    const emptyMsg = document.getElementById("noHistoryMsg");
    if (!list) return;

    list.innerHTML = "";

    if (analysisHistory.length === 0) {
        if (emptyMsg) emptyMsg.style.display = "block";
        return;
    }

    if (emptyMsg) emptyMsg.style.display = "none";

    analysisHistory.forEach((item, index) => {
        const li = document.createElement("li");
        li.className = "history-item";

        // Format detected labels
        const LABEL_MAP = {
            sexual_content: "Sexual Content",
            grooming: "Grooming",
            harassment: "Harassment",
            manipulation: "Manipulation",
            emotional_abuse: "Emotional Abuse",
            violence: "Violence",
            self_harm_risk: "Self-Harm Risk"
        };

        const labels = Object.entries(item.detected_labels || {})
            .filter(([key, val]) => val && LABEL_MAP[key])
            .map(([key, _]) => LABEL_MAP[key])
            .join(", ") || "Safe";

        li.innerHTML = `
            <div class="history-info">
                <span class="history-severity ${item.severity_level}">${item.severity_level} Risk</span>
                <span class="history-labels">${labels}</span>
            </div>
        `;
        list.appendChild(li);
    });
}
