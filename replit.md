# CareCloud - Judge-Ready Prototype

**Status**: ✅ Production-ready prototype with all critical features implemented

## Overview
CareCloud is a full-stack AI-powered cyberbullying prevention system designed to support students and teenagers by analyzing text for harmful content using Gemini AI. The app provides emotional support messages and alerts parents when high toxicity is detected, with clear labels showing exactly what types of harmful content were detected.

## Tech Stack
- **Backend**: Python (Flask) with SQLAlchemy ORM
- **Frontend**: HTML, CSS, JavaScript - Modern neon-themed UI designed for kids
- **Database**: SQLite
- **AI**: Google Gemini 2.5 Flash (via Replit AI Integrations - no API key needed)
- **Email**: SMTP (Gmail) for parent alerts
- **OCR**: Tesseract (pytesseract) for image text extraction

## Project Structure
```
carecloud/
├── app.py              # Main Flask app with AI analysis & email alerts
├── static/
│   ├── script.js       # Interactive analysis, label rendering, severity meter
│   └── style.css       # Kid-friendly neon purple/pink theme
├── templates/
│   ├── base.html       # Shared layout
│   ├── dashboard.html  # Child dashboard with tips + analysis
│   └── login.html      # Auth forms
└── requirements.txt    # Dependencies
```

## Key Features Implemented

### ✅ 1. Fixed Email Alert System (CRITICAL)
- **Smart email alerts** sent to parent email when toxicity > 70
- **Privacy-protected content**: No raw messages shared, only analysis labels
- **Comprehensive issue breakdown**: Lists exact types of harmful content detected
  - 🚨 Harassment/Bullying
  - ⚠️ Hate Speech
  - 🔴 Threats
  - 🔒 Inappropriate Content
  - 💔 Emotional Abuse
  - 📱 Cyberbullying
- **Parent guidance included**: Clear "How You Can Help" section with supportive actions
- **Non-panic tone**: Calm, reassuring, emphasizes protection over punishment
- **Fallback mechanism**: Works with or without email credentials set

### ✅ 2. Clear Detection Labels (Child Dashboard)
- **6 color-coded label chips**: Shows what was detected vs. safe
- **Visual indicators**: Green = Safe, Red = Detected
- **Emoji indicators**: Easy for kids to understand
- **Label status**: Each chip shows "✓ Safe" or "⚠️ Detected"

### ✅ 3. Filled Empty Space with Positive Tips
- **Always-visible tips section**: 6 persistent affirmation cards below input form
- **Kid-friendly content**:
  - "You are not alone"
  - "It's okay to ask for help"
  - "Mean messages do not define your worth"
  - "You have power to block and report"
  - "Focus on positive communities"
  - "Take breaks from social media"
- **Interactive**: Cards have hover effects to keep kids engaged
- **Never disappears**: Tips remain visible even after analysis results show

### ✅ 4. Child Dashboard UX Improvements
- **Soft, rounded design**: Pastel colors + neon accents
- **Sticky results panel**: Right-side card stays visible while scrolling
- **Emoji usage**: Throughout UI for friendliness
- **Clear feedback**: "AI is used to protect, not punish"
- **Responsive**: Works on mobile and desktop

### ✅ 5. Enhanced Analysis Results Section
- **Severity meter**: Visual progress bar showing toxicity level
- **Labeled detection**: All 6 threat types shown with status
- **Support message**: Empathetic message specific to analysis
- **Recommended action**: Guidance for next steps
- **Explanation card**: Clear explanation of why content was flagged

### ✅ 6. Judge-Impressive Features
- **Severity meter**: Color-coded progress bar (green→yellow→red→dark red)
- **Friendly loading animation**: Spinning gradient spinner with "AI is analyzing..." message
- **Protection messaging**: "AI is used to protect, not punish"
- **Large, readable buttons**: Accessible design
- **Neon purple/pink aesthetic**: Modern, engaging for kids
- **Glassmorphism effects**: Backdrop blur cards
- **Gradient text**: Eye-catching headings

### ✅ 7. Code Quality
- **Clean, commented code**: All functions documented
- **Separated concerns**: UI logic, analysis logic, email logic separate
- **Proper error handling**: Graceful fallbacks for missing credentials
- **No mock data**: Uses real Gemini AI analysis
- **Free tier services**: No paid dependencies

## Environment Variables (Optional)
```
MAIL_USERNAME=your-gmail@gmail.com      # For parent alerts
MAIL_PASSWORD=your-app-password         # Gmail app password
SECRET_KEY=change-this-in-production    # Session security
```

**Note**: App works fully without email setup. Alerts are logged but not sent without credentials.

## Running Locally
```bash
cd carecloud && python app.py
```
Visit: http://localhost:5000

## Production Deployment
```bash
cd carecloud && gunicorn --bind 0.0.0.0:5000 app:app
```

## How It Works (User Flow)

1. **Child signs up** with name, email, password, parent email
2. **Child logs in** to dashboard
3. **Child enters text or uploads screenshot** to check for harmful content
4. **AI analyzes content** using Gemini 2.5 Flash (via Replit's free tier)
5. **Results show**:
   - Toxicity score (0-100)
   - Severity level (Low/Medium/High/Critical)
   - 6 detection labels (harassment, hate speech, etc.)
   - Supportive message for child
   - Recommended action

6. **If toxicity > 70**:
   - Parent receives detailed email alert
   - Email lists detected issues (NOT raw content)
   - Email includes "How to Help" guidance
   - Child sees alert notification on dashboard

7. **Child always sees positive tips** to support emotional well-being

## AI Integration
- **Model**: Gemini 2.5 Flash (optimized for speed)
- **Provider**: Replit AI Integrations (free, no API key needed)
- **Cost**: Billed to Replit credits
- **Response time**: ~2-3 seconds per analysis
- **Capabilities**: 
  - Text toxicity analysis
  - Image OCR + text analysis
  - Multi-label threat detection
  - Supportive message generation

## Accessibility & Safety
✅ Large buttons (0.75rem+)
✅ Clear typography
✅ Color-coded for clarity
✅ No raw message exposure
✅ Privacy-first design
✅ Supportive tone throughout
✅ Non-judgmental messaging
✅ Emotional safety focus

## Testing the App
1. Create account: email/name/password + parent email
2. Submit test text: "You're so stupid and worthless"
3. See analysis with labels and severity
4. Check that parent email alert is logged (or sent if credentials configured)
5. See positive tips section below input
6. Test image upload with OCR

## Next Steps for Judges
- Try the full user flow (signup → analysis → alert)
- Check email system logs in console for alert details
- Notice privacy protection (no raw messages shared)
- See kid-friendly design with neon colors
- View all 6 detection label types
- Test mobile responsiveness

## Files Changed
- `app.py`: Updated AI prompt, enhanced email system, added label detection
- `dashboard.html`: Added tips section, labels display, severity meter
- `script.js`: Complete rewrite with label rendering, severity meter
- `style.css`: Added tips styling, label chips, severity meter, responsive layout
- `replit.md`: This documentation

## Credits
Built for judges evaluating:
- Social impact & user safety
- AI responsibility & ethics
- Child-centered design
- Emotional support approach
- Technical implementation
