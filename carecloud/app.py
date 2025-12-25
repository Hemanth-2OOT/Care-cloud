import os
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from flask import (
    Flask, render_template, request,
    jsonify, session, redirect, url_for, flash
)

import google.generativeai as genai

# =====================================================
# APP SETUP
# =====================================================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "carecloud-dev-secret")

# =====================================================
# ENV VARIABLES
# =====================================================
PERSPECTIVE_API_KEY = os.environ.get("PERSPECTIVE_API_KEY")
GEMINI_API_KEY = os.environ.get("AI_INTEGRATIONS_GEMINI")

MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

PORT = int(os.environ.get("PORT", 5000))

# =====================================================
# GEMINI SETUP
# =====================================================
genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-pro")

# =====================================================
# HELPERS
# =====================================================
def logged_in():
    return "user" in session


def local_analyze(text):
    text = text.lower()

    labels = {
        "profanity": False,
        "harassment": False,
        "insult": False,
        "hate_speech": False,
        "threat": False,
        "sexual_content": False,
        "grooming": False,
        "emotional_abuse": False,
        "manipulation": False,
        "violence": False,
        "self_harm_risk": False
    }

    score = 10
    severity = "Low"
    explanation = "This content appears safe."
    support = "Everything looks okay. Stay safe!"
    steps = ["Continue being positive online."]
    guidance = "No action needed."

    # Logic
    if any(w in text for w in ["die", "kill myself", "suicide", "end it"]):
        labels["self_harm_risk"] = True
        labels["emotional_abuse"] = True
        score = 95
        severity = "Critical"
        explanation = "This message indicates a risk of self-harm."
        support = "You are precious. Please call a helpline or talk to an adult immediately."
        steps = ["Call 988 or a local helpline", "Talk to a parent now", "Do not be alone"]
        guidance = "Immediate intervention required. Support the child."

    elif any(w in text for w in ["kill you", "punch", "hurt", "beat", "gun", "knife", "die"]):
        labels["violence"] = True
        labels["threat"] = True
        score = 90
        severity = "Critical"
        explanation = "This message contains threats of violence."
        support = "This is not okay. You have the right to be safe."
        steps = ["Block the user", "Report to platform", "Tell an adult"]
        guidance = "Assess safety. Report threats to authorities if serious."

    elif any(w in text for w in ["hate", "ugly", "stupid", "idiot", "fat", "loser"]):
        labels["hate_speech"] = True
        labels["harassment"] = True
        labels["insult"] = True
        labels["emotional_abuse"] = True
        score = 75
        severity = "High"
        explanation = "This message contains insults and hate speech."
        support = "Their words reflect them, not you. You are worthy."
        steps = ["Ignore the message", "Block the sender", "Talk to a friend"]
        guidance = "Discuss how to handle bullies. Reassure the child."

    elif any(w in text for w in ["sex", "nude", "send pic"]):
        labels["sexual_content"] = True
        labels["grooming"] = True
        score = 85
        severity = "High"
        explanation = "This message contains inappropriate sexual content."
        support = "This is not appropriate. You don't have to respond."
        steps = ["Block immediately", "Do not share photos", "Tell an adult"]
        guidance = "Check for grooming signs. Report user."

    return {
        "risk_score": score,
        "severity_level": severity,
        "detected_labels": labels,
        "why_harmful": explanation,
        "victim_support_message": support,
        "safe_response_steps": steps,
        "parent_guidance": guidance
    }


# =====================================================
# AUTH ROUTES
# =====================================================
@app.route("/", methods=["GET"])
def home():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        # Simple demo auth (no DB yet)
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


# =====================================================
# DASHBOARD
# =====================================================
@app.route("/dashboard")
def dashboard():
    if not logged_in():
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        user=session["user"],
        history=[]
    )


# =====================================================
# PERSPECTIVE API
# =====================================================
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

    r = requests.post(
        f"{url}?key={PERSPECTIVE_API_KEY}",
        json=payload,
        timeout=8
    )

    data = r.json()
    scores = {}

    for k, v in data.get("attributeScores", {}).items():
        scores[k.lower()] = int(v["summaryScore"]["value"] * 100)

    return scores


# =====================================================
# GEMINI ANALYSIS (HEAVILY FINE-TUNED)
# =====================================================
def gemini_analyze(text):
    prompt = f"""
You are CareCloud Safety AI.

Your role is to protect children and teenagers from harmful online content
in a calm, non-judgmental, emotionally safe way.

You are NOT a police system.
You are NOT here to shame, punish, or scare.
You are here to:
- Identify harm
- Explain risk gently
- Support the victim
- Guide safe next steps

Always assume the content may be read by a vulnerable child.

--------------------------------------------------
ANALYSIS GOALS
--------------------------------------------------
When analyzing content, you must:

1. Detect harmful INTENT, not just words
2. Consider emotional impact on a child
3. Be conservative but protective
4. Prefer false-positive safety over silence
5. NEVER freeze, refuse, or moralize

--------------------------------------------------
LABEL DEFINITIONS (INTENT-BASED)
--------------------------------------------------
You must assign labels ONLY when intent is present.

Use these labels:

- profanity:
  Swear words or vulgar language without direct targeting

- harassment:
  Repeated or targeted insulting language meant to hurt

- insult:
  Single-instance humiliation or name-calling

- hate_speech:
  Attacks based on identity (race, gender, religion, disability, etc.)

- threat:
  Any suggestion of harm, violence, or intimidation

- sexual_content:
  Sexual language inappropriate for minors

- grooming:
  Manipulation, trust-building, secrecy, or sexual undertones involving minors

- emotional_abuse:
  Gaslighting, humiliation, worthlessness, control, fear

- manipulation:
  Pressure, coercion, guilt-tripping, psychological control

- violence:
  Encouraging or describing physical harm

- self_harm_risk:
  Encouragement or normalization of self-harm or suicide

--------------------------------------------------
SCORING RULES
--------------------------------------------------
Generate a risk score from 0–100:

0–20   → Safe
21–39  → Mild concern
40–69  → Harmful
70–89  → High risk
90–100 → Critical risk

Score must reflect:
- emotional harm
- vulnerability
- severity
- intent

--------------------------------------------------
WHAT TO SHOW THE CHILD (USER)
--------------------------------------------------
Use SIMPLE, KIND, SUPPORTIVE language.

Never say:
❌ "You are wrong"
❌ "This is illegal"
❌ "You should be punished"

Always say things like:
✅ "This message could be hurtful"
✅ "You didn’t do anything wrong"
✅ "It’s okay to ask for help"

--------------------------------------------------
OUTPUT FORMAT (STRICT JSON)
--------------------------------------------------
Return ONLY valid JSON in this format:

{{
  "risk_score": number,
  "severity_level": "Low | Medium | High | Critical",

  "detected_labels": {{
    "profanity": true/false,
    "harassment": true/false,
    "insult": true/false,
    "hate_speech": true/false,
    "threat": true/false,
    "sexual_content": true/false,
    "grooming": true/false,
    "emotional_abuse": true/false,
    "manipulation": true/false,
    "violence": true/false,
    "self_harm_risk": true/false
  }},

  "why_harmful": "Explain clearly WHY this message is harmful in child-safe language. No blame.",

  "victim_support_message": "A comforting message reminding the child they are not alone and did nothing wrong.",

  "safe_response_steps": [
    "Step 1 – what the child can do",
    "Step 2 – another safe action",
    "Step 3 – optional support step"
  ],

  "parent_guidance": "Calm, supportive advice for parents. Never judgmental."
}}

--------------------------------------------------
IMPORTANT RULES
--------------------------------------------------
- Never hallucinate crimes
- Never include explicit content
- Never instruct retaliation
- Never suggest punishment
- Always prioritize emotional safety
- Always finish the analysis

Message to analyze:
\"\"\"{text}\"\"\"
"""

    response = gemini.generate_content(prompt).text
    start = response.find("{")
    end = response.rfind("}") + 1
    return json.loads(response[start:end])


# =====================================================
# EMAIL ALERT
# =====================================================
def send_parent_alert(text, score, parent_email):
    if not parent_email or not MAIL_USERNAME or not MAIL_PASSWORD:
        return

    msg = MIMEMultipart()
    msg["From"] = MAIL_USERNAME
    msg["To"] = parent_email
    msg["Subject"] = "⚠ CareCloud Alert: High Risk Content"

    msg.attach(MIMEText(
        f"""
High-risk content detected.

Message:
{text}

Risk Score: {score}%

Please provide emotional support.
""",
        "plain"
    ))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.send_message(msg)


# =====================================================
# ANALYZE ENDPOINT (NEVER HANGS)
# =====================================================
@app.route("/analyze", methods=["POST"])
def analyze():
    if not logged_in():
        return jsonify({"error": "Unauthorized"}), 401

    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        perspective = perspective_analyze(text)
    except Exception:
        perspective = {}

    try:
        gemini_data = gemini_analyze(text)
    except Exception:
        gemini_data = local_analyze(text)

    final_score = max(
        perspective.get("toxicity", 0),
        gemini_data.get("risk_score", 0)
    )

    severity = gemini_data.get("severity_level")
    if not severity:
        severity = (
            "High" if final_score >= 70
            else "Medium" if final_score >= 40
            else "Low"
        )

    if final_score >= 80:
        send_parent_alert(
            text,
            final_score,
            session["user"].get("parent_email")
        )

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": gemini_data["detected_labels"],
        "explanation": gemini_data["why_harmful"],
        "victim_support_message": gemini_data.get("victim_support_message", gemini_data.get("victim_support")),
        "safe_response_steps": gemini_data.get("safe_response_steps", gemini_data.get("safety_steps", [])),
        "parent_alert_required": final_score >= 80,
        "support_panel_content": {
            "context_summary": gemini_data["why_harmful"],
            "student_guidance": gemini_data.get("victim_support_message", gemini_data.get("victim_support")),
            "parent_guidance": gemini_data["parent_guidance"],
            "next_steps": gemini_data.get("safe_response_steps", gemini_data.get("safety_steps", []))
        }
    })


# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
