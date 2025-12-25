import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import (
    Flask, render_template, request, jsonify,
    session, redirect, url_for, flash
)

import google.generativeai as genai

# =====================================================
# APP SETUP
# =====================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "carecloud-dev-key")

# =====================================================
# ENV VARIABLES
# =====================================================
PERSPECTIVE_API_KEY = os.environ.get("PERSPECTIVE_API_KEY")
GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI")
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

# =====================================================
# GEMINI SETUP
# =====================================================
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini = genai.GenerativeModel("gemini-pro")
else:
    gemini = None

# =====================================================
# AUTH ROUTES
# =====================================================
@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            flash("Invalid login details")
            return redirect(url_for("login"))

        # demo session user
        session["user"] = {
            "name": "Student",
            "email": email,
            "parent_email": email
        }
        return redirect(url_for("dashboard"))

    return render_template("login.html", mode="login")

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        parent_email = request.form.get("parent_email")

        if not all([name, email, password, parent_email]):
            flash("All fields are required")
            return redirect(url_for("signup"))

        session["user"] = {
            "name": name,
            "email": email,
            "parent_email": parent_email
        }
        return redirect(url_for("dashboard"))

    return render_template("login.html", mode="signup")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# =====================================================
# DASHBOARD
# =====================================================
@app.route("/dashboard")
def dashboard():
    user = session.get("user")
    if not user:
        return redirect(url_for("login"))

    history = []
    return render_template("dashboard.html", user=user, history=history)

# =====================================================
# PERSPECTIVE API
# =====================================================
def perspective_analyze(text):
    if not PERSPECTIVE_API_KEY:
        return {}

    try:
        url = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
        payload = {
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {
                "TOXICITY": {},
                "INSULT": {},
                "THREAT": {},
                "IDENTITY_ATTACK": {},
                "SEXUALLY_EXPLICIT": {}
            }
        }

        r = requests.post(
            f"{url}?key={PERSPECTIVE_API_KEY}",
            json=payload,
            timeout=10
        )
        data = r.json()

        scores = {}
        for k, v in data.get("attributeScores", {}).items():
            scores[k.lower()] = int(v["summaryScore"]["value"] * 100)

        return scores
    except Exception:
        return {}

# =====================================================
# GEMINI SAFETY ANALYSIS (STRONG PROMPT)
# =====================================================
def gemini_analyze(text):
    if not gemini:
        return default_gemini_response()

    prompt = f"""
You are CareCloud Guardian AI.

Audience: children and teenagers.
Goal: identify harmful intent, even if subtle.

Detect:
- bullying, insults, humiliation
- threats or intimidation
- manipulation or gaslighting
- grooming or coercion
- sexual or suggestive language
- hate speech or identity attacks
- emotional abuse
- encouragement of self-harm

Message:
\"\"\"{text}\"\"\"

Return ONLY JSON:

{{
  "gemini_score": 0-100,
  "detected_labels": {{
    "harassment": true/false,
    "threats": true/false,
    "sexual_content": true/false,
    "grooming": true/false,
    "manipulation": true/false,
    "emotional_abuse": true/false,
    "hate_speech": true/false,
    "self_harm_risk": true/false
  }},
  "why_harmful": "short child-friendly explanation",
  "victim_support": "supportive calming message",
  "safety_steps": ["step1","step2","step3"],
  "parent_guidance": "guardian advice"
}}
"""

    try:
        res = gemini.generate_content(prompt).text
        start = res.find("{")
        end = res.rfind("}") + 1
        return json.loads(res[start:end])
    except Exception:
        return default_gemini_response()

def default_gemini_response():
    return {
        "gemini_score": 0,
        "detected_labels": {},
        "why_harmful": "No clear harm detected.",
        "victim_support": "You are safe. If something feels wrong, talk to someone you trust.",
        "safety_steps": ["Pause", "Reflect", "Ask for help"],
        "parent_guidance": "Stay observant and supportive."
    }

# =====================================================
# EMAIL ALERT
# =====================================================
def send_parent_alert(message, score):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = MAIL_USERNAME
        msg["To"] = MAIL_USERNAME
        msg["Subject"] = "⚠ CareCloud Safety Alert"

        body = f"""
High risk content detected.

Message:
{message}

Risk Score: {score}%
"""
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
    except Exception:
        pass

# =====================================================
# ANALYZE ENDPOINT
# =====================================================
@app.route("/analyze", methods=["POST"])
def analyze():
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    perspective = perspective_analyze(text)
    gemini_data = gemini_analyze(text)

    final_score = max(
        perspective.get("toxicity", 0),
        gemini_data.get("gemini_score", 0)
    )

    severity = "High" if final_score >= 70 else "Medium" if final_score >= 40 else "Low"

    if final_score >= 80:
        send_parent_alert(text, final_score)

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": gemini_data["detected_labels"],
        "explanation": gemini_data["why_harmful"],
        "victim_support_message": gemini_data["victim_support"],
        "safe_response_steps": gemini_data["safety_steps"],
        "parent_alert_required": final_score >= 80,
        "support_panel_content": {
            "context_summary": gemini_data["why_harmful"],
            "student_guidance": gemini_data["victim_support"],
            "parent_guidance": gemini_data["parent_guidance"],
            "next_steps": gemini_data["safety_steps"]
        }
    })

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
