// ==============================
// GLOBAL STATE
// ==============================
let analysisHistory = [];

// ==============================
// INIT
// ==============================
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("analyzeForm");
    if (form) form.addEventListener("submit", handleAnalyze);
    showIdleState();
});

// ==============================
// FORM HANDLER
// ==============================
async function handleAnalyze(e) {
    e.preventDefault();

    const text = document.getElementById("text_content")?.value.trim() || "";
    const image = document.getElementById("image_file")?.files[0];

    if (!text && !image) {
        alert("Please enter text or upload an image.");
        return;
    }

    showAnalyzingState();

    try {
        const fd = new FormData();
        fd.append("text", text);
        if (image) fd.append("image", image);

        const res = await fetch("/analyze", { method: "POST", body: fd });
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
// MAIN UI UPDATE (STRICT SAFETY)
// ==============================
function updateUI(data = {}) {
    const score = Number(data.toxicity_score || 0);
    const labels = data.detected_labels || {};

    // 🔒 HARD SAFETY LOGIC (UI NEVER LIES)
    const hasHarm = Object.values(labels).some(Boolean);
    const isRisk = score >= 40 || hasHarm;

    let severity;
    if (score >= 90) severity = "Critical";
    else if (score >= 70) severity = "High";
    else if (score >= 40) severity = "Medium";
    else severity = "Low";

    updateGauge(score);
    updateRiskBar(score);

    setText("riskScore", `${score}%`);
    setText("riskStatus", severity);

    setText(
        "explanationText",
        data.explanation || "Potentially unsafe content detected."
    );

    renderLabels(labels, score);
    renderVictimSupport(data.victim_support_message);
    renderSafeSteps(data.safe_response_steps || []);

    toggle("alertInfo", !!data.parent_alert_required);

    toggle("analyzingState", false);
    toggle("resultsEmpty", false);
    toggle("resultsContent", true);

    // 🔴 SAFE vs RISK STATE (FINAL AUTHORITY)
    if (isRisk) {
        toggle("riskState", true);
        toggle("safeState", false);
    } else {
        toggle("riskState", false);
        toggle("safeState", true);
    }

    disableAnalyze(false);
    addToHistory({ score, severity, labels });
}

// ==============================
// VISUALS
// ==============================
function updateGauge(score) {
    const needle = document.getElementById("gaugeNeedle");
    if (!needle) return;
    needle.style.transform =
        `translateX(-50%) rotate(${score * 1.8 - 90}deg)`;
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
// LABELS (INTENT-AWARE)
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

    let shown = false;

    Object.entries(LABEL_MAP).forEach(([key, label]) => {
        if (labels[key]) {
            shown = true;
            container.innerHTML +=
                `<span class="label-minimal detected">⚠ ${label}</span>`;
        }
    });

    if (!shown) {
        container.innerHTML =
            score >= 40
                ? `<span class="label-minimal detected">⚠ Unsafe content detected</span>`
                : `<span class="label-minimal safe">✓ No major risks detected</span>`;
    }
}

// ==============================
// SUPPORT
// ==============================
function renderVictimSupport(text) {
    const section = document.getElementById("victimSupportSection");
    const el = document.getElementById("victimSupportText");
    if (!section || !el) return;

    el.textContent =
        text || "You are not alone. Please talk to someone you trust.";
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
// HISTORY (SANITIZED)
// ==============================
function addToHistory(entry) {
    analysisHistory.unshift(entry);
    if (analysisHistory.length > 5) analysisHistory.pop();
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

    analysisHistory.forEach(item => {
        const li = document.createElement("li");
        li.className = "history-item";
        li.innerHTML = `
            <div class="history-info">
                <span class="history-severity">${item.severity} Risk</span>
                <span class="history-labels">
                    ${Object.keys(item.labels).filter(k => item.labels[k]).join(", ") || "Safe"}
                </span>
            </div>
        `;
        list.appendChild(li);
    });
}

// ==============================
// UTILS
// ==============================
function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}
