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

    prompt = f"""You are CareCloud Safety AI. Protect children and teenagers from harmful messages.
Assume the reader is always a vulnerable minor.

CORE PRINCIPLES (STRICT):
• Analyze INTENT, not just words
• Casual, joking, or slang language can still be harmful
• Never downplay harm
• False negatives are NOT acceptable

LABEL DEFINITIONS:
- harassment: Insults, humiliation, degrading language
- profanity: Vulgar, explicit, or offensive language
- hate_speech: Attacks on identity, family, race, gender, religion
- sexual_content: Sexual language, body parts, or sexual acts
- grooming: Flattery, trust-building, or normalization with sexual intent
- manipulation: Pressure, coercion, secrecy, emotional steering
- threats: Direct or implied threats of harm
- violence: Any encouragement/threat of physical harm (hit, slap, beat, kill)
- emotional_abuse: Shaming, intimidation, guilt, psychological harm
- self_harm_risk: Encouraging or expressing self-harm

SCORING RULES (MANDATORY):
• violence/threats → risk_score ≥ 50
• harassment or emotional_abuse → risk_score ≥ 40
• sexual_content → risk_score ≥ 70
• grooming or coercion → risk_score ≥ 80
• If ANY label true → NOT SAFE

Return STRICT JSON ONLY:
{{
  "risk_score": number,
  "severity_level": "Low | Medium | High | Critical",
  "detected_labels": {{
    "harassment": boolean,
    "profanity": boolean,
    "hate_speech": boolean,
    "sexual_content": boolean,
    "grooming": boolean,
    "manipulation": boolean,
    "threats": boolean,
    "violence": boolean,
    "emotional_abuse": boolean,
    "self_harm_risk": boolean
  }},
  "context_summary": "Explain clearly why THIS message is harmful",
  "support_for_user": "Supportive message tailored to this situation",
  "instructions": ["Action 1", "Action 2", "Action 3"]
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
    score = 10
    severity = "Low"
    
    sexual_terms = ["penis", "sex", "come sit", "touch me", "nude", "kiss", "send pic", "bed", "pic", "nudes"]
    grooming_terms = ["special", "only you", "don't tell", "our secret", "nobody needs to know", "you're mature"]
    threat_terms = ["kill", "hurt", "punch", "stab", "die", "death", "harm", "attack"]
    insult_terms = ["stupid", "dumb", "idiot", "loser", "worthless", "ugly", "fat"]
    coercion_terms = ["you have to", "you must", "you need to", "i'll tell everyone", "everyone will know", "you owe me"]
    hate_terms = ["hate all", "stupid", "inferior", "trash", "dirty"]
    profanity_terms = ["f***", "s***", "a**", "b****", "h***", "damn", "hell"]
    
    has_sexual = any(w in t for w in sexual_terms)
    has_grooming = any(w in t for w in grooming_terms)
    has_threat = any(w in t for w in threat_terms)
    has_insult = any(w in t for w in insult_terms)
    has_coercion = any(w in t for w in coercion_terms)
    has_hate = any(w in t for w in hate_terms)
    has_profanity = any(w in t for w in profanity_terms)
    has_self_harm = any(w in t for w in ["kill myself", "hurt myself", "die", "suicide"])
    
    if has_threat:
        labels["threats"] = True
        labels["violence"] = True
        score = max(score, 50)
    
    if has_sexual:
        labels["sexual_content"] = True
        score = max(score, 75)
    
    if has_sexual and has_grooming:
        labels["grooming"] = True
        labels["manipulation"] = True
        labels["harassment"] = True
        score = max(score, 85)
    elif has_grooming:
        labels["grooming"] = True
        labels["manipulation"] = True
        score = max(score, 80)
    
    if has_profanity:
        labels["profanity"] = True
        score = max(score, 25)
    
    if has_insult:
        labels["harassment"] = True
        score = max(score, 40)
    
    if has_coercion:
        labels["coercion"] = True
        labels["manipulation"] = True
        score = max(score, 80)
    
    if has_hate:
        labels["hate_speech"] = True
        score = max(score, 50)
    
    if has_self_harm:
        labels["self_harm_risk"] = True
        score = max(score, 70)
    
    if score >= 90:
        severity = "Critical"
    elif score >= 70:
        severity = "High"
    elif score >= 40:
        severity = "Medium"
    
    context_summary = ""
    support = ""
    instructions = []
    
    if has_sexual and has_grooming:
        context_summary = "This message uses flattery mixed with sexual language. It's a common grooming tactic where someone tries to make you feel special while also testing your boundaries."
        support = "You are not overreacting. Adults who mix compliments with sexual interest are trying to manipulate you. You deserve adults who respect your safety."
        instructions = ["Screenshot this message (don't delete it)", "Block this person immediately on all platforms", "Show a trusted adult or school counselor right now"]
    elif has_coercion:
        context_summary = "This message uses pressure or threats to force you to do something. This is coercion and is a form of control."
        support = "You have the right to say no. Nobody can force you into something you don't want to do. Tell a trusted adult about this pressure."
        instructions = ["Don't give in to the pressure", "Tell a trusted adult immediately", "Block this person if you feel unsafe"]
    elif has_threat:
        context_summary = "This message contains threats or language meant to frighten or harm you."
        support = "Threats are serious. Your safety matters, and you don't deserve to be treated this way."
        instructions = ["Take threats seriously (even if they seem joking)", "Save evidence and report to platform", "Tell a school official or parent immediately"]
    elif has_sexual:
        context_summary = "This message contains explicit sexual language directed at a minor. This is predatory behavior."
        support = "You didn't do anything to cause this. Sexual messages from adults to minors are always wrong."
        instructions = ["Do not respond or engage", "Block and report on this platform", "Tell a trusted adult immediately"]
    elif has_grooming:
        context_summary = "This message uses special attention and flattery to make you feel unique. This is a grooming pattern designed to isolate you."
        support = "Real caring adults in your life already support you. Suspicious online attention is a warning sign, not a compliment."
        instructions = ["Remember: They don't actually know you", "Stop responding to this person", "Tell a parent, school counselor, or call NCMEC (1-800-843-5678)"]
    elif has_insult:
        context_summary = "This message uses insulting or degrading language to hurt or humiliate you."
        support = "Words designed to hurt can affect us, but you're not what they say. You have value."
        instructions = ["Don't engage or respond to insults", "Block this person", "Talk to someone you trust about how this made you feel"]
    elif has_self_harm:
        context_summary = "This message expresses or encourages self-harm or suicide. This is a crisis situation."
        support = "If you're having these thoughts, reach out for help immediately. You matter and your life has value."
        instructions = ["Call the 988 Suicide & Crisis Lifeline immediately", "Text HOME to 741741", "Tell a trusted adult or go to an emergency room"]
    else:
        context_summary = "This message has raised some concerns."
        support = "Your instincts about uncomfortable messages are important."
        instructions = ["Take a break from responding", "Talk to someone you trust", "You can block or mute anytime"]
    
    return {
        "risk_score": score,
        "severity_level": severity,
        "detected_labels": labels,
        "context_summary": context_summary,
        "support_for_user": support,
        "instructions": instructions
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

# =====================================================
# RESPONSE GENERATORS
# =====================================================
def generate_user_summary(labels, severity):
    if labels.get("sexual_content"):
        return "This message contains sexual language that is unsafe for minors."
    if labels.get("grooming"):
        return "This message attempts to build inappropriate trust or intimacy."
    if labels.get("threats") or labels.get("violence"):
        return "This message includes threats or violent language."
    if labels.get("harassment") or labels.get("profanity"):
        return "This message contains abusive or hostile language."
    if labels.get("emotional_abuse"):
        return "This message may cause emotional harm."
    return "No major safety risks were detected."

def generate_instructions(labels, severity):
    if labels.get("sexual_content") or labels.get("grooming"):
        return [
            "Do not reply",
            "Block the sender immediately",
            "Tell a trusted adult right away"
        ]
    if labels.get("threats") or labels.get("violence"):
        return [
            "Do not engage",
            "Save evidence",
            "Report to platform or authorities"
        ]
    if labels.get("harassment") or labels.get("profanity"):
        return [
            "Mute or block the sender",
            "Do not escalate",
            "Take a break if needed"
        ]
    return [
        "Continue being cautious online",
        "Trust your instincts"
    ]

def generate_support_message(labels):
    if any(labels.values()):
        return "You did nothing wrong. Harmful messages are not your fault."
    return "Everything looks okay. Stay safe online."

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

    return jsonify({
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": detected,
        "summary": generate_user_summary(detected, severity),
        "support_message": generate_support_message(detected),
        "instructions": generate_instructions(detected, severity),
        "content_safe": not any(detected.values()),
        "parent_alert_required": final_score >= 80
    })

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=False)
