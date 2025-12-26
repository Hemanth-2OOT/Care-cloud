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

# Replit webview requires port 5000. Use PORT env var to override.
PORT = int(os.environ.get("PORT", 5000))

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
        scores = {}
        for k, v in data.get("attributeScores", {}).items():
            scores[k.lower()] = int(v["summaryScore"]["value"] * 100)
        return scores
    except Exception as e:
        logger.error(f"Perspective error: {e}")
        return {}

# =====================================================
# GEMINI ANALYSIS (INTENT + GROOMING SAFE)
# =====================================================
def gemini_analyze(text):
    if not client:
        raise RuntimeError("Gemini client not available")

    prompt = f"""You are CareCloud Safety Intelligence AI. Your primary responsibility is to protect CHILDREN and TEENAGERS from harmful digital communication.

CRITICAL: Assume the recipient is always a minor. Analyze at THREE levels:
1. Literal Content
2. Implied/Hidden Intent
3. Escalation Risk

SCORING RULES (NON-NEGOTIABLE):
• sexual_content = true → risk_score ≥ 70
• grooming = true → risk_score ≥ 80
• If ANY label is true → content is NOT SAFE
• NEVER mark content as safe if sexual intent exists
• Friendly tone ≠ Safe intent. Compliments + sexual context = HIGH RISK

LABEL DEFINITIONS:
- sexual_content: explicit sexual language, body parts, invitations, sexualized compliments
- grooming: flattery + sexual intent, normalization of sexual topics, secrecy requests
- manipulation: emotional steering, "You're special", making child feel responsible
- harassment: unwanted sexual attention, objectifying language
- emotional_abuse: shaming, guilt-tripping, fear, control
- violence: threats, intimidation, harm
- self_harm_risk: encouraging or expressing self-harm or suicide

Return STRICT JSON ONLY:
{{
  "risk_score": number,
  "severity_level": "Low | Medium | High | Critical",
  "detected_labels": {{
    "sexual_content": true/false,
    "grooming": true/false,
    "harassment": true/false,
    "manipulation": true/false,
    "emotional_abuse": true/false,
    "violence": true/false,
    "self_harm_risk": true/false
  }},
  "why_harmful": "Clear explanation written for a teenager",
  "victim_support_message": "Kind, calming reassurance (never blame)",
  "safe_response_steps": [
    "Do not reply",
    "Block or mute the sender",
    "Tell a trusted adult"
  ],
  "dashboard_summary": {{
    "risk_overview": "1-2 sentence plain-language summary",
    "primary_concerns": ["Short label list"],
    "intent_detected": "Explain hidden intent in simple terms",
    "recommended_action": "Immediate guidance for the user",
    "parent_visibility": true/false
  }}
}}

Message: "{text}"
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[prompt]
        )
        if not response or not response.text:
            raise ValueError("Empty response from Gemini")

        raw = response.text
        start = raw.find("{")
        end = raw.rfind("}") + 1

        if start == -1 or end <= start:
            raise ValueError("No valid JSON found in response")

        return json.loads(raw[start:end])
    except Exception as e:
        logger.error(f"Gemini processing error: {e}")
        raise

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
    severity = "Low"
    
    sexual_terms = ["penis", "sex", "come sit", "touch me", "nude", "kiss", "send pic", "bed", "pic", "nudes"]
    grooming_terms = ["special", "only you", "don't tell", "our secret", "nobody needs to know", "you're mature"]
    threat_terms = ["kill", "hurt", "punch", "stab", "die", "death"]
    
    has_sexual = any(w in t for w in sexual_terms)
    has_grooming = any(w in t for w in grooming_terms)
    has_threat = any(w in t for w in threat_terms)
    
    if has_sexual:
        labels["sexual_content"] = True
        score = max(score, 75)
    
    if has_sexual and has_grooming:
        labels["grooming"] = True
        labels["manipulation"] = True
        score = max(score, 85)
    elif has_grooming:
        labels["grooming"] = True
        labels["manipulation"] = True
        score = max(score, 80)
    
    if has_sexual or has_grooming:
        labels["harassment"] = True
    
    if has_threat:
        labels["violence"] = True
        score = max(score, 75)
    
    if score >= 90:
        severity = "Critical"
    elif score >= 70:
        severity = "High"
    elif score >= 40:
        severity = "Medium"
    
    return {
        "risk_score": score,
        "severity_level": severity,
        "detected_labels": labels,
        "why_harmful": "This message contains concerning language targeting a minor. Trust your instincts.",
        "victim_support_message": "You did nothing wrong. This is not okay, and you deserve to feel safe.",
        "safe_response_steps": [
            "Do not reply",
            "Block the sender immediately",
            "Tell a trusted adult right away"
        ],
        "dashboard_summary": {
            "risk_overview": "This message shows patterns of concern.",
            "primary_concerns": [k for k, v in labels.items() if v],
            "intent_detected": "The sender may be trying to build trust before escalating.",
            "recommended_action": "Block this person and tell a parent or school counselor.",
            "parent_visibility": score >= 70
        }
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
        msg["Subject"] = "⚠ CareCloud Safety Alert"

        msg.attach(MIMEText(
            f"High-risk content detected.\n\nMessage:\n{text}\n\nRisk Score: {score}%",
            "plain"
        ))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        logger.error(f"Email failed: {e}")

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
        logger.error(f"Gemini failed, using local fallback: {e}")
        gemini_data = local_fallback(text)

    final_score = max(
        perspective.get("toxicity", 0),
        gemini_data.get("risk_score", 0)
    )

    detected = gemini_data.get("detected_labels", {})

    # Enforce risk score requirements
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

    dashboard_summary = gemini_data.get("dashboard_summary", {
        "risk_overview": "Analysis complete.",
        "primary_concerns": [k for k, v in detected.items() if v],
        "intent_detected": "Review the detected labels above.",
        "recommended_action": "Follow the safety steps provided.",
        "parent_visibility": final_score >= 70
    })

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": detected,
        "explanation": gemini_data.get("why_harmful", "Analysis complete."),
        "victim_support_message": gemini_data.get("victim_support_message", "Stay safe and talk to someone you trust."),
        "safe_response_steps": gemini_data.get("safe_response_steps", ["Do not reply", "Block sender", "Tell an adult"]),
        "dashboard_summary": dashboard_summary,
        "parent_alert_required": final_score >= 80
    })

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
