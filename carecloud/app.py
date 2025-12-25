import os
import json
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

import requests
import google.generativeai as genai

# ======================================================
# ENV SETUP
# ======================================================
load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "carecloud-secret")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///database.db")

PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY")
GEMINI_API_KEY = os.getenv("AI_INTEGRATIONS_GEMINI_API_KEY")

if not PERSPECTIVE_API_KEY:
    raise RuntimeError("PERSPECTIVE_API_KEY is missing")

if not GEMINI_API_KEY:
    raise RuntimeError("AI_INTEGRATIONS_GEMINI_API_KEY is missing")

# ======================================================
# FLASK APP
# ======================================================
app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ======================================================
# GEMINI SETUP (ONLY FOR SUPPORT / EXPLANATION)
# ======================================================
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# ======================================================
# DATABASE MODELS
# ======================================================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    parent_email = db.Column(db.String(120), nullable=False)

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

# ======================================================
# ROUTES
# ======================================================
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


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

    return render_template(
        "dashboard.html",
        user=current_user,   # ✅ FIXED
        history=history
    )

# ======================================================
# PERSPECTIVE API (CORE SAFETY ENGINE)
# ======================================================
def analyze_with_perspective(text):
    url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={PERSPECTIVE_API_KEY}"

    attributes = {
        "TOXICITY": {},
        "SEVERE_TOXICITY": {},
        "THREAT": {},
        "INSULT": {},
        "SEXUALLY_EXPLICIT": {},
        "PROFANITY": {},
        "IDENTITY_ATTACK": {}
    }

    payload = {
        "comment": {"text": text},
        "languages": ["en"],
        "requestedAttributes": attributes
    }

    res = requests.post(url, json=payload, timeout=10)
    res.raise_for_status()
    data = res.json()["attributeScores"]

    scores = {k: round(v["summaryScore"]["value"] * 100) for k, v in data.items()}

    max_score = max(scores.values())
    severity = "Low"
    if max_score >= 70:
        severity = "High"
    elif max_score >= 40:
        severity = "Medium"

    labels = {
        "harassment": scores["INSULT"] >= 40 or scores["PROFANITY"] >= 40,
        "threats": scores["THREAT"] >= 40,
        "sexual_content": scores["SEXUALLY_EXPLICIT"] >= 30,
        "hate_speech": scores["IDENTITY_ATTACK"] >= 30,
        "cyberbullying": scores["TOXICITY"] >= 40,
        "violence": scores["THREAT"] >= 30
    }

    return max_score, severity, labels, scores

# ======================================================
# GEMINI SUPPORT CONTENT
# ======================================================
def generate_support_content(text, labels):
    prompt = f"""
You are a child-safety support assistant.

Message:
{text}

Detected risks:
{labels}

Generate:
1. Short explanation (why harmful, child-safe)
2. Emotional support message for victim
3. 3 clear safe steps for the child
4. Guidance for parents

Return JSON with keys:
explanation,
victim_support_message,
safe_response_steps (array),
support_panel_content {{
  context_summary,
  student_guidance,
  parent_guidance
}}
"""

    response = gemini_model.generate_content(prompt)
    raw = response.text.strip()

    start = raw.find("{")
    end = raw.rfind("}")

    return json.loads(raw[start:end + 1])

# ======================================================
# ANALYZE ROUTE
# ======================================================
@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    text = request.form.get("text", "").strip()

    if not text:
        return jsonify({"error": "No text provided"}), 400

    score, severity, labels, raw_scores = analyze_with_perspective(text)
    support = generate_support_content(text, labels)

    analysis = {
        "toxicity_score": score,
        "severity_level": severity,
        "detected_labels": labels,
        "explanation": support["explanation"],
        "victim_support_message": support["victim_support_message"],
        "safe_response_steps": support["safe_response_steps"],
        "parent_alert_required": score >= 70,
        "support_panel_content": support["support_panel_content"]
    }

    record = Analysis(
        user_id=current_user.id,
        toxicity_score=score,
        severity_level=severity,
        explanation=analysis["explanation"],
        victim_support_message=analysis["victim_support_message"],
        safe_response_steps=json.dumps(analysis["safe_response_steps"]),
        labels=json.dumps(labels),
        content_preview=text[:100]
    )

    db.session.add(record)
    db.session.commit()

    return jsonify(analysis)

# ======================================================
# START APP
# ======================================================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
