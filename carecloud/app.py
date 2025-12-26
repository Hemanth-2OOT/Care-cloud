import os
import json
import requests
import smtplib
import logging
import io

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import (
    Flask, render_template, request,
    jsonify, session, redirect, url_for
)

from PIL import Image
from google import genai

# =====================================================
# APP SETUP
# =====================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "carecloud-dev-secret")

PORT = int(os.environ.get("PORT", 8080))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =====================================================
# ENV VARIABLES (DO NOT RENAME)
# =====================================================
PERSPECTIVE_API_KEY = os.environ.get("PERSPECTIVE_API_KEY")
GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI")
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

# =====================================================
# GEMINI CLIENT (NEW SDK – SAFE)
# =====================================================
client = None
if GEMINI_API_KEY:
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini client initialized")
    except Exception as e:
        logger.error(f"Gemini init failed: {e}")

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

    try:
        r = requests.post(
            "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze",
            params={"key": PERSPECTIVE_API_KEY},
            json={
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
            },
            timeout=8
        )
        data = r.json()
    except Exception as e:
        logger.error(f"Perspective error: {e}")
        return {}

    scores = {}
    for k, v in data.get("attributeScores", {}).items():
        scores[k.lower()] = int(v["summaryScore"]["value"] * 100)

    return scores

# =====================================================
# GEMINI ANALYSIS (INTENT + GROOMING SAFE)
# =====================================================
def gemini_analyze(text):
    if not client:
        raise RuntimeError("Gemini client not available")

    prompt = f"""
You are CareCloud Safety Guardian AI.

The reader is ALWAYS a child or teenager.

Rules:
- Sexual language is NEVER safe for minors
- Sexual invitations = HIGH RISK
- Flattery + sexual intent = grooming
- Never mark sexual content as safe

Return STRICT JSON ONLY:

{{
  "risk_score": number,
  "detected_labels": {{
    "sexual_content": true/false,
    "grooming": true/false,
    "harassment": true/false,
    "manipulation": true/false,
    "emotional_abuse": true/false,
    "violence": true/false,
    "self_harm_risk": true/false
  }},
  "why_harmful": "Explain why unsafe for a child",
  "victim_support_message": "Reassuring message",
  "safe_response_steps": [
    "Do not reply",
    "Block or mute the sender",
    "Tell a trusted adult"
  ],
  "parent_guidance": "Supportive advice"
}}

Message:
\"\"\"{text}\"\"\"
"""

    response = client.models.generate_content(
        model="gemini-1.5-flash",
        contents=[prompt]
    )

    raw = response.text
    start = raw.find("{")
    end = raw.rfind("}") + 1
    return json.loads(raw[start:end])

# =====================================================
# LOCAL FALLBACK (NEVER FAILS)
# =====================================================
def local_fallback(text):
    t = text.lower()

    labels = {
        "sexual_content": False,
        "grooming": False,
        "harassment": False,
        "manipulation": False,
        "emotional_abuse": False,
        "violence": False,
        "self_harm_risk": False
    }

    score = 10

    sexual_terms = [
        "penis", "sex", "come sit", "touch me",
        "nude", "kiss", "send pic", "bed"
    ]

    if any(w in t for w in sexual_terms):
        labels.update({
            "sexual_content": True,
            "grooming": True,
            "harassment": True,
            "manipulation": True
        })
        score = 85

    return {
        "risk_score": score,
        "detected_labels": labels,
        "why_harmful": "This message contains inappropriate sexual content for a minor.",
        "victim_support_message": "You did nothing wrong. This is not okay.",
        "safe_response_steps": [
            "Do not reply",
            "Block the sender",
            "Tell a trusted adult"
        ],
        "parent_guidance": "Provide calm reassurance."
    }

# =====================================================
# EMAIL ALERT
# =====================================================
def send_parent_alert(text, score, parent_email):
    if not (MAIL_USERNAME and MAIL_PASSWORD and parent_email):
        return

    msg = MIMEMultipart()
    msg["From"] = MAIL_USERNAME
    msg["To"] = parent_email
    msg["Subject"] = "⚠ CareCloud Safety Alert"

    msg.attach(MIMEText(
        f"High-risk content detected.\n\nMessage:\n{text}\n\nRisk Score: {score}%",
        "plain"
    ))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)

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
            "parent_email": session.get("parent_email")
        }
        return redirect(url_for("dashboard"))
    return render_template("login.html", mode="login")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        session["user"] = {
            "name": request.form.get("name"),
            "email": request.form.get("email"),
            "parent_email": request.form.get("parent_email")
        }
        return redirect(url_for("dashboard"))
    return render_template("login.html", mode="signup")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
def dashboard():
    if not logged_in():
        return redirect(url_for("login"))
    return render_template("dashboard.html", user=session["user"], history=[])

# =====================================================
# ANALYZE ENDPOINT (FINAL SAFE VERSION)
# =====================================================
@app.route("/analyze", methods=["POST"])
def analyze():
    if not logged_in():
        return jsonify({"error": "Unauthorized"}), 401

    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    perspective = perspective_analyze(text)

    try:
        gemini_data = gemini_analyze(text)
    except Exception as e:
        logger.error(f"Gemini failed: {e}")
        gemini_data = local_fallback(text)

    final_score = max(
        perspective.get("toxicity", 0),
        gemini_data.get("risk_score", 0)
    )

    detected = gemini_data["detected_labels"]

    if detected.get("sexual_content"):
        final_score = max(final_score, 70)
    if detected.get("grooming"):
        final_score = max(final_score, 80)

    if final_score >= 90:
        severity = "Critical"
    elif final_score >= 70:
        severity = "High"
    elif final_score >= 40:
        severity = "Medium"
    else:
        severity = "Low"

    if final_score >= 80:
        send_parent_alert(
            text,
            final_score,
            session["user"].get("parent_email")
        )

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": detected,
        "explanation": gemini_data["why_harmful"],
        "victim_support_message": gemini_data["victim_support_message"],
        "safe_response_steps": gemini_data["safe_response_steps"],
        "parent_alert_required": final_score >= 80
    })

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
