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

from PIL import Image
import pytesseract
import google.generativeai as genai

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
# GEMINI PRO SETUP
# =========================
GEMINI_API_KEY = os.getenv("AI_INTEGRATIONS_GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("AI_INTEGRATIONS_GEMINI_API_KEY missing")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

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
    age_risk_level = db.Column(db.String(20))
    ai_summary = db.Column(db.Text)

    labels = db.Column(db.Text)
    intent_labels = db.Column(db.Text)
    safe_response_steps = db.Column(db.Text)
    content_preview = db.Column(db.Text)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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
            parent_email=request.form["parent_email"]
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
        h.intent_list = json.loads(h.intent_labels or "{}")
        h.steps = json.loads(h.safe_response_steps or "[]")

    return render_template("dashboard.html", user=current_user, history=history)

# =========================
# EMAIL ALERT
# =========================
def send_email_alert(parent_email, student_name, risk_level, summary):
    sender = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")
    if not sender or not password:
        return False

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = parent_email
    msg["Subject"] = f"CareCloud Safety Alert for {student_name}"

    body = f"""
CareCloud detected HIGH-RISK content.

Student: {student_name}
Risk Level: {risk_level}

Summary:
{summary}

Please check in with your child.
"""
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, parent_email, msg.as_string())
        server.quit()
        return True
    except Exception:
        return False

# =========================
# ANALYZE (INTENT + SAFETY)
# =========================
@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    text = request.form.get("text", "")
    image = request.files.get("image")

    ocr_text = ""
    if image:
        try:
            img = Image.open(image.stream).convert("RGB")
            ocr_text = pytesseract.image_to_string(img).strip()
        except Exception:
            pass

    combined = f"{text} {ocr_text}".lower()

    # -------------------------
    # HARD SAFETY LABELS
    # -------------------------
    SAFETY_LABELS = {
        "profanity": ["fuck", "shit", "bitch"],
        "violence": ["kill", "stab", "attack"],
        "gore": ["blood everywhere", "guts"],
        "self_harm": ["kill yourself", "want to die"],
        "sexual_content": ["porn", "nude"],
        "drugs_alcohol": ["drugs", "alcohol"]
    }

    detected_labels = {k: False for k in SAFETY_LABELS}
    for label, words in SAFETY_LABELS.items():
        if any(w in combined for w in words):
            detected_labels[label] = True

    # -------------------------
    # INTENT ANALYSIS (AI)
    # -------------------------
    intent_prompt = f"""
You are analyzing messages sent to a CHILD.

Determine if the speaker shows any of these INTENTS:
- emotional_manipulation
- coercion
- isolation
- grooming
- dependency
- fear_induction
- emotional_blackmail

Text:
{text}

OCR:
{ocr_text}

Return ONLY JSON with each intent as true or false.
"""
    try:
        intent_raw = model.generate_content(intent_prompt).text.strip()
        s, e = intent_raw.find("{"), intent_raw.rfind("}")
        intent_labels = json.loads(intent_raw[s:e+1])
    except Exception:
        intent_labels = {}

    # -------------------------
    # RISK CALCULATION
    # -------------------------
    risk_score = sum(1 for v in detected_labels.values() if v)
    intent_score = sum(1 for v in intent_labels.values() if v)

    if detected_labels.get("self_harm") or intent_labels.get("grooming"):
        age_risk = "Critical"
        severity = "High"
        score = 95
    elif risk_score + intent_score >= 3:
        age_risk = "High Risk"
        severity = "High"
        score = 80
    elif risk_score + intent_score >= 1:
        age_risk = "Mild Risk"
        severity = "Medium"
        score = 55
    else:
        age_risk = "Safe"
        severity = "Low"
        score = 10

    # -------------------------
    # AI SUMMARY (KID FRIENDLY)
    # -------------------------
    summary_prompt = f"""
Explain the safety concern in calm, simple language for a child or parent.

Detected safety issues:
{detected_labels}

Detected intent patterns:
{intent_labels}

Keep it short, supportive, and non-judgmental.
"""
    try:
        ai_summary = model.generate_content(summary_prompt).text.strip()
    except Exception:
        ai_summary = "This content may not be suitable for children."

    analysis = {
        "toxicity_score": score,
        "severity_level": severity,
        "age_risk_level": age_risk,
        "ai_summary": ai_summary,
        "detected_labels": detected_labels,
        "intent_labels": intent_labels,
        "safe_response_steps": [
            "Do not respond",
            "Block or mute the sender",
            "Talk to a trusted adult"
        ],
        "parent_alert_required": age_risk in ["High Risk", "Critical"]
    }

    record = Analysis(
        user_id=current_user.id,
        toxicity_score=score,
        severity_level=severity,
        age_risk_level=age_risk,
        ai_summary=ai_summary,
        labels=json.dumps(detected_labels),
        intent_labels=json.dumps(intent_labels),
        safe_response_steps=json.dumps(analysis["safe_response_steps"]),
        content_preview=text[:100]
    )

    db.session.add(record)
    db.session.commit()

    if analysis["parent_alert_required"]:
        send_email_alert(
            current_user.parent_email,
            current_user.name,
            age_risk,
            ai_summary
        )

    return jsonify(analysis)

# =========================
# RUN
# =========================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
