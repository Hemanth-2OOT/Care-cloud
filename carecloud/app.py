import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename

import google.generativeai as genai

# -----------------------------
# Flask App Setup
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# -----------------------------
# Environment Variables
# -----------------------------
PERSPECTIVE_API_KEY = os.environ.get("PERSPECTIVE_API_KEY")
GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI")
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

# -----------------------------
# Gemini Setup
# -----------------------------
genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-pro")

# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def home():
    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    # Ensure user exists for template
    user = {
        "name": session.get("username", "Student")
    }
    history = []
    return render_template("dashboard.html", user=user, history=history)


# -----------------------------
# Perspective API Analysis
# -----------------------------
def perspective_analyze(text):
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

    response = requests.post(
        f"{url}?key={PERSPECTIVE_API_KEY}",
        json=payload,
        timeout=10
    )

    data = response.json()
    scores = {}

    for key, value in data.get("attributeScores", {}).items():
        scores[key.lower()] = round(
            value["summaryScore"]["value"] * 100
        )

    return scores


# -----------------------------
# Gemini Deep Safety Analysis
# -----------------------------
def gemini_analyze(text):
    prompt_lines = [
        "You are CareCloud Guardian AI.",
        "Your mission is to protect children and teenagers online.",
        "",
        "CRITICAL SAFETY RULES:",
        "- Treat all content as if read by a vulnerable child.",
        "- Detect bullying, harassment, humiliation, insults.",
        "- Detect threats, violence, intimidation.",
        "- Detect grooming, manipulation, coercion.",
        "- Detect sexual content, especially involving minors.",
        "- Detect emotional abuse and self-harm encouragement.",
        "",
        "Analyze the message below:",
        text,
        "",
        "Return ONLY valid JSON in this format:",
        "{",
        ' "gemini_score": number (0-100),',
        ' "detected_labels": {',
        '   "harassment": true/false,',
        '   "threats": true/false,',
        '   "sexual_content": true/false,',
        '   "grooming": true/false,',
        '   "manipulation": true/false,',
        '   "emotional_abuse": true/false,',
        '   "hate_speech": true/false,',
        '   "violence": true/false,',
        '   "self_harm_risk": true/false',
        ' },',
        ' "why_harmful": "string",',
        ' "victim_support": "string",',
        ' "safety_steps": ["step1", "step2"],',
        ' "parent_guidance": "string"',
        "}"
    ]

    prompt = "\n".join(prompt_lines)

    response = gemini.generate_content(prompt).text

    start = response.find("{")
    end = response.rfind("}") + 1

    return json.loads(response[start:end])


# -----------------------------
# Email Alert (SMTP)
# -----------------------------
def send_parent_alert(message, score):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return

    msg = MIMEMultipart()
    msg["From"] = MAIL_USERNAME
    msg["To"] = MAIL_USERNAME
    msg["Subject"] = "⚠️ CareCloud Alert: High Risk Content Detected"

    body = f"""
High-risk content detected.

Message:
{message}

Risk Score: {score}%

Please review and support the child.
"""

    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)


# -----------------------------
# Analyze Endpoint
# -----------------------------
@app.route("/analyze", methods=["POST"])
def analyze():
    text = request.form.get("text", "").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Perspective
    perspective_scores = perspective_analyze(text)

    # Gemini
    gemini_data = gemini_analyze(text)

    # Combine Scores
    final_score = max(
        perspective_scores.get("toxicity", 0),
        gemini_data.get("gemini_score", 0)
    )

    severity = (
        "High" if final_score >= 70 else
        "Medium" if final_score >= 40 else
        "Low"
    )

    if final_score >= 80:
        send_parent_alert(text, final_score)

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": gemini_data.get("detected_labels", {}),
        "explanation": gemini_data.get("why_harmful", ""),
        "victim_support_message": gemini_data.get("victim_support", ""),
        "safe_response_steps": gemini_data.get("safety_steps", []),
        "parent_alert_required": final_score >= 80,
        "support_panel_content": {
            "context_summary": gemini_data.get("why_harmful", ""),
            "student_guidance": gemini_data.get("victim_support", ""),
            "parent_guidance": gemini_data.get("parent_guidance", ""),
            "next_steps": gemini_data.get("safety_steps", [])
        }
    })


# -----------------------------
# Run App
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
