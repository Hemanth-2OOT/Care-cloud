import os
import json
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

import google.generativeai as genai

# =========================
# ENV + APP SETUP
# =========================
load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "carecloud-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///database.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


@app.route("/health")
def health():
    return "OK", 200


# =========================
# GEMINI PRO (FREE INDIA)
# =========================
GEMINI_API_KEY = os.getenv("AI_INTEGRATIONS_GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("AI_INTEGRATIONS_GEMINI_API_KEY is not set")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.0-pro")


# =========================
# DATABASE MODELS
# =========================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    parent_email = db.Column(db.String(100), nullable=False)

    analyses = db.relationship("Analysis", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    toxicity_score = db.Column(db.Integer)
    severity_level = db.Column(db.String(20))
    explanation = db.Column(db.Text)
    victim_support_message = db.Column(db.Text)
    safe_response_steps = db.Column(db.Text)
    labels = db.Column(db.Text)
    content_preview = db.Column(db.Text)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =========================
# HARD SAFETY RULES (INTENT)
# =========================
PROFANITY = [
    "fuck", "shit", "bitch", "ugly", "stupid", "asshole"
]

GROOMING_PATTERNS = [
    "come sit on my lap",
    "you are cute",
    "you are so mature",
    "our secret",
    "don’t tell your parents",
    "send me a picture",
    "i can take care of you",
    "i understand you better than others"
]


def detect_intent(text):
    t = text.lower()
    return {
        "profanity": any(w in t for w in PROFANITY),
        "grooming": any(p in t for p in GROOMING_PATTERNS)
    }


def enforce_child_safety(raw, text):
    intent = detect_intent(text)
    score = int(raw.get("toxicity_score", 0))

    if intent["profanity"] and score < 60:
        score = 60

    if intent["grooming"] and score < 75:
        score = 75

    if score >= 70:
        severity = "High"
    elif score >= 40:
        severity = "Medium"
    else:
        severity = "Low"

    labels = raw.get("detected_labels", {})
    if intent["profanity"]:
        labels["profanity"] = True
    if intent["grooming"]:
        labels["manipulation"] = True
        labels["grooming"] = True
        labels["sexual_content"] = True

    return {
        "toxicity_score": min(score, 100),
        "severity_level": severity,
        "explanation": raw.get(
            "explanation",
            "This message may be harmful or inappropriate for a child."
        ),
        "victim_support_message": raw.get(
            "victim_support_message",
            "This message crosses boundaries. You did nothing wrong, and it’s okay to feel uncomfortable."
        ),
        "safe_response_steps": raw.get(
            "safe_response_steps",
            [
                "Do not reply to the message",
                "Block or report the sender",
                "Tell a parent, teacher, or trusted adult",
                "Save screenshots if needed"
            ]
        ),
        "detected_labels": labels,
        "parent_alert_required": score >= 70
    }


# =========================
# ROUTES
# =========================
@app.route("/")
def index():
    return redirect(url_for("dashboard")) if current_user.is_authenticated else redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        if User.query.filter_by(email=request.form["email"]).first():
            flash("Email already exists")
            return redirect(url_for("signup"))

        user = User(
            name=request.form["name"],
            email=request.form["email"],
            parent_email=request.form["parent_email"],
        )
        user.set_password(request.form["password"])

        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("login.html", mode="signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if not user or not user.check_password(request.form["password"]):
            flash("Invalid credentials")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("login.html", mode="login")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    history = Analysis.query.filter_by(
        user_id=current_user.id
    ).order_by(Analysis.timestamp.desc()).all()

    for h in history:
        h.labels_list = json.loads(h.labels or "{}")
        h.steps = json.loads(h.safe_response_steps or "[]")

    return render_template("dashboard.html", user=current_user, history=history)


# =========================
# ANALYZE ROUTE (MASTER PROMPT)
# =========================
@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    text = request.form.get("text", "").strip()

    PROMPT = f"""
You are CareCloud, an AI system built ONLY to protect CHILDREN and TEENAGERS (ages 8–17).

CRITICAL RULES:
- Assume the receiver is a minor.
- Intent matters more than wording.
- Polite language can still be dangerous.
- Grooming, manipulation, secrecy, pressure, or sexual undertones MUST be flagged.
- Be conservative. When unsure, protect the child.

YOU MUST DETECT:
- insults, humiliation, bullying
- emotional manipulation or coercion
- grooming or sexual intent
- violence, gore, threats
- hate speech
- self-harm encouragement

SCORING:
- Mild insult → 40–55
- Profanity or humiliation → 60–70
- Manipulation or grooming → 75–90
- Sexual or violent threats → 90–100

PARENT ALERT:
- true if score ≥ 70

RETURN ONLY VALID JSON WITH THESE EXACT KEYS:
toxicity_score,
severity_level,
explanation,
victim_support_message,
safe_response_steps (array),
detected_labels {{
  profanity, harassment, manipulation,
  grooming, sexual_content, violence,
  gore, hate_speech, self_harm
}},
parent_alert_required

TEXT:
{text}
"""

    try:
        response = model.generate_content(PROMPT)
        raw_text = response.text.strip()
        raw_text = raw_text[raw_text.find("{"): raw_text.rfind("}") + 1]
        raw = json.loads(raw_text)
        analysis = enforce_child_safety(raw, text)
    except Exception:
        analysis = enforce_child_safety({}, text)

    record = Analysis(
        user_id=current_user.id,
        toxicity_score=analysis["toxicity_score"],
        severity_level=analysis["severity_level"],
        explanation=analysis["explanation"],
        victim_support_message=analysis["victim_support_message"],
        safe_response_steps=json.dumps(analysis["safe_response_steps"]),
        labels=json.dumps(analysis["detected_labels"]),
        content_preview=text[:100],
    )

    db.session.add(record)
    db.session.commit()

    return jsonify(analysis)


# =========================
# RUN
# =========================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
