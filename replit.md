# CareCloud

## Overview
CareCloud is an AI-powered cyberbullying prevention application that analyzes text messages for harmful content. It uses Google Gemini AI and the Perspective API to detect various types of harmful content including harassment, grooming, hate speech, and more.

## Project Structure
```
carecloud/
├── static/
│   ├── script.js       # Frontend JavaScript
│   └── style.css       # Styles
├── templates/
│   ├── base.html       # Base template
│   ├── dashboard.html  # Main dashboard
│   └── login.html      # Login page
├── __init__.py
├── app.py              # Main Flask application
└── README.md

main.py                 # Entry point
requirements.txt        # Python dependencies
```

## Running the Application
The application runs on port 5000 using Flask's development server:
```
python main.py
```

For production, use gunicorn:
```
gunicorn -b 0.0.0.0:5000 main:app
```

## Environment Variables
- `SECRET_KEY` - Flask secret key for sessions
- `PERSPECTIVE_API_KEY` - Google Perspective API key for toxicity detection
- `AI_INTEGRATIONS_GEMINI` - Gemini API key for AI analysis
- `MAIL_USERNAME` - Email username for sending alerts
- `MAIL_PASSWORD` - Email password for sending alerts

## Features
- Text analysis for harmful content detection
- Multiple detection categories: harassment, profanity, hate speech, sexual content, grooming, manipulation, threats, violence, emotional abuse, self-harm risk
- Risk scoring and severity levels
- Parent email alerts for high-risk content
- Session-based authentication

## Recent Changes
- December 26, 2025: Imported from GitHub and configured for Replit environment
  - Set up Python 3.11 runtime
  - Installed required dependencies
  - Configured port 5000 for web preview
  - Added deployment configuration
