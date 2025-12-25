import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from flask_mail import Mail, Message
import google.generativeai as genai

# =======================
# ENV
# =======================
load_dotenv()

# =======================
# APP
# =======================
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "carecloud-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///carecloud.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# =======================
# MAIL
# =======================
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USER")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASS")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_USER")

mail = Mail(app)
db = SQLAlchemy(app)

# =======================
# LOGIN
# =======================
login_manager = LoginManager(app)
login_manager.login_view = "login"

# =======================
# AI SETUP
# =======================
genai.configure(api_key=os.getenv("AI_INTEGRATIONS_GEMINI_API_KEY"))
gemini = genai.GenerativeModel("models/gemini-pro")

PERSPECTIVE_KEY = os.getenv("PERSPECTIVE_API_KEY")

# =======================
# MODELS
# =======================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256))
    parent_email = db.Column(db.String(120))

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Analysis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    content_preview = db.Column(db.Text)
    toxicity_score = db.Column(db.Integer)
    severity_level = db.Column(db.String(20))
    labels = db.Column(db.Text)
    explanation = db.Column(db.Text)
    support = db.Column(db.Text)
    steps = db.Column(db.Text)

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# =======================
# PERSPECTIVE
# =======================
def perspective_analyze(text):
    url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={PERSPECTIVE_KEY}"
    payload = {
        "comment": {"text": text},
        "requestedAttributes": {
            "TOXICITY": {},
            "THREAT": {},
            "INSULT": {},
            "SEXUALLY_EXPLICIT": {}
        }
    }
    r = requests.post(url, json=payload, timeout=10)
    data = r.json()["attributeScores"]

    def score(k):
        return int(data[k]["summaryScore"]["value"] * 100)

    return {
        "toxicity": score("TOXICITY"),
        "threat": score("THREAT"),
        "sexual": score("SEXUALLY_EXPLICIT"),
        "insult": score("INSULT")
    }

# =======================
# GEMINI ANALYSIS
# =======================
def gemini_analyze(text):
    prompt = open("prompt.txt").read().replace("{TEXT}", text)
    response = gemini.generate_content(prompt).text
    return json.loads(response[response.find("{"):response.rfind("}")+1])

# =======================
# EMAIL
# =======================
def notify_parent(user, analysis):
    if analysis["severity_level"] != "High":
        return

    msg = Message(
        subject="⚠️ CareCloud Safety Alert",
        recipients=[user.parent_email],
        body=f"""
High-risk content detected.

Child: {user.name}
Score: {analysis['toxicity_score']}%

Reason:
{analysis['explanation']}
"""
    )
    mail.send(msg)

# =======================
# ROUTES
# =======================
@app.route("/dashboard")
@login_required
def dashboard():
    history = Analysis.query.filter_by(user_id=current_user.id).order_by(Analysis.timestamp.desc()).all()
    return render_template("dashboard.html", user=current_user, history=history)

@app.route("/analyze", methods=["POST"])
@login_required
def analyze():
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty input"}), 400

    p = perspective_analyze(text)
    g = gemini_analyze(text)

    final_score = max(p.values() | {g["gemini_score"]})
    severity = "Low"

    if p["threat"] > 60 or p["sexual"] > 60 or g["detected_labels"]["grooming"]:
        severity = "High"
    elif p["toxicity"] > 30 or g["detected_labels"]["manipulation"]:
        severity = "Medium"

    result = {
        "toxicity_score": final_score,
        "severity_level": severity,
        "detected_labels": g["detected_labels"],
        "explanation": g["why_harmful"],
        "victim_support_message": g["victim_support"],
        "safe_response_steps": g["safety_steps"],
        "parent_alert_required": severity == "High",
        "support_panel_content": {
            "context_summary": g["why_harmful"],
            "student_guidance": g["victim_support"],
            "parent_guidance": g["parent_guidance"]
        }
    }

    db.session.add(Analysis(
        user_id=current_user.id,
        content_preview=text[:120],
        toxicity_score=final_score,
        severity_level=severity,
        labels=json.dumps(g["detected_labels"]),
        explanation=g["why_harmful"],
        support=g["victim_support"],
        steps=json.dumps(g["safety_steps"])
    ))
    db.session.commit()

    notify_parent(current_user, result)
    return jsonify(result)

# =======================
# RUN
# =======================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
