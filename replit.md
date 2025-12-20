# CareCloud

## Overview
CareCloud is a full-stack AI-powered cyberbullying prevention system designed to support students and teenagers by analyzing text for harmful content using Gemini AI. It provides emotional support messages and alerts parents if high toxicity levels are detected.

## Tech Stack
- **Backend**: Python (Flask)
- **Frontend**: HTML, CSS, JavaScript (served by Flask)
- **Database**: SQLite (SQLAlchemy ORM)
- **AI**: Google Gemini API
- **OCR**: Tesseract (pytesseract)
- **Email**: SMTP (Gmail)

## Project Structure
```
carecloud/
├── app.py              # Main Flask application
├── static/
│   ├── script.js       # Frontend JavaScript
│   └── style.css       # Styles
├── templates/
│   ├── base.html       # Base template
│   ├── dashboard.html  # User dashboard
│   └── login.html      # Login/signup page
├── requirements.txt    # Python dependencies
└── README.md          # Original documentation
```

## Environment Variables
- `GEMINI_API_KEY`: Google Gemini API key for AI analysis
- `MAIL_USERNAME`: Gmail address for sending alerts
- `MAIL_PASSWORD`: Gmail app password for SMTP
- `SECRET_KEY`: Flask secret key (has default, should be changed in production)

## Running the Application
The app runs on port 5000 using the Flask development server:
```bash
cd carecloud && python app.py
```

## Production Deployment
Uses Gunicorn as the WSGI server:
```bash
cd carecloud && gunicorn --bind 0.0.0.0:5000 app:app
```

## Features
1. User signup with parent email for alerts
2. Text analysis for cyberbullying/toxicity
3. Image upload with OCR text extraction
4. AI-powered toxicity scoring
5. Automatic parent email alerts for high toxicity content
