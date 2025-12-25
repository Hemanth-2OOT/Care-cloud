import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import PIL.Image
from dotenv import load_dotenv
import pytesseract

# Load environment variables
load_dotenv()

# Configure Gemini AI using Replit integration (no API key needed)
from google import genai
from google.genai import types

# This uses Replit's AI Integrations service automatically
client = genai.Client(
    api_key=os.environ.get("AI_INTEGRATIONS_GEMINI_API_KEY", ""),
    http_options={
        'api_version': '',
        'base_url': os.environ.get("AI_INTEGRATIONS_GEMINI_BASE_URL", "")   
    }
)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'carecloud-secret-key-change-this-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # type: ignore

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    parent_email = db.Column(db.String(100), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Routes ---

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        parent_email = request.form.get('parent_email')

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists')
            return redirect(url_for('signup'))

        new_user = User(name=name, email=email, parent_email=parent_email)  # type: ignore
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
    return render_template('dashboard.html', user=current_user)

def send_email_alert(parent_email, student_name, score, severity, labels=None):
    """Send detailed email alert to parent with comprehensive analysis labels."""
    sender_email = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')

    if not sender_email or not sender_password:
        print("⚠️ Email credentials not configured. Alert saved but email not sent.")
        print(f"   To enable: Set MAIL_USERNAME and MAIL_PASSWORD environment variables")
        return False

    # Prepare labels for email
    detected_issues = []
    if labels:
        if labels.get('harassment'): detected_issues.append('🚨 Harassment/Bullying')
        if labels.get('hate_speech'): detected_issues.append('⚠️ Hate Speech')
        if labels.get('threats'): detected_issues.append('🔴 Threats')
        if labels.get('sexual_content'): detected_issues.append('🔒 Inappropriate Content')
        if labels.get('emotional_abuse'): detected_issues.append('💔 Emotional Abuse')
        if labels.get('cyberbullying'): detected_issues.append('📱 Cyberbullying')

    issues_text = '\n'.join([f"  {issue}" for issue in detected_issues]) if detected_issues else "  Toxicity detected"

    msg = MIMEMultipart('alternative')
    msg['From'] = sender_email
    msg['To'] = parent_email
    msg['Subject'] = f"🚨 CareCloud Alert – Support Needed for {student_name}"

    # HTML email with proper formatting (no raw content)
    body = f"""
Dear Parent/Guardian,

We're reaching out because CareCloud detected potentially harmful content exposure on {student_name}'s account.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 ANALYSIS SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Detected Issues:
{issues_text}

Severity Level: {severity} ({score}/100)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 HOW YOU CAN HELP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Have a calm, supportive conversation
✓ Listen without judgment
✓ Reassure them it's not their fault
✓ Consider professional counseling if needed
✓ Monitor their online activity going forward

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 IMPORTANT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CareCloud uses AI to PROTECT, not punish.
We never share raw messages - only analysis labels.
Your child is safe, and we're here to help.

Best regards,
The CareCloud Team
Support: carecloud@example.com
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, parent_email, text)
        server.quit()
        print(f"✅ Email alert sent to {parent_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    # Expecting 'text' in form and 'image' in files (script.js uses these keys)
    text_content = request.form.get('text', '')
    image_file = request.files.get('image')

    if not text_content and not image_file:
        return jsonify({'error': 'No text content or image provided'}), 400

    try:
        # OCR step (if an image was uploaded)
        ocr_text = ''
        if image_file:
            try:
                img = PIL.Image.open(image_file.stream)  # type: ignore
                # Optional: convert to RGB for some images
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                ocr_text = pytesseract.image_to_string(img)
                ocr_text = ocr_text.strip()
            except Exception as e:
                print(f"Failed to process image for OCR: {e}")
                ocr_text = ''

        prompt_text = """
        You are CareCloud Safety Agent. Analyze content for harmful patterns. Return ONLY valid JSON (no markdown, no extra text).
        
        CRITICAL: Always include ALL these sections. Never omit any:
        - toxicity_score: 0-100 integer
        - severity_level: "Low" (0-30), "Medium" (31-60), "High" (61-85), or "Critical" (86-100)
        - explanation: Clear explanation of WHY this content is harmful. Simple language. If safe, explain it's appropriate.
        - victim_support_message: Empathetic reassurance if harmful. Always provide guidance & emotional safety. If safe, provide encouragement.
        - safe_response_steps: Array of 3 step-by-step instructions on how to respond safely. If safe, provide tips for similar situations.
        - detected_labels: Object with BOOLEAN values (true/false) for: harassment, hate_speech, threats, sexual_content, emotional_abuse, cyberbullying
        - parent_alert_required: true if toxicity_score > 70, false otherwise
        
        Example (High Risk):
        {
          "toxicity_score": 85,
          "severity_level": "Critical",
          "explanation": "This contains severe harassment with dehumanizing language and threats of violence directed at the recipient.",
          "victim_support_message": "This is not okay. You don't deserve to be treated this way. Please talk to a trusted adult about what happened. You are not alone.",
          "safe_response_steps": ["Step 1: Block this person immediately.", "Step 2: Take a screenshot for evidence.", "Step 3: Tell a trusted adult or report to the platform."],
          "detected_labels": {"harassment": true, "hate_speech": true, "threats": true, "sexual_content": false, "emotional_abuse": true, "cyberbullying": true},
          "parent_alert_required": true
        }
        
        Example (Safe):
        {
          "toxicity_score": 15,
          "severity_level": "Low",
          "explanation": "This is appropriate communication. It shows respect and clear boundaries.",
          "victim_support_message": "Great job communicating clearly and respectfully. Keep setting healthy boundaries in your interactions.",
          "safe_response_steps": ["Step 1: Continue using respectful language.", "Step 2: Listen to others' perspectives.", "Step 3: Ask clarifying questions if confused."],
          "detected_labels": {"harassment": false, "hate_speech": false, "threats": false, "sexual_content": false, "emotional_abuse": false, "cyberbullying": false},
          "parent_alert_required": false
        }
        """

        # Build content for Gemini
        content = [prompt_text]
        if text_content:
            content.append(f"Text Input: {text_content}")
        if ocr_text:
            content.append(f"OCR Extracted Text: {ocr_text}")

        # Call Gemini AI via Replit integration
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=' '.join(content)
        )
        response_text = response.text.strip() if response.text else ""

        # Try to extract JSON substring in case the model added commentary
        first = response_text.find('{')
        last = response_text.rfind('}')
        if first != -1 and last != -1 and last > first:
            response_text = response_text[first:last+1]

        analysis_result = json.loads(response_text)

        # Ensure labels exist in response
        if 'detected_labels' not in analysis_result:
            analysis_result['detected_labels'] = {}

        # Trigger email alert if needed (critical severity)
        if analysis_result.get('parent_alert_required', False):
            send_email_alert(
                current_user.parent_email,
                current_user.name,
                analysis_result.get('toxicity_score', 0),
                analysis_result.get('severity_level', 'Unknown'),
                analysis_result.get('detected_labels', {})
            )

        return jsonify(analysis_result)

    except json.JSONDecodeError as je:
        print(f"Failed to parse model output as JSON: {je}")
        return jsonify({'error': 'Failed to parse model output'}), 500
    except Exception as e:
        print(f"Error calling AI or processing request: {e}")
        return jsonify({'error': 'Failed to analyze content'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', debug=True, port=port)
