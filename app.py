from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from openai import OpenAI
import os
import re
from datetime import datetime, timedelta
import json
import warnings
import uuid

# Google Calendar imports
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Load environment variable (optional: only needed locally)
from dotenv import load_dotenv
load_dotenv()

# Import our enhanced email service
try:
    from utils.email_notifications import EmailNotificationService
    email_service = EmailNotificationService()
    EMAIL_SERVICE_AVAILABLE = True
except ImportError:
    print("⚠️ Email service not available. Create utils/email_notifications.py to enable email functionality.")
    EMAIL_SERVICE_AVAILABLE = False

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "your-secret-key"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Configuration for doctor emails (add to environment variables)
DOCTOR_EMAILS = {
    "drlee": os.getenv('DR_LEE_EMAIL', 'dr.lee@clinic.com'),
    "drsmith": os.getenv('DR_SMITH_EMAIL', 'dr.smith@clinic.com')
}

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

# Google Calendar Helper Functions
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

def sync_from_google_calendar():
    """Sync appointments from Google Calendar"""
    service = get_google_calendar_service()
    if not service:
        print("Cannot sync: Google Calendar service not available")
        return
    
    try:
        # Get events from the next 30 days
        now = datetime.utcnow().isoformat() + 'Z'
        future = (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=future,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        doctor_id = current_user.get_id()
        
        for event in events:
            # Check if this event is already in our appointments
            event_id = event.get('id')
            existing = next((apt for apt in appointments 
                           if apt.get("google_event_id") == event_id), None)
            
            if not existing:
                # Add this Google Calendar event as an appointment
                start = event['start'].get('dateTime', event['start'].get('date'))
                summary = event.get('summary', 'Appointment')
                description = event.get('description', '')
                
                # Parse the start time to a readable format
                if 'T' in start:
                    dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
                    time_str = dt.strftime('%A %I:%M %p')
                else:
                    time_str = start
                
                appointment = {
                    "patient": summary,
                    "time": time_str,
                    "reason": description[:100] if description else "Calendar appointment",
                    "location": "Google Calendar",
                    "doctor_id": doctor_id,
                    "status": "confirmed",
                    "google_event_id": event_id,
                    "source": "google_calendar"
                }
                
                appointments.append(appointment)
        
        print(f"Synced {len(events)} events from Google Calendar")
        
    except Exception as e:
        print(f"Error syncing from Google Calendar: {e}")

# Enhanced appointment booking endpoint with email notifications
@app.route('/api/book-appointment', methods=['POST'])
def book_appointment():
    """Complete appointment booking with patient details and email notifications"""
    try:
        data = request.json
        patient_info = data.get('patientInfo', {})
        health_concern = data.get('healthConcern', '')
        appointment_time = data.get('appointmentTime', '')
        location = data.get('location', '')
        
        # Validate required fields
        required_fields = ['firstName', 'lastName', 'age', 'gender', 'email', 'phone']
        missing_fields = [field for field in required_fields if not patient_info.get(field)]
        
        if missing_fields:
            return jsonify({
                "success": False,
                "error": f"Missing required fields: {', '.join(missing_fields)}"
            })
        
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
        
        # Create appointment details for email
        appointment_details = {
            "time": appointment_time,
            "reason": health_concern,
            "confirmationId": confirmation_id
        }
        
        # Send confirmation email to patient
        patient_email_sent = False
        if EMAIL_SERVICE_AVAILABLE:
            patient_email_sent = email_service.send_appointment_confirmation(
                patient_info, appointment_details
            )
        
        # Send notification to assigned doctor
        doctor_email = DOCTOR_EMAILS.get("drlee")
        doctor_email_sent = False
        if EMAIL_SERVICE_AVAILABLE and doctor_email:
            doctor_email_sent = email_service.send_doctor_notification(
                doctor_email, patient_info, appointment_details
            )
        
        # Create Google Calendar event (keep existing functionality)
        google_event_id = None
        try:
            google_event_id = create_google_calendar_event(patient_info, appointment_time, health_concern)
            if google_event_id:
                appointment["google_event_id"] = google_event_id
        except Exception as e:
            print(f"⚠️ Google Calendar sync failed: {e}")
        
        # Log email results
        email_status = {
            "patient_email": "sent" if patient_email_sent else "failed" if EMAIL_SERVICE_AVAILABLE else "service_unavailable",
            "doctor_email": "sent" if doctor_email_sent else "failed" if (EMAIL_SERVICE_AVAILABLE and doctor_email) else "no_email_configured"
        }
        
        print(f"📧 Email Status - Patient: {email_status['patient_email']}, Doctor: {email_status['doctor_email']}")
        
        return jsonify({
            "success": True,
            "confirmationId": confirmation_id,
            "message": f"Appointment confirmed for {appointment_time}",
            "emailSent": patient_email_sent,
            "googleCalendarSynced": google_event_id is not None,
            "emailStatus": email_status
        })
        
    except Exception as e:
        print(f"❌ Error booking appointment: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to book appointment. Please try again."
        })

# Patient AI endpoint
# Replace the /api/ask endpoint in your app.py with this fixed version:

@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.json
    user_input = data.get("message", "")
    location = data.get("location", "unknown")

    if not user_input.strip():
        return jsonify({"response": "Please enter your health concern."})

    # Handle appointment requests with availability check
    reason = user_input
    time = "Tomorrow 10:00 AM"  # Default placeholder
    
    # Extract time from user input with better parsing
    user_input_lower = user_input.lower()
    
    # Day parsing
    if "friday" in user_input_lower:
        if "10" in user_input_lower or "10am" in user_input_lower:
            time = "Friday 10:00 AM"
        elif "11" in user_input_lower or "11am" in user_input_lower:
            time = "Friday 11:00 AM"
        elif "2" in user_input_lower or "2pm" in user_input_lower:
            time = "Friday 2:00 PM"
        elif "3" in user_input_lower or "3pm" in user_input_lower:
            time = "Friday 3:00 PM"
        else:
            time = "Friday 10:00 AM"
    elif "saturday" in user_input_lower:
        if "11" in user_input_lower or "11am" in user_input_lower:
            time = "Saturday 11:00 AM"
        elif "10" in user_input_lower or "10am" in user_input_lower:
            time = "Saturday 10:00 AM"
        elif "2" in user_input_lower or "2pm" in user_input_lower:
            time = "Saturday 2:00 PM"
        else:
            time = "Saturday 11:00 AM"
    elif "sunday" in user_input_lower:
        if "9" in user_input_lower or "9am" in user_input_lower:
            time = "Sunday 9:00 AM"
        elif "10" in user_input_lower or "10am" in user_input_lower:
            time = "Sunday 10:00 AM"
        else:
            time = "Sunday 9:00 AM"
    elif "monday" in user_input_lower:
        if "2" in user_input_lower or "2pm" in user_input_lower:
            time = "Monday 2:00 PM"
        elif "3" in user_input_lower or "3pm" in user_input_lower:
            time = "Monday 3:00 PM"
        elif "10" in user_input_lower or "10am" in user_input_lower:
            time = "Monday 10:00 AM"
        else:
            time = "Monday 2:00 PM"
    elif "tuesday" in user_input_lower:
        time = "Tuesday 10:00 AM"
    elif "wednesday" in user_input_lower:
        time = "Wednesday 10:00 AM"
    elif "thursday" in user_input_lower:
        time = "Thursday 10:00 AM"
    elif "tomorrow" in user_input_lower:
        time = "Tomorrow 10:00 AM"
    elif "today" in user_input_lower:
        time = "Today 2:00 PM"

    # Check for appointment request keywords
    appointment_keywords = [
        "appointment", "book", "schedule", "see doctor", "visit", 
        "consultation", "meet", "checkup", "exam", "appointment"
    ]
    
    is_appointment_request = any(word in user_input_lower for word in appointment_keywords)
    
    if is_appointment_request:
        # Check if this time slot is already taken
        existing_appointment = next((apt for apt in appointments 
                                   if apt.get("time") == time and 
                                   apt.get("doctor_id") == "drlee"), None)
        
        if existing_appointment:
            # Suggest alternative times
            alternative_times = [
                "Friday 11:00 AM", "Saturday 10:00 AM", "Monday 3:00 PM", 
                "Tuesday 10:00 AM", "Wednesday 2:00 PM"
            ]
            
            # Find an available alternative
            available_alternative = None
            for alt_time in alternative_times:
                if not next((apt for apt in appointments 
                           if apt.get("time") == alt_time and 
                           apt.get("doctor_id") == "drlee"), None):
                    available_alternative = alt_time
                    break
            
            if available_alternative:
                response_text = f"❌ Sorry, Dr. Lee is not available at {time}. That slot is already booked. However, Dr. Lee is available at {available_alternative}. Would you like to book this appointment?"
            else:
                response_text = f"❌ Sorry, Dr. Lee is not available at {time}. That slot is already booked. Please try a different time or contact us directly."
        else:
            # Show availability with the exact pattern the frontend expects
            response_text = f"✅ Great! Dr. Lee is available at {time} for your concern about '{reason}'. Would you like to book this appointment?"
    else:
        # Just health inquiry, provide helpful response and suggest booking
        if any(symptom in user_input_lower for symptom in ["headache", "pain", "sick", "fever", "cough", "cold"]):
            response_text = f"I understand you're experiencing health concerns about '{reason}'. For proper diagnosis and treatment, I recommend scheduling an appointment with Dr. Lee. You can say something like 'I would like to book an appointment for Friday 10am' to schedule a visit."
        else:
            response_text = f"Thank you for your health inquiry about '{reason}'. If you'd like to schedule an appointment with Dr. Lee, please mention 'appointment' or 'book' along with your preferred day and time."

    return jsonify({"response": response_text})

# Google Calendar OAuth routes
@app.route('/api/google-calendar-connect', methods=['POST'])
@login_required
def google_calendar_connect():
    """Initiate Google Calendar OAuth flow"""
    try:
        if not os.path.exists(CLIENT_SECRETS_FILE):
            return jsonify({
                "success": False,
                "error": "Google OAuth not configured. Missing client_secret.json file."
            })
        
        # Create flow instance
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES
        )
        flow.redirect_uri = OAUTH_REDIRECT_URI
        
        # Generate authorization URL
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true'
        )
        
        # Store state in session
        session['oauth_state'] = state
        
        return jsonify({
            "success": True,
            "redirect": True,
            "redirect_url": authorization_url
        })
        
    except Exception as e:
        print(f"Error initiating Google OAuth: {e}")
        return jsonify({
            "success": False,
            "error": f"OAuth initialization failed: {str(e)}"
        })

@app.route('/google-calendar-callback')
@login_required
def google_calendar_callback():
    """Handle Google Calendar OAuth callback"""
    try:
        # Verify state parameter
        state = session.get('oauth_state')
        if not state:
            return redirect('/clinic?error=no_state')
        
        # Create flow instance
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state
        )
        flow.redirect_uri = OAUTH_REDIRECT_URI
        
        # Get authorization response
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)
        
        # Save credentials
        credentials = flow.credentials
        doctor_id = current_user.get_id()
        token_file = f'token_{doctor_id}.json'
        
        with open(token_file, 'w') as token:
            token.write(credentials.to_json())
        
        # Clear session state
        session.pop('oauth_state', None)
        
        # Sync existing appointments
        sync_from_google_calendar()
        
        return redirect('/clinic?connected=true')
        
    except Exception as e:
        print(f"OAuth callback error: {e}")
        return redirect('/clinic?error=callback_failed')

@app.route('/api/google-calendar-sync', methods=['POST'])
@login_required
def google_calendar_sync():
    """Manually sync with Google Calendar"""
    try:
        sync_from_google_calendar()
        return jsonify({
            "success": True,
            "message": "Calendar synced successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

# Doctor AI assistant
def parse_appointment_command(message):
    """Parse doctor's natural language commands for appointment management"""
    message = message.lower().strip()
    
    # ADD appointment patterns
    add_patterns = [
        r'add appointment for (\w+(?:\s+\w+)*) on (\w+(?:\s+\d+(?:am|pm))*) for (.+)',
        r'create appointment for (\w+(?:\s+\w+)*) at (\w+(?:\s+\d+(?:am|pm))*) for (.+)',
        r'schedule (\w+(?:\s+\w+)*) on (\w+(?:\s+\d+(?:am|pm))*) for (.+)'
    ]
    
    for pattern in add_patterns:
        match = re.search(pattern, message)
        if match:
            patient_name = match.group(1).title()
            time = match.group(2).title()
            reason = match.group(3)
            return "add", {"patient": patient_name, "time": time, "reason": reason}
    
    # MODIFY appointment patterns
    modify_patterns = [
        r'reschedule (\w+(?:\s+\d+(?:am|pm))*) (?:appointment )?to (\w+(?:\s+\d+(?:am|pm))*)',
        r'move (\w+(?:\s+\d+(?:am|pm))*) (?:appointment )?to (\w+(?:\s+\d+(?:am|pm))*)',
        r'change (\w+(?:\s+\d+(?:am|pm))*) (?:appointment )?to (\w+(?:\s+\d+(?:am|pm))*)'
    ]
    
    for pattern in modify_patterns:
        match = re.search(pattern, message)
        if match:
            old_time = match.group(1).title()
            new_time = match.group(2).title()
            return "modify", {"old_time": old_time, "new_time": new_time}
    
    # DELETE appointment patterns
    delete_patterns = [
        r'cancel (?:the )?(\w+(?:\s+\d+(?:am|pm))*) appointment',
        r'delete (?:the )?(\w+(?:\s+\d+(?:am|pm))*) appointment',
        r'remove (?:the )?(\w+(?:\s+\d+(?:am|pm))*) appointment'
    ]
    
    for pattern in delete_patterns:
        match = re.search(pattern, message)
        if match:
            time = match.group(1).title()
            return "delete", {"time": time}
    
    # BLOCK time patterns
    block_patterns = [
        r'block (\w+(?:\s+from\s+\d+(?:am|pm)\s+to\s+\d+(?:am|pm))*)',
        r'reserve (\w+(?:\s+from\s+\d+(?:am|pm)\s+to\s+\d+(?:am|pm))*)'
    ]
    
    for pattern in block_patterns:
        match = re.search(pattern, message)
        if match:
            time_block = match.group(1).title()
            return "block", {"time": time_block}
    
    return None, None

@app.route('/api/clinic-ai', methods=['POST'])
@login_required
def clinic_ai():
    """AI assistant for doctors to manage appointments"""
    try:
        data = request.json
        message = data.get("message", "")
        
        if not message.strip():
            return jsonify({"response": "Please enter a command."})
        
        # Parse the command
        action, params = parse_appointment_command(message)
        doctor_id = current_user.get_id()
        
        if action == "add":
            # Add new appointment
            appointment = {
                "patient": params["patient"],
                "time": params["time"],
                "reason": params["reason"],
                "location": "Doctor Added",
                "doctor_id": doctor_id,
                "status": "confirmed",
                "confirmationId": f"DR{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}",
                "bookedAt": datetime.now().isoformat(),
                "source": "doctor_ai"
            }
            
            # Check for conflicts
            existing = next((apt for apt in appointments 
                           if apt.get("time") == params["time"] and 
                           apt.get("doctor_id") == doctor_id), None)
            
            if existing:
                return jsonify({
                    "response": f"❌ Cannot add appointment. {params['time']} is already booked for {existing['patient']}."
                })
            
            appointments.append(appointment)
            
            # Try to add to Google Calendar
            try:
                # For doctor-added appointments, create a simple patient info structure
                patient_info = {
                    "firstName": params["patient"].split()[0],
                    "lastName": params["patient"].split()[-1] if len(params["patient"].split()) > 1 else "",
                    "email": "patient@example.com",  # Placeholder
                    "phone": "N/A",
                    "age": "N/A",
                    "gender": "N/A"
                }
                
                google_event_id = create_google_calendar_event(patient_info, params["time"], params["reason"])
                if google_event_id:
                    appointment["google_event_id"] = google_event_id
            except Exception as e:
                print(f"Failed to add to Google Calendar: {e}")
            
            return jsonify({
                "response": f"✅ Appointment added successfully! {params['patient']} scheduled for {params['time']} - {params['reason']}. Also added to Google Calendar."
            })
        
        elif action == "modify":
            # Modify existing appointment
            old_appointment = next((apt for apt in appointments 
                                  if apt.get("time") == params["old_time"] and 
                                  apt.get("doctor_id") == doctor_id), None)
            
            if not old_appointment:
                return jsonify({
                    "response": f"❌ No appointment found at {params['old_time']}."
                })
            
            # Check if new time is available
            existing = next((apt for apt in appointments 
                           if apt.get("time") == params["new_time"] and 
                           apt.get("doctor_id") == doctor_id), None)
            
            if existing:
                return jsonify({
                    "response": f"❌ Cannot reschedule. {params['new_time']} is already booked."
                })
            
            # Update the appointment
            old_appointment["time"] = params["new_time"]
            
            return jsonify({
                "response": f"✅ Appointment rescheduled from {params['old_time']} to {params['new_time']}."
            })
        
        elif action == "delete":
            # Delete appointment
            appointment = next((apt for apt in appointments 
                              if apt.get("time") == params["time"] and 
                              apt.get("doctor_id") == doctor_id), None)
            
            if not appointment:
                return jsonify({
                    "response": f"❌ No appointment found at {params['time']}."
                })
            
            # Remove from list
            appointments.remove(appointment)
            
            return jsonify({
                "response": f"✅ Appointment at {params['time']} has been cancelled."
            })
        
        elif action == "block":
            # Block time (add as blocked appointment)
            block_appointment = {
                "patient": "BLOCKED TIME",
                "time": params["time"],
                "reason": "Time blocked by doctor",
                "location": "Doctor Blocked",
                "doctor_id": doctor_id,
                "status": "blocked",
                "confirmationId": f"BL{datetime.now().strftime('%Y%m%d')}{str(uuid.uuid4())[:6].upper()}",
                "bookedAt": datetime.now().isoformat(),
                "source": "doctor_ai"
            }
            
            appointments.append(block_appointment)
            
            return jsonify({
                "response": f"✅ Time blocked: {params['time']}. No appointments can be scheduled during this time."
            })
        
        else:
            # No specific action recognized, try general AI response
            return jsonify({
                "response": f"I understand you want to: '{message}'. Please use commands like:\n• 'Add appointment for John on Monday 3pm for checkup'\n• 'Reschedule Friday 10am to Friday 2pm'\n• 'Cancel the Saturday appointment'\n• 'Block tomorrow from 2pm to 4pm'"
            })
            
    except Exception as e:
        print(f"Error in clinic AI: {e}")
        return jsonify({
            "response": f"Sorry, I encountered an error: {str(e)}"
        })

# Email system endpoints
@app.route('/api/email-status', methods=['GET'])
@login_required
def email_status():
    """Check if email system is properly configured"""
    try:
        if not EMAIL_SERVICE_AVAILABLE:
            return jsonify({
                "configured": False,
                "error": "Email service not available - missing utils/email_notifications.py"
            })
        
        # Check if SendGrid API key is configured
        sendgrid_configured = bool(email_service.sg_api_key)
        
        # Check if from email is configured
        from_email_configured = bool(email_service.from_email)
        
        return jsonify({
            "configured": sendgrid_configured and from_email_configured,
            "sendgrid_key": sendgrid_configured,
            "from_email": from_email_configured,
            "clinic_name": email_service.clinic_name,
            "clinic_phone": email_service.clinic_phone
        })
        
    except Exception as e:
        return jsonify({
            "configured": False,
            "error": str(e)
        })

@app.route('/api/send-reminder/<appointment_id>', methods=['POST'])
@login_required
def send_appointment_reminder(appointment_id):
    """Send appointment reminder email"""
    if not EMAIL_SERVICE_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "Email service not available"
        })
    
    try:
        # Find the appointment
        appointment = next((apt for apt in appointments 
                          if apt.get("confirmationId") == appointment_id), None)
        
        if not appointment:
            return jsonify({
                "success": False,
                "error": "Appointment not found"
            })
        
        # Get hours before from request (default 24)
        hours_before = request.json.get('hours_before', 24)
        
        # Send reminder email
        patient_info = appointment.get('patientInfo', {})
        if not patient_info.get('email'):
            return jsonify({
                "success": False,
                "error": "No email address found for this patient"
            })
        
        appointment_details = {
            "time": appointment['time'],
            "reason": appointment['reason'],
            "confirmationId": appointment['confirmationId']
        }
        
        reminder_sent = email_service.send_appointment_reminder(
            patient_info, appointment_details, hours_before
        )
        
        return jsonify({
            "success": reminder_sent,
            "message": "Reminder sent successfully" if reminder_sent else "Failed to send reminder"
        })
        
    except Exception as e:
        print(f"❌ Error sending reminder: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to send reminder"
        })

@app.route('/api/test-email', methods=['POST'])
@login_required
def test_email():
    """Test email functionality with sample data"""
    if not EMAIL_SERVICE_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "Email service not available"
        })
    
    try:
        # Sample patient info for testing
        test_patient_info = {
            "firstName": "John",
            "lastName": "Doe",
            "age": 35,
            "gender": "male",
            "email": request.json.get('test_email', 'test@example.com'),
            "phone": "(555) 123-4567",
            "medicalId": "TEST12345",
            "allergies": "Penicillin"
        }
        
        test_appointment_details = {
            "time": "Tomorrow 10:00 AM",
            "reason": "Annual checkup",
            "confirmationId": "TEST123456"
        }
        
        email_type = request.json.get('type', 'confirmation')
        
        if email_type == 'confirmation':
            result = email_service.send_appointment_confirmation(
                test_patient_info, test_appointment_details
            )
        elif email_type == 'reminder':
            result = email_service.send_appointment_reminder(
                test_patient_info, test_appointment_details, 24
            )
        elif email_type == 'doctor_notification':
            doctor_email = request.json.get('doctor_email', 'test.doctor@example.com')
            result = email_service.send_doctor_notification(
                doctor_email, test_patient_info, test_appointment_details
            )
        else:
            return jsonify({
                "success": False,
                "error": "Invalid email type. Use: confirmation, reminder, or doctor_notification"
            })
        
        return jsonify({
            "success": result,
            "message": f"Test {email_type} email {'sent' if result else 'failed'}"
        })
        
    except Exception as e:
        print(f"❌ Error testing email: {e}")
        return jsonify({
            "success": False,
            "error": f"Email test failed: {str(e)}"
        })

@app.route('/api/send-bulk-reminders', methods=['POST'])
@login_required
def send_bulk_reminders():
    """Send reminder emails to all patients with appointments in next 24 hours"""
    if not EMAIL_SERVICE_AVAILABLE:
        return jsonify({
            "success": False,
            "error": "Email service not available"
        })
    
    try:
        current_time = datetime.now()
        tomorrow = current_time + timedelta(hours=24)
        
        # Find appointments in next 24 hours
        upcoming_appointments = []
        for appointment in appointments:
            # Simple time parsing - you might want to improve this
            appointment_time_str = appointment.get('time', '')
            
            # Check if appointment is tomorrow or within 24 hours
            if ('tomorrow' in appointment_time_str.lower() or 
                'friday' in appointment_time_str.lower() or
                'saturday' in appointment_time_str.lower() or
                'sunday' in appointment_time_str.lower()):
                
                patient_info = appointment.get('patientInfo')
                if patient_info and patient_info.get('email'):
                    upcoming_appointments.append(appointment)
        
        sent_count = 0
        failed_count = 0
        
        for appointment in upcoming_appointments:
            patient_info = appointment['patientInfo']
            appointment_details = {
                "time": appointment['time'],
                "reason": appointment['reason'],
                "confirmationId": appointment['confirmationId']
            }
            
            # Send reminder email
            success = email_service.send_appointment_reminder(
                patient_info, appointment_details, hours_before=24
            )
            
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        return jsonify({
            "success": True,
            "sent_count": sent_count,
            "failed_count": failed_count,
            "total_eligible": len(upcoming_appointments),
            "message": f"Sent {sent_count} reminder emails, {failed_count} failed"
        })
        
    except Exception as e:
        print(f"❌ Error sending bulk reminders: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/cancel-appointment', methods=['POST'])
def cancel_appointment():
    """Cancel appointment and send notification email"""
    try:
        data = request.json
        confirmation_id = data.get('confirmationId')
        
        if not confirmation_id:
            return jsonify({
                "success": False,
                "error": "Confirmation ID required"
            })
        
        # Find and remove the appointment
        appointment = None
        for i, apt in enumerate(appointments):
            if apt.get("confirmationId") == confirmation_id:
                appointment = appointments.pop(i)
                break
        
        if not appointment:
            return jsonify({
                "success": False,
                "error": "Appointment not found"
            })
        
        # Send cancellation email to patient
        patient_info = appointment.get('patientInfo', {})
        cancellation_sent = False
        if EMAIL_SERVICE_AVAILABLE and patient_info.get('email'):
            cancellation_sent = send_cancellation_email(patient_info, appointment)
        
        # Delete from Google Calendar if event exists
        if appointment.get('google_event_id'):
            try:
                delete_google_calendar_event(appointment['google_event_id'])
            except Exception as e:
                print(f"⚠️ Failed to delete Google Calendar event: {e}")
        
        return jsonify({
            "success": True,
            "message": "Appointment cancelled successfully",
            "cancellationEmailSent": cancellation_sent
        })
        
    except Exception as e:
        print(f"❌ Error cancelling appointment: {e}")
        return jsonify({
            "success": False,
            "error": "Failed to cancel appointment"
        })

def send_cancellation_email(patient_info, appointment):
    """Send appointment cancellation email"""
    if not EMAIL_SERVICE_AVAILABLE:
        return False
    
    try:
        subject = f"❌ Appointment Cancelled - {appointment['time']}"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; }}
                .header {{ background: #dc3545; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 30px; }}
                .cancellation-box {{ background: #f8d7da; border: 1px solid #dc3545; padding: 20px; border-radius: 8px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>❌ Appointment Cancelled</h1>
                    <p>{email_service.clinic_name}</p>
                </div>
                
                <div class="content">
                    <p>Dear <strong>{patient_info['firstName']} {patient_info['lastName']}</strong>,</p>
                    
                    <div class="cancellation-box">
                        <h3>Your appointment has been cancelled:</h3>
                        <p><strong>Date & Time:</strong> {appointment['time']}</p>
                        <p><strong>Reason:</strong> {appointment['reason']}</p>
                        <p><strong>Confirmation ID:</strong> {appointment['confirmationId']}</p>
                    </div>
                    
                    <p>If you need to reschedule, please contact us at {email_service.clinic_phone} or visit our website.</p>
                    
                    <p>Best regards,<br><strong>The {email_service.clinic_name} Team</strong></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Email, To, Content
        
        message = Mail(
            from_email=Email(email_service.from_email, email_service.clinic_name),
            to_emails=To(patient_info['email']),
            subject=subject,
            html_content=Content("text/html", html_content)
        )
        
        sg = SendGridAPIClient(api_key=email_service.sg_api_key)
        response = sg.send(message)
        
        print(f"✅ Cancellation email sent to {patient_info['email']} | Status: {response.status_code}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending cancellation email: {e}")
        return False

def delete_google_calendar_event(event_id):
    """Delete event from Google Calendar"""
    service = get_google_calendar_service()
    if not service:
        return False
    
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        print(f"✅ Deleted Google Calendar event: {event_id}")
        return True
    except Exception as e:
        print(f"❌ Error deleting Google Calendar event: {e}")
        return False

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

if __name__ == '__main__':
    app.run(debug=True)