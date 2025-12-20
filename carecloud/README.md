# CareCloud
Full-Stack AI-Powered Cyberbullying Prevention System

CareCloud is a web application designed to support students and teenagers by analyzing text for harmful content using Gemini AI. It provides emotional support messages and alerts parents if high toxicity levels are detected.

## Tech Stack
- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Python (Flask)
- **Database**: SQLite (SQLAlchemy)
- **AI**: Google Gemini API
- **Email**: SMTP (Gmail)

## Setup Instructions

### 1. Install Dependencies

Make sure you have system dependencies for OCR (Tesseract) installed, then install Python deps:

Ubuntu / Debian:
```bash
sudo apt-get update && sudo apt-get install -y tesseract-ocr
```

macOS (Homebrew):
```bash
brew install tesseract
```

Then install Python requirements:
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory (or set them in your environment) with the following keys:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_email_app_password
SECRET_KEY=change_this_to_a_secure_random_value
```

*Note: For Gmail, you need to generate an App Password in your Google Account security settings if you have 2FA enabled.*

### 3. Run the Application (development)

```bash
python app.py
```

By default the app binds to 0.0.0.0 and uses port 5000. To change the port set the PORT env var.

### 4. Production / Hosting Notes
- Use a production WSGI server like Gunicorn. Example Procfile for platforms like Heroku/Render:
```
web: gunicorn -w 4 -b 0.0.0.0:$PORT app:app
```
- Make sure SECRET_KEY is set to a secure value in production.
- Ensure GEMINI_API_KEY and SMTP credentials are configured in the host environment.

## Usage Flow
1. **Signup**: Create an account with your name, email, password, and a parent's email.
2. **Dashboard**: Enter text in the analysis box or upload a screenshot.
3. **Analyze**: Click "Analyze Content". The system will use Gemini AI to check for toxicity. If an image is uploaded, OCR will extract text for analysis.
4. **Results**:
   - View the toxicity score and severity.
   - Read the explanation and support message.
   - If the score is > 70 (High/Critical), an email is automatically sent to the parent email provided during signup.

## Demo Notes
- If no API key is provided, the app runs in a "Mock Mode" returning safe default values for demonstration purposes.
- To test the email feature, ensure valid SMTP credentials are in `.env`.
