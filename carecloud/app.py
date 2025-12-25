import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

import google.generativeai as genai

# =========================
# APP SETUP
# =========================
app = Flask(__name__)

@app.route("/health")
def health():
    return "CareCloud is running", 200

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY", "carecloud-secret-key-change-this"
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL", "sqlite:///database.db"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# =========================
# GEMINI SETUP
# =========================
GEMINI_API_KEY = os.getenv("AI_INTEGRATIONS_GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("AI_INTEGRATIONS_GEMINI_API_KEY is not set")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

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
# ROUTES
# =========================
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

    for h in history:
        h.labels_list = json.loads(h.labels or "{}")
        h.steps = json.loads(h.safe_response_steps or "[]")

    return render_template("dashboard.html", user=current_user, history=history)

# =========================
# EMAIL ALERT
# =========================
def send_email_alert(parent_email, student_name, score, severity, labels):
    sender = os.getenv("MAIL_USERNAME")
    password = os.getenv("MAIL_PASSWORD")

    if not sender or not password:
        return False

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = parent_email
    msg["Subject"] = f"CareCloud Alert for {student_name}"

    body = f"""
Harmful content detected.

Student: {student_name}
Severity: {severity}
Score: {score}/100
Labels: {labels}
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
# ANALYZE ROUTE (FIXED)
# =========================
@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    text = request.form.get("text", "")
    image = request.files.get("image")

    ocr_text = ""

    if image:
        try:
            from PIL import Image
            import pytesseract

            img = Image.open(image.stream).convert("RGB")
            ocr_text = pytesseract.image_to_string(img).strip()
        except Exception:
            ocr_text = ""

    prompt = f"""
Return ONLY valid JSON.

Text:
{text}

OCR:
{ocr_text}

Required keys:
toxicity_score,
severity_level,
explanation,
victim_support_message,
safe_response_steps,
detected_labels,
parent_alert_required
"""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()

        start = raw.find("{")
        end = raw.rfind("}")
        analysis = json.loads(raw[start:end+1])

    except Exception:
        analysis = {
            "toxicity_score": 0,
            "severity_level": "Low",
            "explanation": "Analysis failed",
            "victim_support_message": "Stay safe",
            "safe_response_steps": [],
            "detected_labels": {},
            "parent_alert_required": False,
        }

    record = Analysis(
        user_id=current_user.id,
        toxicity_score=analysis.get("toxicity_score", 0),
        severity_level=analysis.get("severity_level", "Low"),
        explanation=analysis.get("explanation", ""),
        victim_support_message=analysis.get("victim_support_message", ""),
        safe_response_steps=json.dumps(analysis.get("safe_response_steps", [])),
        labels=json.dumps(analysis.get("detected_labels", {})),
        content_preview=text[:100],
    )

    db.session.add(record)
    db.session.commit()

    if analysis.get("parent_alert_required"):
        send_email_alert(
            current_user.parent_email,
            current_user.name,
            analysis.get("toxicity_score"),
            analysis.get("severity_level"),
            analysis.get("detected_labels"),
        )

    return jsonify(analysis)

# =========================
# START
# =========================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
