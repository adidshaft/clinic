from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from openai import OpenAI
import os
import re
from datetime import datetime, timedelta
import json
import warnings
import uuid

# SendGrid imports
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

# Google Calendar imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variable (optional: only needed locally)
from dotenv import load_dotenv
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "your-secret-key"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# SendGrid Configuration
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
FROM_EMAIL = 'noreply@clinic-vnpy.onrender.com'  # Replace with your verified sender

# Google Calendar configuration - Updated scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/calendar.readonly'
]
CLIENT_SECRETS_FILE = 'client_secret.json'

# OAuth Configuration - handles both local and production
if os.getenv('FLASK_ENV') == 'production' or 'onrender.com' in os.getenv('RENDER_EXTERNAL_URL', ''):
    # Production URLs
    OAUTH_REDIRECT_URI = 'https://clinic-vnpy.onrender.com/google-calendar-callback'
else:
    # Local development URLs
    OAUTH_REDIRECT_URI = 'http://localhost:5000/google-calendar-callback'

# Temporary doctor store
doctors = {
    "drlee": "password123",
    "drsmith": "clinicpass"
}

# User Class
class Doctor(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return Doctor(user_id)

@app.route('/login', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if doctors.get(username) == password:
            user = Doctor(username)
            login_user(user)
            return redirect(url_for("clinic_dashboard"))
        else:
            return "Invalid credentials", 401
    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

@app.errorhandler(500)
def internal_error(e):
    return f"Something broke: {str(e)}", 500

# In-memory storage for appointments (now with full patient details)
appointments = []

# Initialize OpenAI client (for SDK v1.x)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/')
def index():
    return render_template('index.html')

# Email helper functions
def send_appointment_confirmation_email(patient_info, appointment_details):
    """Send appointment confirmation email using SendGrid"""
    if not SENDGRID_API_KEY:
        print("SendGrid API key not configured")
        return False
    
    try:
        # Create the email content
        subject = f"Appointment Confirmation - {appointment_details['time']}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #007bff; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 8px 8px; }}
                .appointment-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 5px 0; border-bottom: 1px solid #eee; }}
                .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 14px; }}
                .confirmation-id {{ background: #28a745; color: white; padding: 10px; text-align: center; border-radius: 4px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏥 AI Clinic</h1>
                    <h2>Appointment Confirmation</h2>
                </div>
                
                <div class="content">
                    <p>Dear {patient_info['firstName']} {patient_info['lastName']},</p>
                    
                    <p>Your appointment has been successfully scheduled! Here are the details:</p>
                    
                    <div class="confirmation-id">
                        <strong>Confirmation ID: {appointment_details['confirmationId']}</strong>
                    </div>
                    
                    <div class="appointment-details">
                        <h3>Appointment Details</h3>
                        <div class="detail-row">
                            <span><strong>Doctor:</strong></span>
                            <span>Dr. Lee</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Date & Time:</strong></span>
                            <span>{appointment_details['time']}</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Reason:</strong></span>
                            <span>{appointment_details['reason']}</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Patient:</strong></span>
                            <span>{patient_info['firstName']} {patient_info['lastName']}</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Age:</strong></span>
                            <span>{patient_info['age']} years old</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Phone:</strong></span>
                            <span>{patient_info['phone']}</span>
                        </div>
                        {f'''<div class="detail-row">
                            <span><strong>Medical ID:</strong></span>
                            <span>{patient_info['medicalId']}</span>
                        </div>''' if patient_info.get('medicalId') else ''}
                        {f'''<div class="detail-row">
                            <span><strong>Known Allergies:</strong></span>
                            <span>{patient_info['allergies']}</span>
                        </div>''' if patient_info.get('allergies') else ''}
                    </div>
                    
                    <div style="background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 4px; margin: 20px 0;">
                        <h4 style="margin: 0 0 10px 0; color: #856404;">📋 Important Reminders:</h4>
                        <ul style="margin: 0; padding-left: 20px;">
                            <li>Please arrive <strong>15 minutes early</strong> for check-in</li>
                            <li>Bring a valid government-issued ID</li>
                            <li>Bring your insurance card (if applicable)</li>
                            <li>List of current medications</li>
                            <li>Wear a mask if you have any cold symptoms</li>
                        </ul>
                    </div>
                    
                    <p>If you need to reschedule or cancel your appointment, please contact us at least 24 hours in advance.</p>
                    
                    <p>We look forward to seeing you!</p>
                    
                    <p>Best regards,<br>
                    <strong>AI Clinic Team</strong></p>
                </div>
                
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                    <p>If you have questions, please visit our website or call our office.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Create the email
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=patient_info['email'],
            subject=subject,
            html_content=html_content
        )
        
        # Send the email
        sg = SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sg.send(message)
        
        print(f"Email sent successfully. Status code: {response.status_code}")
        return True
        
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_doctor_notification_email(doctor_email, patient_info, appointment_details):
    """Send new appointment notification to doctor"""
    if not SENDGRID_API_KEY:
        return False
    
    try:
        subject = f"New Appointment Booked - {appointment_details['time']}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #28a745; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #f8f9fa; padding: 30px; border-radius: 0 0 8px 8px; }}
                .patient-details {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .detail-row {{ display: flex; justify-content: space-between; margin: 10px 0; padding: 5px 0; border-bottom: 1px solid #eee; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🏥 AI Clinic - Doctor Portal</h1>
                    <h2>New Appointment Notification</h2>
                </div>
                
                <div class="content">
                    <p>Dear Dr. Lee,</p>
                    
                    <p>A new appointment has been booked through the patient portal:</p>
                    
                    <div class="patient-details">
                        <h3>Patient Information</h3>
                        <div class="detail-row">
                            <span><strong>Patient:</strong></span>
                            <span>{patient_info['firstName']} {patient_info['lastName']}</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Age:</strong></span>
                            <span>{patient_info['age']} years old ({patient_info['gender']})</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Contact:</strong></span>
                            <span>{patient_info['phone']} | {patient_info['email']}</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Appointment Time:</strong></span>
                            <span>{appointment_details['time']}</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Chief Complaint:</strong></span>
                            <span>{appointment_details['reason']}</span>
                        </div>
                        <div class="detail-row">
                            <span><strong>Confirmation ID:</strong></span>
                            <span>{appointment_details['confirmationId']}</span>
                        </div>
                        {f'''<div class="detail-row">
                            <span><strong>Medical ID:</strong></span>
                            <span>{patient_info['medicalId']}</span>
                        </div>''' if patient_info.get('medicalId') else ''}
                        {f'''<div class="detail-row">
                            <span><strong>Emergency Contact:</strong></span>
                            <span>{patient_info['emergencyContact']} ({patient_info['emergencyPhone']})</span>
                        </div>''' if patient_info.get('emergencyContact') else ''}
                        {f'''<div class="detail-row">
                            <span><strong>Known Allergies:</strong></span>
                            <span style="color: #dc3545; font-weight: bold;">{patient_info['allergies']}</span>
                        </div>''' if patient_info.get('allergies') else ''}
                    </div>
                    
                    <p>The appointment has been automatically added to your Google Calendar (if connected).</p>
                    
                    <p>Best regards,<br>
                    <strong>AI Clinic System</strong></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=doctor_email,
            subject=subject,
            html_content=html_content
        )
        
        sg = SendGridAPIClient(api_key=SENDGRID_API_KEY)
        response = sg.send(message)
        
        print(f"Doctor notification sent. Status code: {response.status_code}")
        return True
        
    except Exception as e:
        print(f"Error sending doctor notification: {e}")
        return False

# Google Calendar Helper Functions (keeping existing functions)
def get_google_calendar_service():
    """Get Google Calendar service object"""
    try:
        creds = None
        doctor_id = current_user.get_id()
        token_file = f'token_{doctor_id}.json'
        
        print(f"Looking for token file: {token_file}")
        
        # Load existing credentials
        if os.path.exists(token_file):
            try:
                creds = Credentials.from_authorized_user_file(token_file, SCOPES)
                print("Credentials loaded from file")
            except Exception as load_error:
                print(f"Error loading credentials: {load_error}")
                return None
        else:
            print("No token file found")
            return None
        
        # If credentials are not valid, try to refresh
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    print("Refreshing expired credentials")
                    creds.refresh(Request())
                    # Save the refreshed credentials
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
                    print("Credentials refreshed and saved")
                except Exception as refresh_error:
                    print(f"Error refreshing credentials: {refresh_error}")
                    return None
            else:
                print("Credentials are invalid and cannot be refreshed")
                return None
        
        try:
            service = build('calendar', 'v3', credentials=creds)
            print("Google Calendar service built successfully")
            return service
        except Exception as build_error:
            print(f"Error building service: {build_error}")
            return None
            
    except Exception as e:
        print(f"Error in get_google_calendar_service: {e}")
        return None

def create_google_calendar_event(patient_info, appointment_time, reason):
    """Create an event in Google Calendar with patient details"""
    service = get_google_calendar_service()
    if not service:
        return None
    
    try:
        # Parse the time - enhanced version with patient info
        event_start = datetime.now() + timedelta(days=1)  # Default to tomorrow
        
        # Try to parse common time formats
        if 'monday' in appointment_time.lower():
            days_ahead = 0 - datetime.now().weekday()
            if days_ahead <= 0:
                days_ahead += 7
            event_start = datetime.now() + timedelta(days=days_ahead)
        elif 'friday' in appointment_time.lower():
            days_ahead = 4 - datetime.now().weekday()
            if days_ahead <= 0:
                days_ahead += 7
            event_start = datetime.now() + timedelta(days=days_ahead)
        # Add more day parsing as needed
        
        # Set time
        if '3pm' in appointment_time.lower():
            event_start = event_start.replace(hour=15, minute=0)
        elif '2pm' in appointment_time.lower():
            event_start = event_start.replace(hour=14, minute=0)
        elif '10am' in appointment_time.lower():
            event_start = event_start.replace(hour=10, minute=0)
        else:
            event_start = event_start.replace(hour=10, minute=0)  # Default 10 AM
        
        event_end = event_start + timedelta(hours=1)  # 1 hour appointment
        
        # Create detailed event description
        description = f"""Patient: {patient_info['firstName']} {patient_info['lastName']}
Age: {patient_info['age']} ({patient_info['gender']})
Phone: {patient_info['phone']}
Email: {patient_info['email']}
Chief Complaint: {reason}
{f"Medical ID: {patient_info['medicalId']}" if patient_info.get('medicalId') else ""}
{f"Allergies: {patient_info['allergies']}" if patient_info.get('allergies') else ""}
{f"Emergency Contact: {patient_info['emergencyContact']} ({patient_info['emergencyPhone']})" if patient_info.get('emergencyContact') else ""}

Booked via AI Clinic Patient Portal"""
        
        event = {
            'summary': f"{patient_info['firstName']} {patient_info['lastName']} - {reason}",
            'description': description,
            'start': {
                'dateTime': event_start.isoformat(),
                'timeZone': 'America/New_York',  # Adjust timezone as needed
            },
            'end': {
                'dateTime': event_end.isoformat(),
                'timeZone': 'America/New_York',
            },
            'attendees': [
                {'email': patient_info['email'], 'displayName': f"{patient_info['firstName']} {patient_info['lastName']}"}
            ],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 24 hours before
                    {'method': 'popup', 'minutes': 60},       # 1 hour before
                ],
            },
        }
        
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return created_event.get('id')
    
    except Exception as e:
        print(f"Error creating Google Calendar event: {e}")
        return None

# New appointment booking endpoint
@app.route('/api/book-appointment', methods=['POST'])
def book_appointment():
    """Complete appointment booking with patient details and email notifications"""
    try:
        data = request.json
        patient_info = data.get('patientInfo', {})
        health_concern = data.get('healthConcern', '')
        appointment_time = data.get('appointmentTime', '')
        location = data.get('location', '')
        
        # Generate confirmation ID
        confirmation_id = f"AC{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:8].upper()}"
        
        # Create appointment record
        appointment = {
            "patient": f"{patient_info['firstName']} {patient_info['lastName']}",
            "patientInfo": patient_info,
            "time": appointment_time,
            "reason": health_concern,
            "location": location,
            "doctor_id": "drlee",  # Default doctor
            "status": "confirmed",
            "confirmationId": confirmation_id,
            "bookedAt": datetime.now().isoformat(),
            "source": "patient_portal"
        }
        
        # Check for conflicts one more time
        existing = next((apt for apt in appointments 
                        if apt.get("time") == appointment_time and 
                        apt.get("doctor_id") == "drlee"), None)
        
        if existing:
            return jsonify({
                "success": False,
                "error": "This time slot is no longer available. Please choose a different time."
            })
        
        # Add to appointments
        appointments.append(appointment)
        
        # Create Google Calendar event
        google_event_id = create_google_calendar_event(patient_info, appointment_time, health_concern)
        if google_event_id:
            appointment["google_event_id"] = google_event_id
        
        # Send confirmation email to patient
        appointment_details = {
            "time": appointment_time,
            "reason": health_concern,
            "confirmationId": confirmation_id
        }
        
        email_sent = send_appointment_confirmation_email(patient_info, appointment_details)
        
        # Send notification to doctor (you can add doctor's email here)
        doctor_email = "doctor@clinic.com"  # Replace with actual doctor email
        send_doctor_notification_email(doctor_email, patient_info, appointment_details)
        
        return jsonify({
            "success": True,
            "confirmationId": confirmation_id,
            "message": f"Appointment confirmed for {appointment_time}",
            "emailSent": email_sent
        })
        
    except Exception as e:
        print(f"Error booking appointment: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to book appointment. Please try again."
        })

# Keep all existing routes and functions...
# (I'll include the key ones but keeping the same structure)

@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.json
    user_input = data.get("message")
    location = data.get("location", "unknown")

    # Handle appointment requests with availability check
    name = "New Patient"
    reason = user_input
    time = "Tomorrow 10 AM"  # Default placeholder
    
    # Extract time from user input
    if "friday" in user_input.lower():
        if "10" in user_input or "10am" in user_input.lower():
            time = "Friday 10:00 AM"
        else:
            time = "Friday Morning"
    elif "saturday" in user_input.lower():
        if "11" in user_input or "11am" in user_input.lower():
            time = "Saturday 11:00 AM"
        else:
            time = "Saturday Morning"
    elif "sunday" in user_input.lower():
        if "9" in user_input or "9am" in user_input.lower():
            time = "Sunday 9:00 AM"
        else:
            time = "Sunday Morning"
    elif "monday" in user_input.lower():
        if "2" in user_input or "2pm" in user_input.lower():
            time = "Monday 2:00 PM"
        else:
            time = "Monday Afternoon"
    elif "tomorrow" in user_input.lower():
        time = "Tomorrow 10:00 AM"
    elif "today" in user_input.lower():
        time = "Today (if available)"
    
    # Check for appointment request keywords
    if any(word in user_input.lower() for word in ["appointment", "book", "schedule", "see doctor", "visit", "consultation"]):
        # Check if this time slot is already taken
        existing_appointment = next((apt for apt in appointments if apt.get("time") == time and apt.get("doctor_id") == "drlee"), None)
        
        if existing_appointment:
            response_text = f"❌ Sorry, Dr. Lee is not available at {time}. That slot is already booked. Please try a different time."
        else:
            # Show availability and ask for confirmation
            response_text = f"✅ Great! Dr. Lee is available at {time} for your concern: '{reason}'. Would you like to book this appointment?"
    else:
        # Just health inquiry, don't check availability
        response_text = f"Thank you for your health inquiry about '{reason}'. If you'd like to schedule an appointment, please mention 'appointment' or 'book' in your message."

    return jsonify({"response": response_text})

# Keep all existing Google Calendar and clinic routes...
# (Including sync_from_google_calendar, parse_appointment_command, etc.)

@app.route('/clinic')
@login_required
def clinic_dashboard():
    # Sync with Google Calendar when loading dashboard
    try:
        sync_from_google_calendar()
    except:
        pass  # Don't fail if sync fails
    
    doc_id = current_user.get_id()
    filtered = [a for a in appointments if a.get("doctor_id") == doc_id]
    
    # Check if Google Calendar is connected
    token_file = f'token_{doc_id}.json'
    google_connected = os.path.exists(token_file)
    
    return render_template("clinic.html", appointments=filtered, google_connected=google_connected)

# Include all other existing routes...
# (OAuth routes, clinic-ai, etc.)

if __name__ == '__main__':
    app.run(debug=True)