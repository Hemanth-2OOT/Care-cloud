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
import google.generativeai as genai
import pytesseract

# Load environment variables
load_dotenv()

# Configure Gemini AI
GENAI_API_KEY = os.getenv('GEMINI_API_KEY')
if GENAI_API_KEY:
    genai.configure(api_key=GENAI_API_KEY)
else:
    print("Warning: GEMINI_API_KEY not found in environment variables.")

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'carecloud-secret-key-change-this-in-prod')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

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
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        parent_email = request.form.get('parent_email')

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email already exists')
            return redirect(url_for('signup'))

        new_user = User(name=name, email=email, parent_email=parent_email)
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

def send_email_alert(parent_email, student_name, score, severity):
    sender_email = os.getenv('MAIL_USERNAME')
    sender_password = os.getenv('MAIL_PASSWORD')

    if not sender_email or not sender_password:
        print("Email credentials not set. Skipping email alert.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = parent_email
    msg['Subject'] = f"CareCloud Alert: Emotional Support Needed for {student_name}"

    body = f"""
    Dear Parent/Guardian,

    CareCloud has detected content associated with {student_name}'s account that may be emotionally harmful.

    Analysis Summary:
    - Toxicity Score: {score}/100
    - Severity Level: {severity}

    We encourage you to have a supportive, non-judgmental conversation with {student_name}.
    Please approach this with empathy and care. The goal is emotional safety, not punishment.

    Best regards,
    The CareCloud Team
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        text = msg.as_string()
        server.sendmail(sender_email, parent_email, text)
        server.quit()
        print(f"Email sent to {parent_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    # Expecting 'text' in form and 'image' in files (script.js uses these keys)
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
        # OCR step (if an image was uploaded)
        ocr_text = ''
        if image_file:
            try:
                img = PIL.Image.open(image_file)
                # Optional: convert to RGB for some images
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                ocr_text = pytesseract.image_to_string(img)
                ocr_text = ocr_text.strip()
            except Exception as e:
                print(f"Failed to process image for OCR: {e}")
                ocr_text = ''

        # Build the prompt for Gemini
        model_name = 'gemini-1.5-flash'
        model = genai.GenerativeModel(model_name)

        prompt_text = """
        Analyze the following content (text and/or OCR-extracted text from an image) for cyberbullying, toxicity, harassment, hate speech, and threats.
        Provide a JSON object with the fields:
          - toxicity_score: integer (0-100)
          - severity_level: string ("Low", "Medium", "High", "Critical")
          - explanation: string (brief explanation of why it was flagged or not)
          - victim_support_message: string (empathetic message for the user)
          - parent_alert_required: boolean (true if toxicity_score > 70)

        Return only the raw JSON (no markdown code fences).
        """

        content_parts = [prompt_text]
        if text_content:
            content_parts.append(f"Text Input: {text_content}")
        if ocr_text:
            content_parts.append(f"OCR Extracted Text: {ocr_text}")

        # Call the model
        response = model.generate_content(content_parts)
        response_text = getattr(response, 'text', str(response)).strip()

        # Try to extract JSON substring in case the model added commentary
        first = response_text.find('{')
        last = response_text.rfind('}')
        if first != -1 and last != -1 and last > first:
            response_text = response_text[first:last+1]

        analysis_result = json.loads(response_text)

        # Trigger email alert if needed
        if analysis_result.get('parent_alert_required', False):
            send_email_alert(
                current_user.parent_email,
                current_user.name,
                analysis_result.get('toxicity_score', 0),
                analysis_result.get('severity_level', 'Unknown')
            )

        return jsonify(analysis_result)

    except json.JSONDecodeError as je:
        print(f"Failed to parse model output as JSON: {je}")
        return jsonify({'error': 'Failed to parse model output'}), 500
    except Exception as e:
        print(f"Error calling Gemini or processing request: {e}")
        return jsonify({'error': 'Failed to analyze content'}), 500

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', debug=True, port=port)
