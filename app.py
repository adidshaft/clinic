from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from openai import OpenAI
import os
import re
from datetime import datetime, timedelta
import json
import warnings

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

# In-memory storage for appointments (now synced with Google Calendar)
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

def sync_from_google_calendar():
    """Fetch appointments from Google Calendar and sync to local storage"""
    service = get_google_calendar_service()
    if not service:
        print("No Google Calendar service available")
        return False
    
    try:
        # Get events from the next 30 days
        now = datetime.utcnow().isoformat() + 'Z'
        future = (datetime.utcnow() + timedelta(days=30)).isoformat() + 'Z'
        
        print(f"Fetching events from {now} to {future}")
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=future,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        print(f"Found {len(events)} events in Google Calendar")
        
        # Clear existing appointments for this doctor
        global appointments
        doctor_id = current_user.get_id()
        old_count = len([apt for apt in appointments if apt.get("doctor_id") == doctor_id])
        appointments = [apt for apt in appointments if apt.get("doctor_id") != doctor_id]
        
        # Add Google Calendar events to appointments
        synced_count = 0
        for event in events:
            try:
                if 'summary' in event and 'start' in event:
                    start = event['start'].get('dateTime', event['start'].get('date'))
                    
                    # Parse the datetime
                    if 'T' in start:
                        event_time = datetime.fromisoformat(start.replace('Z', '+00:00'))
                        formatted_time = event_time.strftime('%A %I:%M %p')
                    else:
                        # All day event
                        formatted_time = "All Day"
                    
                    # Extract patient name and reason from event summary
                    summary = event.get('summary', 'Appointment')
                    description = event.get('description', '')
                    
                    # Try to parse "Patient: Name - Reason: Description" format
                    if ' - ' in summary:
                        parts = summary.split(' - ')
                        patient_name = parts[0].replace('Patient: ', '').strip()
                        reason = parts[1].replace('Reason: ', '').strip() if len(parts) > 1 else 'Appointment'
                    else:
                        patient_name = summary
                        reason = description or 'Appointment'
                    
                    appointments.append({
                        "patient": patient_name,
                        "time": formatted_time,
                        "reason": reason,
                        "location": "Google Calendar",
                        "doctor_id": doctor_id,
                        "status": "confirmed",
                        "google_event_id": event.get('id')
                    })
                    synced_count += 1
            except Exception as event_error:
                print(f"Error processing event {event.get('id', 'unknown')}: {event_error}")
                continue
        
        print(f"Synced {synced_count} appointments from Google Calendar")
        return True
        
    except Exception as e:
        print(f"Error syncing from Google Calendar: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_google_calendar_event(patient, time, reason):
    """Create an event in Google Calendar"""
    service = get_google_calendar_service()
    if not service:
        return None
    
    try:
        # Parse the time - this is a simplified version
        # You might want to improve this parsing based on your time format
        event_start = datetime.now() + timedelta(days=1)  # Default to tomorrow
        
        # Try to parse common time formats
        if 'monday' in time.lower():
            # Find next Monday
            days_ahead = 0 - datetime.now().weekday()
            if days_ahead <= 0:
                days_ahead += 7
            event_start = datetime.now() + timedelta(days=days_ahead)
        elif 'friday' in time.lower():
            days_ahead = 4 - datetime.now().weekday()
            if days_ahead <= 0:
                days_ahead += 7
            event_start = datetime.now() + timedelta(days=days_ahead)
        # Add more day parsing as needed
        
        # Set time (simplified - defaults to 10 AM)
        if '3pm' in time.lower():
            event_start = event_start.replace(hour=15, minute=0)
        elif '2pm' in time.lower():
            event_start = event_start.replace(hour=14, minute=0)
        elif '10am' in time.lower():
            event_start = event_start.replace(hour=10, minute=0)
        else:
            event_start = event_start.replace(hour=10, minute=0)  # Default 10 AM
        
        event_end = event_start + timedelta(hours=1)  # 1 hour appointment
        
        event = {
            'summary': f'Patient: {patient} - Reason: {reason}',
            'description': f'Appointment for {patient}\nReason: {reason}',
            'start': {
                'dateTime': event_start.isoformat(),
                'timeZone': 'America/New_York',  # Adjust timezone as needed
            },
            'end': {
                'dateTime': event_end.isoformat(),
                'timeZone': 'America/New_York',
            },
        }
        
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        return created_event.get('id')
    
    except Exception as e:
        print(f"Error creating Google Calendar event: {e}")
        return None

def delete_google_calendar_event(event_id):
    """Delete an event from Google Calendar"""
    service = get_google_calendar_service()
    if not service or not event_id:
        return False
    
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting Google Calendar event: {e}")
        return False

# Google Calendar OAuth routes
@app.route('/google-calendar-auth')
@login_required
def google_calendar_auth():
    """Start Google Calendar OAuth flow"""
    try:
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=OAUTH_REDIRECT_URI
        )
        
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to ensure we get refresh token
        )
        
        session['state'] = state
        return redirect(authorization_url)
    except Exception as e:
        print(f"Error starting OAuth flow: {e}")
        return redirect(url_for('clinic_dashboard', error='oauth_start_failed'))

@app.route('/google-calendar-callback')
@login_required
def google_calendar_callback():
    """Handle Google Calendar OAuth callback"""
    try:
        state = session.get('state')
        
        if not state:
            print("No state found in session")
            return redirect(url_for('clinic_dashboard', error='no_state'))
        
        # Check for error parameter in callback
        if request.args.get('error'):
            error = request.args.get('error')
            print(f"OAuth error: {error}")
            return redirect(url_for('clinic_dashboard', error=f'oauth_error_{error}'))
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=OAUTH_REDIRECT_URI
        )
        
        # Use the full URL including query parameters
        authorization_response = request.url
        
        # Handle HTTPS vs HTTP in callback URL
        if authorization_response.startswith('http://') and 'onrender.com' in authorization_response:
            authorization_response = authorization_response.replace('http://', 'https://')
        
        print(f"Authorization response URL: {authorization_response}")
        
        # Fetch the token with better error handling
        try:
            flow.fetch_token(authorization_response=authorization_response)
        except Exception as token_error:
            print(f"Token fetch error: {token_error}")
            # Try without the warning-causing validation
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*Scope has changed.*")
                flow.fetch_token(authorization_response=authorization_response)
        
        # Save credentials
        doctor_id = current_user.get_id()
        token_file = f'token_{doctor_id}.json'
        
        # Ensure we have credentials
        if not flow.credentials:
            print("No credentials received from OAuth flow")
            return redirect(url_for('clinic_dashboard', error='no_credentials'))
        
        # Save to file
        try:
            with open(token_file, 'w') as token:
                token.write(flow.credentials.to_json())
            print(f"Credentials saved to {token_file}")
        except Exception as save_error:
            print(f"Error saving credentials: {save_error}")
            return redirect(url_for('clinic_dashboard', error='save_failed'))
        
        # Try to sync calendar
        try:
            sync_success = sync_from_google_calendar()
            print(f"Calendar sync result: {sync_success}")
        except Exception as sync_error:
            print(f"Calendar sync error: {sync_error}")
            # Don't fail the whole process if sync fails
        
        # Clear session state
        session.pop('state', None)
        
        return redirect(url_for('clinic_dashboard', connected='true'))
        
    except Exception as e:
        print(f"Callback error: {e}")
        import traceback
        traceback.print_exc()
        return redirect(url_for('clinic_dashboard', error='callback_failed'))

# Helper function to parse appointment commands
def parse_appointment_command(command):
    """Parse AI commands for appointment management"""
    command = command.lower().strip()
    
    # Add appointment patterns
    add_patterns = [
        r'add appointment for (\w+(?:\s+\w+)*) on (\w+(?:\s+\d+(?:am|pm))*) for (.+)',
        r'create appointment for (\w+(?:\s+\w+)*) at (\w+(?:\s+\d+(?:am|pm))*) for (.+)',
        r'schedule (\w+(?:\s+\w+)*) on (\w+(?:\s+\d+(?:am|pm))*) for (.+)'
    ]
    
    # Modify/Reschedule patterns
    modify_patterns = [
        r'reschedule (\w+(?:\s+\d+(?:am|pm))*) appointment to (\w+(?:\s+\d+(?:am|pm))*)',
        r'move (\w+(?:\s+\d+(?:am|pm))*) appointment to (\w+(?:\s+\d+(?:am|pm))*)',
        r'change (\w+(?:\s+\d+(?:am|pm))*) to (\w+(?:\s+\d+(?:am|pm))*)'
    ]
    
    # Delete/Cancel patterns
    delete_patterns = [
        r'cancel (?:the )?(\w+(?:\s+\d+(?:am|pm))*) appointment',
        r'delete (?:the )?(\w+(?:\s+\d+(?:am|pm))*) appointment',
        r'remove (?:the )?(\w+(?:\s+\d+(?:am|pm))*) appointment'
    ]
    
    # Check add patterns
    for pattern in add_patterns:
        match = re.search(pattern, command)
        if match:
            return {
                'action': 'add',
                'patient': match.group(1).title(),
                'time': match.group(2).title(),
                'reason': match.group(3)
            }
    
    # Check modify patterns
    for pattern in modify_patterns:
        match = re.search(pattern, command)
        if match:
            return {
                'action': 'modify',
                'old_time': match.group(1).title(),
                'new_time': match.group(2).title()
            }
    
    # Check delete patterns
    for pattern in delete_patterns:
        match = re.search(pattern, command)
        if match:
            return {
                'action': 'delete',
                'time': match.group(1).title()
            }
    
    return None

@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.json
    user_input = data.get("message")
    location = data.get("location", "unknown")

    # Check if this is a booking confirmation
    if user_input.startswith("CONFIRM_BOOKING:"):
        original_message = user_input.replace("CONFIRM_BOOKING:", "").strip()
        
        # Enhanced parsing for confirmed bookings
        name = "New Patient"
        reason = original_message
        time = "Tomorrow 10 AM"  # Default placeholder
        
        # Try to extract time from the message
        if "friday" in original_message.lower():
            if "10" in original_message or "10am" in original_message.lower():
                time = "Friday 10:00 AM"
            else:
                time = "Friday Morning"
        elif "saturday" in original_message.lower():
            if "11" in original_message or "11am" in original_message.lower():
                time = "Saturday 11:00 AM"
            else:
                time = "Saturday Morning"
        elif "sunday" in original_message.lower():
            if "9" in original_message or "9am" in original_message.lower():
                time = "Sunday 9:00 AM"
            else:
                time = "Sunday Morning"
        elif "monday" in original_message.lower():
            if "2" in original_message or "2pm" in original_message.lower():
                time = "Monday 2:00 PM"
            else:
                time = "Monday Afternoon"
        elif "tomorrow" in original_message.lower():
            time = "Tomorrow 10:00 AM"
        elif "today" in original_message.lower():
            time = "Today (if available)"

        # Check if this time slot is already taken (including Google Calendar)
        existing_appointment = next((apt for apt in appointments if apt.get("time") == time and apt.get("doctor_id") == "drlee"), None)
        
        if existing_appointment:
            response_text = f"❌ Sorry, the {time} slot is already booked. Please choose a different time."
        else:
            # Add to appointments
            new_appointment = {
                "patient": name,
                "time": time,
                "reason": reason,
                "location": location,
                "doctor_id": "drlee",  # Default doctor
                "status": "confirmed"
            }
            appointments.append(new_appointment)
            
            # Try to create Google Calendar event
            google_event_id = create_google_calendar_event(name, time, reason)
            if google_event_id:
                new_appointment["google_event_id"] = google_event_id
            
            response_text = f"✅ Your appointment has been successfully booked for {time}. Dr. Lee will see you for: {reason}. Please arrive 15 minutes early."
        
    else:
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
            # Check if this time slot is already taken (including Google Calendar)
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

@app.route('/clinic')
@login_required
def clinic_dashboard():
    # Sync with Google Calendar when loading dashboard
    sync_from_google_calendar()
    
    doc_id = current_user.get_id()
    filtered = [a for a in appointments if a.get("doctor_id") == doc_id]
    
    # Check if Google Calendar is connected
    token_file = f'token_{doc_id}.json'
    google_connected = os.path.exists(token_file)
    
    return render_template("clinic.html", appointments=filtered, google_connected=google_connected)

@app.route('/api/clinic-ai', methods=['POST'])
def clinic_ai():
    data = request.json
    msg = data.get("message", "").lower()

    # Parse the command using our new parser
    parsed_command = parse_appointment_command(msg)
    
    if parsed_command:
        action = parsed_command['action']
        
        if action == 'add':
            # Add new appointment
            patient = parsed_command['patient']
            time = parsed_command['time']
            reason = parsed_command['reason']
            
            # Check if time slot is available (including Google Calendar)
            existing = next((apt for apt in appointments if apt.get("time") == time and apt.get("doctor_id") == current_user.get_id()), None)
            if existing:
                return jsonify({"response": f"❌ Cannot add appointment. {time} slot is already booked by {existing['patient']}."})
            
            # Add appointment
            new_appointment = {
                "patient": patient,
                "time": time,
                "reason": reason,
                "location": "Doctor added",
                "doctor_id": current_user.get_id(),
                "status": "confirmed"
            }
            appointments.append(new_appointment)
            
            # Create Google Calendar event
            google_event_id = create_google_calendar_event(patient, time, reason)
            if google_event_id:
                new_appointment["google_event_id"] = google_event_id
            
            return jsonify({"response": f"✅ Appointment added successfully! {patient} scheduled for {time} - {reason}. Also added to Google Calendar."})
        
        elif action == 'modify':
            # Modify existing appointment
            old_time = parsed_command['old_time']
            new_time = parsed_command['new_time']
            
            # Find existing appointment
            existing = next((apt for apt in appointments if apt.get("time") == old_time and apt.get("doctor_id") == current_user.get_id()), None)
            if not existing:
                return jsonify({"response": f"❌ No appointment found at {old_time}."})
            
            # Check if new time slot is available
            conflict = next((apt for apt in appointments if apt.get("time") == new_time and apt.get("doctor_id") == current_user.get_id()), None)
            if conflict:
                return jsonify({"response": f"❌ Cannot reschedule. {new_time} slot is already booked by {conflict['patient']}."})
            
            # Delete old Google Calendar event if exists
            if existing.get('google_event_id'):
                delete_google_calendar_event(existing['google_event_id'])
            
            # Update appointment
            existing['time'] = new_time
            
            # Create new Google Calendar event
            google_event_id = create_google_calendar_event(existing['patient'], new_time, existing['reason'])
            if google_event_id:
                existing["google_event_id"] = google_event_id
            
            return jsonify({"response": f"✅ Appointment rescheduled! {existing['patient']} moved from {old_time} to {new_time}. Google Calendar updated."})
        
        elif action == 'delete':
            # Delete appointment
            time = parsed_command['time']
            
            # Find and remove appointment
            existing = next((apt for apt in appointments if apt.get("time") == time and apt.get("doctor_id") == current_user.get_id()), None)
            if not existing:
                return jsonify({"response": f"❌ No appointment found at {time}."})
            
            # Delete Google Calendar event if exists
            if existing.get('google_event_id'):
                delete_google_calendar_event(existing['google_event_id'])
            
            appointments.remove(existing)
            
            return jsonify({"response": f"✅ Appointment deleted! {existing['patient']}'s {time} appointment has been cancelled. Removed from Google Calendar."})
    
    # Handle other commands (block time, etc.)
    elif "block" in msg and ("tomorrow" in msg or "today" in msg or any(day in msg for day in ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])):
        return jsonify({"response": "⏰ Time blocked successfully. No appointments will be scheduled during this period."})
    elif "reschedule" in msg:
        return jsonify({"response": "📅 Please specify the exact time to reschedule. Example: 'Reschedule Friday 10am appointment to Friday 2pm'"})
    elif "cancel" in msg:
        return jsonify({"response": "❌ Please specify the exact time to cancel. Example: 'Cancel the Saturday 11am appointment'"})
    
    # Fallback response with examples
    return jsonify({"response": f"🤖 I can help you manage appointments! Try commands like:\n• 'Add appointment for John Doe on Monday 3pm for checkup'\n• 'Reschedule Friday 10am appointment to Friday 2pm'\n• 'Cancel the Saturday 11am appointment'\n\nYour command: '{msg}' - Please be more specific."})

@app.route('/api/google-calendar-connect', methods=['POST'])
def google_calendar_connect():
    """Handle Google Calendar connection request"""
    try:
        # Check if already connected
        doctor_id = current_user.get_id()
        token_file = f'token_{doctor_id}.json'
        
        if os.path.exists(token_file):
            # Try to use existing credentials
            service = get_google_calendar_service()
            if service:
                # Sync calendar
                sync_success = sync_from_google_calendar()
                if sync_success:
                    return jsonify({
                        "success": True,
                        "message": "Already connected to Google Calendar! Synced successfully.",
                        "redirect": False
                    })
        
        # Need to authenticate
        return jsonify({
            "success": True,
            "message": "Redirecting to Google for authentication...",
            "redirect": True,
            "redirect_url": url_for('google_calendar_auth')
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route('/api/google-calendar-sync', methods=['POST'])
@login_required
def google_calendar_sync():
    """Manually sync with Google Calendar"""
    try:
        success = sync_from_google_calendar()
        if success:
            doc_id = current_user.get_id()
            synced_count = len([a for a in appointments if a.get("doctor_id") == doc_id])
            return jsonify({
                "success": True,
                "message": f"Synced {synced_count} appointments from Google Calendar."
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to sync with Google Calendar. Please reconnect."
            })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

if __name__ == '__main__':
    app.run(debug=True)