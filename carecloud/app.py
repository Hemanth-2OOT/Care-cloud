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

    prompt = f"""You are CareCloud Safety AI. Analyze ONLY this message as if sent to a minor.

Your output MUST be fully CONTEXT-AWARE. Do NOT use generic text.
- Explain WHY it is harmful (specific words, tone, intent)
- Generate support that matches THIS situation
- Generate instructions tailored to THIS risk level
- NEVER repeat same instructions for every message
- NEVER say "This is not okay" without explaining why

CRITICAL: Assume recipient is a minor. Detect grooming, manipulation, hidden sexual intent.

LABEL DEFINITIONS:
- sexual_content: explicit language, body parts, invitations, sexualized compliments
- grooming: flattery + sexual intent, normalization, secrecy requests
- manipulation: "You're special", emotional steering, making child feel responsible
- harassment: unwanted sexual attention, objectifying language
- emotional_abuse: shaming, guilt-tripping, fear, control
- violence: threats, intimidation, harm
- self_harm_risk: encouraging self-harm or suicide

RULES:
• sexual_content = true → risk_score ≥ 70
• grooming = true → risk_score ≥ 80
• If ANY label true → NOT SAFE
• Friendly tone ≠ safe. Compliments + sexual = HIGH RISK

Return STRICT JSON ONLY (no extra text):
{{
  "risk_score": number,
  "severity_level": "Low | Medium | High | Critical",
  "detected_labels": {{
    "sexual_content": boolean,
    "grooming": boolean,
    "harassment": boolean,
    "manipulation": boolean,
    "emotional_abuse": boolean,
    "violence": boolean,
    "self_harm_risk": boolean
  }},
  "context_summary": "2-3 lines: what this message does, why unsafe",
  "intent_detected": "Hidden/implied intent in simple language",
  "support_for_user": "Empathetic message tailored to THIS exact situation",
  "why_harmful": "Explanation for teenager (specific to message)",
  "victim_support_message": "Calming reassurance (never blame)",
  "safe_response_steps": [
    "Specific action 1 for THIS message",
    "Specific action 2 for THIS message",
    "Specific action 3 for THIS message"
  ]
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
    
    context_summary = ""
    intent = ""
    support = ""
    steps = []
    
    if has_sexual and has_grooming:
        context_summary = "This message uses flattery mixed with sexual language. It's a common grooming tactic where someone tries to make you feel special while also testing your boundaries."
        intent = "The sender is attempting to normalize sexual conversation while building your trust, gradually escalating the relationship toward sexual content."
        support = "You are not overreacting. Adults who mix compliments with sexual interest are trying to manipulate you. You deserve adults who respect your safety."
        steps = [
            "Screenshot this message (don't delete it)",
            "Block this person immediately on all platforms",
            "Show a trusted adult or school counselor right now"
        ]
    elif has_grooming:
        context_summary = "This message uses special attention and flattery to make you feel unique and understood. This is a grooming pattern designed to isolate you."
        intent = "The sender wants you to feel like they 'get you' in a way others don't, making you less likely to tell adults about the relationship."
        support = "Real caring adults in your life already support you. Suspicious online attention is a warning sign, not a compliment."
        steps = [
            "Remember: They don't actually know you",
            "Stop responding to this person",
            "Tell a parent, school counselor, or call NCMEC (1-800-843-5678)"
        ]
    elif has_sexual:
        context_summary = "This message contains explicit sexual language directed at a minor. This is predatory behavior."
        intent = "The sender is testing if you'll engage with sexual content, or trying to shock/manipulate you into responding."
        support = "You didn't do anything to cause this. Sexual messages from adults to minors are always wrong."
        steps = [
            "Do not respond or engage",
            "Block and report on this platform",
            "Tell a trusted adult immediately"
        ]
    elif has_threat:
        context_summary = "This message contains threats or language meant to frighten or harm you."
        intent = "The sender is trying to control or intimidate you through fear."
        support = "Threats are serious. Your safety matters, and you don't deserve to be treated this way."
        steps = [
            "Take threats seriously (even if they seem joking)",
            "Save evidence and report to platform",
            "Tell a school official or parent immediately"
        ]
    else:
        context_summary = "This message has raised some concerns. Trust your gut if something feels off."
        intent = "Possible concerning intent detected."
        support = "Your instincts about uncomfortable messages are important."
        steps = [
            "Take a break from responding",
            "Talk to someone you trust about how it made you feel",
            "You can block or mute anytime"
        ]
    
    return {
        "risk_score": score,
        "severity_level": severity,
        "detected_labels": labels,
        "context_summary": context_summary,
        "intent_detected": intent,
        "support_for_user": support,
        "why_harmful": context_summary,
        "victim_support_message": support,
        "safe_response_steps": steps
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

    explanation = gemini_data.get("why_harmful") or gemini_data.get("context_summary", "Analysis complete.")
    support_msg = gemini_data.get("victim_support_message") or gemini_data.get("support_for_user", "Stay safe and talk to someone you trust.")
    steps = gemini_data.get("safe_response_steps", ["Do not reply", "Block sender", "Tell an adult"])

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": detected,
        "explanation": explanation,
        "victim_support_message": support_msg,
        "safe_response_steps": steps,
        "context_summary": gemini_data.get("context_summary"),
        "intent_detected": gemini_data.get("intent_detected"),
        "parent_alert_required": final_score >= 80
    })

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
