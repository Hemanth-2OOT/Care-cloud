import os
import json
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import PIL.Image
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Google Cloud Imports
import google.cloud.logging
from google.cloud import secretmanager

# Load environment variables (local dev)
load_dotenv()

# --- Google Cloud Configuration ---
# Function to access secrets from Secret Manager
def get_secret(secret_id, project_id=None):
    """
    Retrieves a secret from Google Cloud Secret Manager.
    Tries environment variable first, then falls back to Secret Manager.
    """
    # 1. Try Local Environment Variable first
    if os.getenv(secret_id):
        return os.getenv(secret_id)

    # 2. Try Secret Manager (if PROJECT_ID env var is set or project_id provided)
    project_id = project_id or os.getenv('GOOGLE_CLOUD_PROJECT')

    if project_id:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        try:
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            print(f"Warning: Failed to fetch secret {secret_id} from Secret Manager: {e}")
            return None
    return None

# Setup Google Cloud Logging
if os.getenv('GOOGLE_CLOUD_PROJECT'):
    try:
        client = google.cloud.logging.Client()
        client.setup_logging()
    except Exception as e:
        print(f"Warning: Failed to setup Google Cloud Logging: {e}")

# Configure Secrets
GENAI_API_KEY = get_secret('GEMINI_API_KEY')
SENDGRID_API_KEY = get_secret('SENDGRID_API_KEY')
SENDGRID_FROM_EMAIL = get_secret('SENDGRID_FROM_EMAIL') # e.g. alerts@carecloud.com

# Configure Gemini AI
if GENAI_API_KEY:
    genai.configure(api_key=GENAI_API_KEY)
else:
    logging.warning("GEMINI_API_KEY not found. AI features will run in mock mode.")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'carecloud-secret-key-change-this-in-prod'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)  # 'child' or 'parent'
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    # For child accounts: linked parent email
    parent_email = db.Column(db.String(100), nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    child_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    toxicity_score = db.Column(db.Integer, nullable=False)
    severity_level = db.Column(db.String(50), nullable=False)
    categories = db.Column(db.Text, nullable=True) # JSON string of categories
    explanation = db.Column(db.Text, nullable=False)

    # Relationship to access child details
    child = db.relationship('User', backref=db.backref('alerts', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        role = request.form.get('role')
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        parent_email = request.form.get('parent_email')

        # Validation
        if not role:
            flash('Please select a role (Child or Parent).')
            return redirect(url_for('signup'))

        if role == 'child':
            if not parent_email:
                flash('Parent email is required for child accounts.')
                return redirect(url_for('signup'))
            if email.strip().lower() == parent_email.strip().lower():
                flash('Child email and Parent email must be different.')
                return redirect(url_for('signup'))

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists')
            return redirect(url_for('signup'))

        new_user = User(role=role, name=name, email=email, parent_email=parent_email if role == 'child' else None)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        login_user(new_user)
        return redirect(url_for('dashboard'))

    return render_template('login.html', mode='signup')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash('Please check your login details and try again.')
            return redirect(url_for('login'))

        login_user(user)
        return redirect(url_for('dashboard'))

    return render_template('login.html', mode='login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'child':
        return render_template('dashboard_child.html', user=current_user)
    elif current_user.role == 'parent':
        # Fetch alerts for all children linked to this parent
        # Find children first
        children = User.query.filter_by(parent_email=current_user.email).all()
        child_ids = [child.id for child in children]

        # Then fetch alerts
        alerts = Alert.query.filter(Alert.child_id.in_(child_ids)).order_by(Alert.timestamp.desc()).all()

        return render_template('dashboard_parent.html', user=current_user, alerts=alerts, children=children)

    # Fallback
    return render_template('dashboard_child.html', user=current_user)

# --- API Endpoints (REST) ---

@app.route('/api/parent/alerts', methods=['GET'])
@login_required
def api_parent_alerts():
    """
    REST Endpoint to retrieve alerts for a parent.
    Input: Implicitly current_user (parent)
    Output: JSON list of alerts
    """
    if current_user.role != 'parent':
        return jsonify({'error': 'Unauthorized access'}), 403

    # Find children linked to this parent
    children = User.query.filter_by(parent_email=current_user.email).all()
    child_ids = [child.id for child in children]

    # Fetch alerts
    alerts = Alert.query.filter(Alert.child_id.in_(child_ids)).order_by(Alert.timestamp.desc()).all()

    # Format output (No raw content, only reason/severity)
    alert_list = []
    for alert in alerts:
        alert_list.append({
            'timestamp': alert.timestamp.isoformat(),
            'child_name': alert.child.name,
            'toxicity_score': alert.toxicity_score,
            'severity_level': alert.severity_level,
            'categories': json.loads(alert.categories) if alert.categories else [],
            'explanation': alert.explanation
        })

    return jsonify({'alerts': alert_list})

@app.route('/api/child/history', methods=['GET'])
@login_required
def api_child_history():
    """
    Returns recent alerts/checks for the child dashboard history.
    """
    if current_user.role != 'child':
        return jsonify({'error': 'Unauthorized'}), 403

    alerts = Alert.query.filter_by(child_id=current_user.id).order_by(Alert.timestamp.desc()).limit(5).all()
    history = []
    for a in alerts:
        history.append({
            'timestamp': a.timestamp.strftime('%Y-%m-%d %H:%M'),
            'severity': a.severity_level,
            'categories': json.loads(a.categories) if a.categories else []
        })
    return jsonify({'history': history})


def send_email_alert(parent_email, student_name, score, severity, categories, explanation):
    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        logging.warning("SendGrid credentials not set. Skipping email alert.")
        return False

    labels_str = ", ".join(categories) if categories else "Potential Harm"

    subject = f"CareCloud Report: Check-in needed for {student_name}"

    html_content = f"""
    <div style="font-family: sans-serif; color: #333; padding: 20px;">
        <h2 style="color: #6366f1;">CareCloud Update 💜</h2>
        <p>Hello,</p>
        <p>We wanted to share a quick update regarding <strong>{student_name}</strong>'s recent activity on CareCloud.</p>

        <div style="background-color: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin-top: 0;">Analysis Report</h3>
            <p><strong>Detected Labels:</strong> {labels_str}</p>
            <p><strong>Severity:</strong> {severity}</p>
            <p><strong>Reason:</strong> {explanation}</p>
        </div>

        <p><em>Note: To respect privacy and encourage trust, we do not include the raw text here.</em></p>

        <h3>Supportive Recommendations:</h3>
        <ul>
            <li>Approach {student_name} with curiosity and care.</li>
            <li>Ask: "I noticed you might be dealing with something tough. Do you want to talk about it?"</li>
            <li>Listen without judgment.</li>
        </ul>

        <p>Thank you for being a supportive part of {student_name}'s digital life.</p>
        <p>Warmly,<br>The CareCloud Team</p>
    </div>
    """

    message = Mail(
        from_email=SENDGRID_FROM_EMAIL,
        to_emails=parent_email,
        subject=subject,
        html_content=html_content
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        logging.info(f"Email sent to {parent_email}. Status Code: {response.status_code}")
        return True
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
        return False

@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    text_content = request.form.get('text', '')
    image_file = request.files.get('image')

    if not text_content and not image_file:
        return jsonify({'error': 'No text content or image provided'}), 400

    if not GENAI_API_KEY:
         # Mock response for testing/demo without API key
        return jsonify({
            "toxicity_score": 0,
            "severity_level": "Low",
            "explanation": "Gemini API Key not configured. Using safe default.",
            "victim_support_message": "Please configure the API key to get real analysis.",
            "parent_alert_required": False
        })

    try:
        # Cost Constraint: Use Gemini Flash model (low cost, high speed)
        model_name = 'gemini-1.5-flash'
        model = genai.GenerativeModel(model_name)

        content_parts = []

        prompt_text = """
        Analyze the following content (text and/or image) for cyberbullying, toxicity, harassment, hate speech, and threats.
        If there is an image, extract relevant text and analyze the visual context as well.

        Return a valid JSON object with the following fields:
        - toxicity_score: integer (0-100)
        - severity_level: string ("Low", "Medium", "High", "Critical")
        - categories: list of strings (e.g. ["Hate Speech", "Insult", "Threat", "Harassment"]) - empty list if none
        - explanation: string (brief explanation of why it was flagged or not, explaining the labels)
        - victim_support_message: string (empathetic message for the user)
        - parent_alert_required: boolean (true if toxicity_score > 70)

        Do not include markdown formatting like ```json ... ```. Just the raw JSON string.
        """
        content_parts.append(prompt_text)

        if text_content:
             content_parts.append(f"Text Input: {text_content}")

        if image_file:
            img = PIL.Image.open(image_file)
            content_parts.append(img)

        response = model.generate_content(content_parts)
        # Clean up response text in case it contains markdown code blocks
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        analysis_result = json.loads(response_text)

        # Trigger email alert if needed
        if analysis_result.get('parent_alert_required', False):
            # Save Alert to Database
            categories_json = json.dumps(analysis_result.get('categories', []))
            new_alert = Alert(
                child_id=current_user.id,
                toxicity_score=analysis_result['toxicity_score'],
                severity_level=analysis_result['severity_level'],
                categories=categories_json,
                explanation=analysis_result['explanation']
            )
            db.session.add(new_alert)
            db.session.commit()

            # Send Email
            send_email_alert(
                current_user.parent_email,
                current_user.name,
                analysis_result['toxicity_score'],
                analysis_result['severity_level'],
                analysis_result.get('categories', []),
                analysis_result['explanation']
            )

        return jsonify(analysis_result)

    except Exception as e:
        print(f"Error calling Gemini: {e}")
        return jsonify({'error': 'Failed to analyze content'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    # Run on PORT provided by Cloud Run, or default to 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
