# CareCloud

## Overview
CareCloud is a full-stack AI-powered cyberbullying prevention system designed to support students and teenagers by analyzing text for harmful content using Gemini AI. It provides emotional support messages and alerts parents if high toxicity levels are detected.

## Tech Stack
- **Backend**: Python (Flask)
- **Frontend**: HTML, CSS, JavaScript (served by Flask) - Modern UI with neon purple/pink theme designed for kids
- **Database**: SQLite (SQLAlchemy ORM)
- **AI**: Google Gemini 2.5 Flash (via Replit AI Integrations - no API key needed)
- **OCR**: Tesseract (pytesseract)
- **Email**: SMTP (Gmail)

## Project Structure
```
carecloud/
├── app.py              # Main Flask application with Gemini AI integration
├── static/
│   ├── script.js       # Frontend JavaScript
│   └── style.css       # Kid-friendly neon purple/pink styling
├── templates/
│   ├── base.html       # Base template
│   ├── dashboard.html  # User dashboard for content analysis
│   └── login.html      # Login/signup page
├── requirements.txt    # Python dependencies
└── README.md          # Original documentation
```

## Environment Variables
- `SECRET_KEY`: Flask secret key (has default, should be changed in production)
- `MAIL_USERNAME`: Gmail address for sending alerts (optional)
- `MAIL_PASSWORD`: Gmail app password for SMTP (optional)
- AI Integration vars (automatically set by Replit):
  - `AI_INTEGRATIONS_GEMINI_API_KEY`
  - `AI_INTEGRATIONS_GEMINI_BASE_URL`

## Running the Application
The app runs on port 5000 using Flask development server:
```bash
cd carecloud && python app.py
```

## AI Integration
- Uses Replit's AI Integrations service (built-in, no API key needed)
- Model: Gemini 2.5 Flash (optimized for speed and performance)
- Capabilities: Content analysis, toxicity detection, support message generation
- Charges: Billed to your Replit credits

## Production Deployment
Uses Gunicorn as the WSGI server:
```bash
cd carecloud && gunicorn --bind 0.0.0.0:5000 app:app
```

## Features
1. User signup with parent email for alerts
2. Text analysis for cyberbullying/toxicity using Gemini AI
3. Image upload with OCR text extraction
4. AI-powered toxicity scoring
5. Automatic parent email alerts for high toxicity content (>70)
6. Kid-friendly neon purple/pink UI theme
7. Real-time analysis with streaming support

## UI Design
- Dark theme with neon purple (#a855f7, #b537f2) and hot pink (#ff006e, #ec4899) accent colors
- Glassmorphism effects with backdrop blur
- Gradient text effects for headings
- Responsive design optimized for mobile and desktop
- Animated loading spinners and hover effects
