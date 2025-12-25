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

    # Strictly the 7 labels requested
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
    explanation = "This content appears safe."
    support = "Everything looks okay. Stay safe!"
    steps = ["Continue being positive online."]
    guidance = "No action needed."

    # Logic mappings
    if any(w in text for w in ["die", "kill myself", "suicide", "end it"]):
        labels["self_harm_risk"] = True
        labels["emotional_abuse"] = True # Self-harm often correlates with emotional distress
        score = 95
        severity = "Critical"
        explanation = "This message indicates a risk of self-harm."
        support = "You are precious. Please call a helpline or talk to an adult immediately."
        steps = ["Call 988 or a local helpline", "Talk to a parent now", "Do not be alone"]
        guidance = "Immediate intervention required. Support the child."

    elif any(w in text for w in ["kill you", "punch", "hurt", "beat", "gun", "knife", "die"]):
        labels["violence"] = True
        labels["harassment"] = True
        score = 90
        severity = "Critical"
        explanation = "This message contains threats of violence."
        support = "This is not okay. You have the right to be safe."
        steps = ["Block the user", "Report to platform", "Tell an adult"]
        guidance = "Assess safety. Report threats to authorities if serious."

    elif any(w in text for w in ["hate", "ugly", "stupid", "idiot", "fat", "loser"]):
        labels["harassment"] = True
        labels["emotional_abuse"] = True
        score = 75
        severity = "High"
        explanation = "This message contains insults and harassment."
        support = "Their words reflect them, not you. You are worthy."
        steps = ["Ignore the message", "Block the sender", "Talk to a friend"]
        guidance = "Discuss how to handle bullies. Reassure the child."

    elif any(w in text for w in ["sex", "nude", "send pic"]):
        labels["sexual_content"] = True
        labels["grooming"] = True # Strict rule: assume grooming risk in messages
        score = 85
        severity = "High"
        explanation = "This message contains inappropriate sexual content."
        support = "This is not appropriate. You don't have to respond."
        steps = ["Block immediately", "Do not share photos", "Tell an adult"]
        guidance = "Check for grooming signs. Report user."

    # Consistency Check (Risk Score Rules)
    if labels["sexual_content"] and score < 70:
        score = 70
        severity = "High"
    if labels["grooming"] and score < 80:
        score = 80
        severity = "Critical" # 80 is High/Critical border, prompt says 70-89 High, 90-100 Critical. 80 is High.
        if score >= 90: severity = "Critical"
        else: severity = "High"

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

Your job is to protect children and teenagers from harmful online messages.

This system is SAFETY-FIRST.
False negatives are NOT acceptable.

--------------------------------------------------
CRITICAL CONSISTENCY RULE (VERY IMPORTANT)
--------------------------------------------------
Your outputs MUST be logically consistent.

If risk_score >= 40:
- You MUST detect at least one harmful label
- You MUST explain why the content is harmful
- You MUST NOT say “safe” or “no risks detected”

If risk_score >= 70:
- sexual_content, harassment, grooming, or emotional_abuse
  MUST be evaluated VERY STRICTLY

If content contains:
- sexual acts
- explicit body parts
- invitations involving sex
THEN:
- sexual_content = true
- grooming = true IF the target could be a minor

--------------------------------------------------
ABSOLUTE RULES (DO NOT BREAK)
--------------------------------------------------
- Sexual language is NEVER safe for children
- Invitations to sexual acts = HIGH RISK
- Flirtation + explicit language = grooming risk
- “Cute + sexual act” = manipulation + sexual content
- Never downplay sexual harm

--------------------------------------------------
LABEL DEFINITIONS (MANDATORY)
--------------------------------------------------
sexual_content:
  Any explicit sexual language, body parts, or sexual acts

grooming:
  Flattery + sexual intent, invitations, or normalization of sexual behavior

harassment:
  Unwanted sexual advances or objectifying language

manipulation:
  Emotional pressure or normalization of inappropriate behavior

--------------------------------------------------
SCORING RULES (STRICT)
--------------------------------------------------
If sexual_content = true → minimum risk_score = 70
If grooming = true → minimum risk_score = 80

--------------------------------------------------
WHAT TO TELL THE CHILD
--------------------------------------------------
- Use calm, supportive language
- NEVER say “this is safe” if sexual content exists
- Always reassure the child they did nothing wrong

--------------------------------------------------
OUTPUT FORMAT (STRICT JSON ONLY)
--------------------------------------------------
Return ONLY valid JSON:

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

  "why_harmful": "Clear explanation of why this content is unsafe for a child",

  "victim_support_message": "Kind, reassuring message",

  "safe_response_steps": [
    "Block or mute the sender",
    "Do not reply",
    "Tell a trusted adult"
  ],

  "parent_guidance": "Supportive advice, not punishment"
}}

--------------------------------------------------
FINAL CHECK (SELF-VERIFY)
--------------------------------------------------
Before responding, verify:
- Do labels match the risk_score?
- Does explanation match detected labels?
- Is sexual content ever marked safe? (If yes → FIX IT)

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

    # ---------------------------------------------------------
    # CRITICAL SAFETY CONSISTENCY CHECK
    # ---------------------------------------------------------
    detected = gemini_data.get("detected_labels", {})
    any_harmful = any(detected.values())

    # 1. High Score MUST have a label
    if final_score >= 40 and not any_harmful:
        detected["harassment"] = True  # Fallback for unexplained high risk
        gemini_data["why_harmful"] = "Content flagged as high risk by safety filters."

    # 2. Severe Labels MUST have High Score
    severe_labels = ["sexual_content", "grooming", "violence", "self_harm_risk"]
    if any(detected.get(l) for l in severe_labels):
        if final_score < 70:
            final_score = 70

    # 3. Strict Severity Recalculation
    if final_score >= 90:
        severity = "Critical"
    elif final_score >= 70:
        severity = "High"
    elif final_score >= 40:
        severity = "Medium"
    else:
        severity = "Low"

    # 4. Explanation Consistency
    if final_score >= 40 and "safe" in gemini_data.get("why_harmful", "").lower():
        gemini_data["why_harmful"] = "Potential harm detected based on analysis scores."

    gemini_data["detected_labels"] = detected
    # ---------------------------------------------------------

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
