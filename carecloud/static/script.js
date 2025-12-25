// ==============================
// GLOBAL STATE
// ==============================
const analysisHistory = [];

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

        if (!res.ok) throw new Error("Analysis failed");

        const data = await res.json();
        updateUI(data);
        addToHistory(text, data);

    } catch (err) {
        console.error(err);
        alert("Something went wrong. Please try again.");
        showIdleState();
    }
}

// ==============================
// UI STATES
// ==============================
function showAnalyzingState() {
    toggle("idleState", false);
    toggle("analyzingState", true);
    toggle("safeState", false);
    toggle("riskState", false);
    toggle("resultsEmpty", false);
    toggle("resultsContent", false);
    disableAnalyze(true);
}

function showIdleState() {
    toggle("idleState", true);
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
function updateUI(data = {}) {
    const score = Number(data.toxicity_score || 0);
    const severity = data.severity_level || "Low";

    updateGauge(score);
    updateRiskBar(score, severity);
    updateState(score);

    setText("riskScore", `${score}%`);
    setText("riskStatus", severity);

    setText(
        "explanationText",
        data.explanation ||
        "This content may be unsafe or inappropriate for children."
    );

    renderLabels(data.detected_labels || {});
    renderVictimSupport(data);
    renderSafeSteps(data.safe_response_steps || []);

    toggle("alertInfo", !!data.parent_alert_required);

    toggle("resultsEmpty", false);
    toggle("resultsContent", true);
    disableAnalyze(false);
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

function updateRiskBar(score, severity) {
    const bar = document.getElementById("riskBar");
    if (!bar) return;

    bar.style.width = `${score}%`;
    bar.style.background =
        score >= 70 ? "#ef4444" :
        score >= 40 ? "#f59e0b" :
        "#22c55e";
}

function updateState(score) {
    toggle("analyzingState", false);
    if (score >= 40) {
        toggle("riskState", true);
        toggle("safeState", false);
    } else {
        toggle("safeState", true);
        toggle("riskState", false);
    }
}

// ==============================
// SUPPORT & GUIDANCE
// ==============================
function renderVictimSupport(data) {
    const section = document.getElementById("victimSupportSection");
    const text = document.getElementById("victimSupportText");

    if (!section || !text) return;

    text.textContent =
        data.victim_support_message ||
        "You are not alone. If this made you uncomfortable, please talk to a trusted adult.";

    section.style.display = "block";
}

function renderSafeSteps(steps) {
    const list = document.getElementById("safeResponsesList");
    if (!list) return;

    if (!Array.isArray(steps) || steps.length === 0) {
        list.innerHTML = "<li>Talk to a trusted adult.</li>";
        return;
    }

    list.innerHTML = steps.map(step =>
        `<li class="response-item">${step}</li>`
    ).join("");
}

// ==============================
// LABELS (FIXED + INTENT-BASED)
// ==============================
function renderLabels(labels) {
    const container = document.getElementById("labelsContainer");
    if (!container) return;

    const LABELS = {
        toxicity: "Toxic Language",
        insult: "Insults",
        profanity: "Profanity",
        threat: "Threats",
        sexual_explicit: "Sexual Content",
        flirtation: "Grooming / Manipulation",
        identity_attack: "Identity Attack",
        severe_toxicity: "Severe Abuse"
    };

    container.innerHTML = "";

    Object.entries(LABELS).forEach(([key, label]) => {
        const value = labels[key];
        if (value && value > 0.4) {
            container.innerHTML += `
                <span class="label-minimal detected">⚠ ${label}</span>
            `;
        }
    });

    if (!container.innerHTML) {
        container.innerHTML =
            `<span class="label-minimal safe">✓ No major risks detected</span>`;
    }
}

// ==============================
// HISTORY
// ==============================
function addToHistory(text, data) {
    analysisHistory.unshift({
        text: (text || "Image").slice(0, 40),
        severity: data.severity_level || "Low",
        score: data.toxicity_score || 0,
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        explanation: data.explanation || ""
    });

    if (analysisHistory.length > 5) analysisHistory.pop();
    updateInsightsPanel();
}

function updateInsightsPanel() {
    const panel = document.getElementById("insightsPanel");
    if (!panel) return;

    panel.innerHTML = analysisHistory.map(item => `
        <div class="history-item"
             onclick="showHistoryDetail('${escapeQuotes(item.explanation)}')">
            <div class="history-info">
                <span class="history-preview">${item.text}</span>
                <div class="history-meta">
                    <span>${item.time}</span>
                    <span class="severity-badge severity-${item.severity.toLowerCase()}">
                        ${item.severity}
                    </span>
                </div>
            </div>
            <div class="history-score">${item.score}%</div>
        </div>
    `).join("");
}

// ==============================
// MODAL
// ==============================
function showHistoryDetail(text) {
    const modal = document.getElementById("reasonModal");
    const body = document.getElementById("modalExplanation");
    if (modal && body) {
        body.textContent = text;
        modal.classList.add("active");
    }
}

function closeReasonModal() {
    document.getElementById("reasonModal")?.classList.remove("active");
}

// ==============================
// UTILS
// ==============================
function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function escapeQuotes(str = "") {
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
}
