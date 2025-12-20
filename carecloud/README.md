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
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory (or set them in your environment) with the following keys:

```ini
GEMINI_API_KEY=your_gemini_api_key_here
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_email_app_password
```
*Note: For Gmail, you need to generate an App Password in your Google Account security settings if you have 2FA enabled.*

### 3. Run the Application
```bash
python app.py
```
The app will start at `http://127.0.0.1:5000`.

## Usage Flow
1. **Signup**:
   - Choose your role: **Child** or **Parent**.
   - **Children**: Must provide a parent's email address to link accounts.
   - **Parents**: Create an account to monitor alerts.
2. **Child Dashboard**:
   - Enter text or upload an image to check for harmful content.
   - Receive gentle feedback, toxicity explanations, and positive emotional support suggestions.
3. **Analysis**:
   - The system uses Gemini AI (gemini-1.5-flash) to analyze content.
   - If high toxicity (>70) is detected:
     - An alert is saved to the database.
     - A supportive email is sent to the parent.
4. **Parent Dashboard**:
   - Log in to view an activity feed of alerts for all linked children.
   - View the reason for alerts (severity, explanation) without seeing the raw abusive content (privacy-first).
   - Access guidance on how to have supportive conversations with your child.

## Demo Notes
- If no API key is provided, the app runs in a "Mock Mode" returning safe default values for demonstration purposes.
- To test the email feature, ensure valid SMTP credentials are in `.env`.
