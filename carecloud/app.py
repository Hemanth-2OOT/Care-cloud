import os
import json
import requests
import smtplib
import logging
import traceback

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import (
    Flask, render_template, request,
    jsonify, session, redirect, url_for
)

from google import genai

# =====================================================
# APP SETUP
# =====================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "carecloud-dev-secret")

PORT = int(os.environ.get("PORT", 5000))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("carecloud")

# =====================================================
# ENV VARIABLES
# =====================================================
PERSPECTIVE_API_KEY = os.environ.get("PERSPECTIVE_API_KEY")
GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI")
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

# =====================================================
# GEMINI CLIENT
# =====================================================
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("✅ Gemini client initialized")
    except Exception as e:
        logger.error(f"❌ Gemini init failed: {e}")
        client = None

# =====================================================
# AUTH HELPER
# =====================================================
def logged_in():
    return "user" in session

# =====================================================
# PERSPECTIVE API
# =====================================================
def perspective_analyze(text):
    if not PERSPECTIVE_API_KEY or not text:
        return {}

    url = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

    payload = {
        "comment": {"text": text},
        "languages": ["en"],
        "requestedAttributes": {
            "TOXICITY": {},
            "SEVERE_TOXICITY": {},
            "INSULT": {},
            "THREAT": {},
            "IDENTITY_ATTACK": {},
            "SEXUALLY_EXPLICIT": {}
        }
    }

    try:
        r = requests.post(
            url,
            params={"key": PERSPECTIVE_API_KEY},
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )

        if r.status_code != 200:
            logger.error(f"Perspective HTTP {r.status_code}")
            return {}

        data = r.json()
        scores = {}

        for k, v in data.get("attributeScores", {}).items():
            scores[k.lower()] = int(v["summaryScore"]["value"] * 100)

        return scores

    except Exception as e:
        logger.error(f"Perspective error: {e}")
        return {}

# =====================================================
# GEMINI ANALYSIS (NO TRIPLE QUOTES)
# =====================================================
def gemini_analyze(text):
    if not client:
        raise RuntimeError("Gemini client not available")

    prompt = (
        "You are the CareCloud Forensic Safety AI. Your goal is to detect harm in messages sent to children/minors.\n"
        "Analyze the provided text for both explicit and implicit dangers, specifically focusing on predatory behavior "
        "that often bypasses simple keyword filters.\n\n"

        "LABEL DEFINITIONS & CHILD HARM CRITERIA:\n"
        "1. grooming: Building rapport to isolate a child (e.g., don't tell your parents, our secret, you're so mature).\n"
        "2. manipulation: Using guilt, gifts, or loyalty tests to control a minor.\n"
        "3. sexual_content: Explicit acts OR suggestive borderline language.\n"
        "4. harassment: Repeated unwanted contact or bullying.\n"
        "5. emotional_abuse: Gaslighting or demeaning language.\n"
        "6. threats/violence: Physical threats or encouragement of harm.\n"
        "7. profanity: Vulgar language.\n"
        "8. hate_speech: Identity-based attacks.\n\n"

        "RISK SCORING WEIGHTS:\n"
        "- Grooming or isolation behavior = 85+\n"
        "- Requests for private photos or meetups = 95+\n"
        "- Intimidation or bullying = 50+\n\n"

        "RESPONSE FORMAT (STRICT JSON ONLY):\n"
        "{\n"
        "  \"risk_score\": 0-100,\n"
        "  \"severity_level\": \"Low | Medium | High | Critical\",\n"
        "  \"detected_labels\": {\n"
        "    \"harassment\": bool,\n"
        "    \"profanity\": bool,\n"
        "    \"hate_speech\": bool,\n"
        "    \"sexual_content\": bool,\n"
        "    \"grooming\": bool,\n"
        "    \"manipulation\": bool,\n"
        "    \"threats\": bool,\n"
        "    \"violence\": bool,\n"
        "    \"emotional_abuse\": bool,\n"
        "    \"self_harm_risk\": bool\n"
        "  },\n"
        "  \"context_summary\": \"Short explanation\",\n"
        "  \"support_for_user\": \"Supportive message\",\n"
        "  \"instructions\": [\"Step 1\", \"Step 2\"]\n"
        "}\n\n"
        f"TEXT TO ANALYZE: \"{text}\""
    )

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[prompt]
        )

        raw = response.text or ""
        start = raw.find("{")
        end = raw.rfind("}") + 1

        if start == -1 or end <= start:
            raise ValueError("Invalid JSON from Gemini")

        return json.loads(raw[start:end])

    except Exception:
        logger.error("Gemini error")
        logger.error(traceback.format_exc())
        raise

# =====================================================
# LOCAL FALLBACK (NEVER FAILS)
# =====================================================
def local_fallback(text):
    t = text.lower()
    labels = {
        "harassment": False,
        "profanity": False,
        "hate_speech": False,
        "sexual_content": False,
        "grooming": False,
        "manipulation": False,
        "threats": False,
        "violence": False,
        "emotional_abuse": False,
        "self_harm_risk": False
    }

    if any(w in t for w in ["secret", "don't tell", "meet up", "private"]):
        labels["grooming"] = True
        labels["manipulation"] = True
        score = 85
    else:
        score = 10

    return {
        "risk_score": score,
        "severity_level": "High" if score >= 70 else "Low",
        "detected_labels": labels,
        "context_summary": "Detected restricted or unsafe patterns.",
        "support_for_user": "Please talk to a trusted adult.",
        "instructions": ["Do not reply", "Show this message to a parent"]
    }

# =====================================================
# EMAIL ALERT
# =====================================================
def send_parent_alert(text, score, parent_email):
    if not (MAIL_USERNAME and MAIL_PASSWORD and parent_email):
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = MAIL_USERNAME
        msg["To"] = parent_email
        msg["Subject"] = "🚨 CareCloud Safety Alert"

        body = (
            "High-risk content detected.\n\n"
            f"Message: {text}\n"
            f"Risk Score: {score}%\n\n"
            "Please review immediately."
        )

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)

    except Exception as e:
        logger.error(f"Email error: {e}")

# =====================================================
# ROUTES
# =====================================================
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "")
        session["user"] = {
            "name": email.split("@")[0].title(),
            "email": email,
            "parent_email": request.form.get("parent_email", "")
        }
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/dashboard")
def dashboard():
    if not logged_in():
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=session["user"])

@app.route("/analyze", methods=["POST"])
def analyze():
    if not logged_in():
        return jsonify({"error": "Unauthorized"}), 401

    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    p_scores = perspective_analyze(text)

    try:
        g_data = gemini_analyze(text)
    except Exception:
        g_data = local_fallback(text)

    p_max = max(p_scores.values()) if p_scores else 0
    final_score = max(p_max, g_data.get("risk_score", 0))

    detected = g_data.get("detected_labels", {})

    if detected.get("grooming") or detected.get("sexual_content"):
        final_score = max(final_score, 85)

    if final_score >= 90:
        severity = "Critical"
    elif final_score >= 75:
        severity = "High"
    elif final_score >= 40:
        severity = "Medium"
    else:
        severity = "Low"

    if final_score >= 80:
        send_parent_alert(text, final_score, session["user"].get("parent_email"))

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": detected,
        "content_safe": final_score < 40,
        "parent_alert_required": final_score >= 80,
        "analysis": g_data
    })

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
