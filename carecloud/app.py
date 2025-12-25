import os
import json
import smtplib
import requests
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

import google.generativeai as genai
from PIL import Image
import pytesseract

# =========================
# ENV + APP SETUP
# =========================
load_dotenv()

app = Flask(__name__)

@app.route("/health")
def health():
    return "CareCloud is running", 200

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "carecloud-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///database.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# =========================
# GEMINI (SUPPORT + EXPLANATION)
# =========================
GEMINI_API_KEY = os.getenv("AI_INTEGRATIONS_GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("AI_INTEGRATIONS_GEMINI_API_KEY missing")

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-1.5-flash")

# =========================
# PERSPECTIVE API (DETECTION)
# =========================
PERSPECTIVE_API_KEY = os.getenv("PERSPECTIVE_API_KEY")
PERSPECTIVE_URL = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"

REQUESTED_ATTRIBUTES = {
    "TOXICITY": {},
    "SEVERE_TOXICITY": {},
    "INSULT": {},
    "PROFANITY": {},
    "THREAT": {},
    "SEXUAL_EXPLICIT": {},
    "FLIRTATION": {},
    "IDENTITY_ATTACK": {}
}

def perspective_analyze(text):
    if not text.strip():
        return {}

    payload = {
        "comment": {"text": text},
        "languages": ["en"],
        "requestedAttributes": REQUESTED_ATTRIBUTES
    }

    try:
        r = requests.post(
            f"{PERSPECTIVE_URL}?key={PERSPECTIVE_API_KEY}",
            json=payload,
            timeout=10
        )
        if r.status_code != 200:
            return {}
        return r.json().get("attributeScores", {})
    except Exception:
        return {}

def compute_score(scores):
    labels = {}
    max_score = 0.0

    for k, v in scores.items():
        s = v["summaryScore"]["value"]
        labels[k.lower()] = round(s, 3)
        max_score = max(max_score, s)

    toxicity = int(max_score * 100)

    if toxicity >= 70:
        severity = "High"
    elif toxicity >= 40:
        severity = "Medium"
    else:
        severity = "Low"

    parent_alert = toxicity >= 70
    return toxicity, severity, labels, parent_alert

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

    def set_password(self, p):
        self.password_hash = generate_password_hash(p)

    def check_password(self, p):
        return check_password_hash(self.password_hash, p)

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
def load_user(uid):
    return User.query.get(int(uid))

# =========================
# ROUTES (AUTH)
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

        u = User(
            name=request.form["name"],
            email=request.form["email"],
            parent_email=request.form["parent_email"]
        )
        u.set_password(request.form["password"])
        db.session.add(u)
        db.session.commit()
        login_user(u)
        return redirect(url_for("dashboard"))

    return render_template("login.html", mode="signup")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(email=request.form["email"]).first()
        if not u or not u.check_password(request.form["password"]):
            flash("Invalid credentials")
            return redirect(url_for("login"))

        login_user(u)
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

    return render_template("dashboard.html", history=history)

# =========================
# EMAIL ALERT
# =========================
def send_email_alert(parent_email, name, score, severity, labels):
    sender = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")
    if not sender or not password:
        return

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = parent_email
    msg["Subject"] = f"CareCloud Alert – {name}"

    msg.attach(MIMEText(f"""
CareCloud detected harmful content.

Severity: {severity}
Score: {score}/100
Detected risks: {labels}

Please check in with your child.
""", "plain"))

    try:
        s = smtplib.SMTP("smtp.gmail.com", 587)
        s.starttls()
        s.login(sender, password)
        s.send_message(msg)
        s.quit()
    except Exception:
        pass

# =========================
# ANALYZE ROUTE (FINAL)
# =========================
@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    text = request.form.get("text", "")
    image = request.files.get("image")

    ocr = ""
    if image:
        try:
            img = Image.open(image.stream).convert("RGB")
            ocr = pytesseract.image_to_string(img).strip()
        except Exception:
            pass

    content = f"{text}\n{ocr}"

    scores = perspective_analyze(content)
    toxicity, severity, labels, parent_alert = compute_score(scores)

    # AI explanation + support
    prompt = f"""
You are a CHILD ONLINE SAFETY ASSISTANT.

Message received:
\"\"\"{content}\"\"\"

Detected risk labels:
{labels}

Tasks:
1. Explain clearly WHY this message is harmful to a child.
2. Give a short emotional support message to the child.
3. Give 3–5 simple steps the child should follow.
4. Give a 1–2 line safety summary.

Rules:
- Speak gently and clearly.
- Do NOT shame the child.
- Assume child age 8–16.
- Be specific to THIS message.

Return ONLY valid JSON with keys:
explanation,
support_message,
steps (array),
summary
"""

    try:
        r = gemini.generate_content(prompt)
        raw = r.text.strip()
        start, end = raw.find("{"), raw.rfind("}")
        ai = json.loads(raw[start:end + 1])
    except Exception:
        ai = {
            "explanation": "This message contains unsafe language that can hurt or scare someone.",
            "support_message": "You did nothing wrong. You deserve to feel safe.",
            "steps": [
                "Do not reply to the message",
                "Block or report the sender",
                "Tell a trusted adult"
            ],
            "summary": "This content is unsafe and should not be ignored."
        }

    record = Analysis(
        user_id=current_user.id,
        toxicity_score=toxicity,
        severity_level=severity,
        explanation=ai["explanation"],
        victim_support_message=ai["support_message"],
        safe_response_steps=json.dumps(ai["steps"]),
        labels=json.dumps(labels),
        content_preview=text[:100]
    )

    db.session.add(record)
    db.session.commit()

    if parent_alert:
        send_email_alert(
            current_user.parent_email,
            current_user.name,
            toxicity,
            severity,
            labels
        )

    return jsonify({
        "toxicity_score": toxicity,
        "severity_level": severity,
        "explanation": ai["explanation"],
        "victim_support_message": ai["support_message"],
        "safe_response_steps": ai["steps"],
        "detected_labels": labels,
        "summary": ai["summary"],
        "parent_alert_required": parent_alert
    })

# =========================
# RUN
# =========================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
