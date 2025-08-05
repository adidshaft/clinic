from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from utils.email_invite import send_email_with_ics
from openai import OpenAI
import os
import datetime
import json
import re
import dateparser
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

# Load environment variable (optional: only needed locally)
from dotenv import load_dotenv
load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
CLIENT_SECRETS_FILE = 'client_secret.json'


# Initialize Flask app
app = Flask(__name__)

app.secret_key = "your-secret-key"

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Temporary doctor store
doctors = [
    {
        "id": "drlee",
        "name": "Dr. Lee",
        "specialty": "Dermatology",
        "location": "Singapore East",
        "email": "drlee@example.com",
        "password": "test123"  # 👈 Add this
    },
    {
        "id": "drjohn",
        "name": "Dr. John",
        "specialty": "Gynecology",
        "location": "Singapore Central",
        "email": "drjohn@example.com",
        "password": "secret456"  # 👈 And this
    }
]



# Fake doctor directory
DOCTORS = [
    {"id": "drlee", "name": "Dr. Lee", "specialty": "headache", "location": "central"},
    {"id": "drchua", "name": "Dr. Chua", "specialty": "stomach", "location": "east"},
    {"id": "drgoh", "name": "Dr. Goh", "specialty": "flu", "location": "north"},
]

def find_doctor(location, specialty):
    location = location.lower().strip()
    specialty = specialty.lower().strip()

    for doc in doctors:
        doc_location = doc.get("location", "").lower()
        doc_specialty = doc.get("specialty", "").lower()

        if location in doc_location and specialty in doc_specialty:
            return doc

    # Fallback: try matching specialty only
    for doc in doctors:
        if specialty in doc.get("specialty", "").lower():
            return doc

    # Fallback: return a random doctor or None
    if doctors:
        return doctors[0]
    
    print(f"Looking for doctor with specialty: {specialty}, location: {location}")

    return None



# User Class
class Doctor(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return Doctor(user_id)


@app.route('/authorize')
@login_required
def authorize():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    # 🔥 Force refresh_token issuance
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent'
    )
    session['state'] = state

    return redirect(authorization_url)


@app.route('/oauth2callback')
@login_required
def oauth2callback():
    state = session['state']

    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=state
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials
    session['credentials'] = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }

    print("Successfully connected to Google Calendar")
    print("Token:", credentials.token)
    print("Refresh:", credentials.refresh_token)

    return redirect(url_for('clinic_dashboard'))




@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        matched_doctor = next((doc for doc in doctors if doc['id'] == username and doc['password'] == password), None)

        if matched_doctor:
            user = User(username)
            login_user(user)
            return redirect(url_for('clinic_dashboard'))
        else:
            return "Invalid credentials", 401

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.errorhandler(500)
def internal_error(e):
    return f"Something broke: {str(e)}", 500


# In-memory storage for appointments
appointments = []


# Initialize OpenAI client (for SDK v1.x)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/ask', methods=['POST'])
def ask():
    data = request.json
    user_input = data.get("message")
    location = data.get("location", "unknown")

    # ========== Basic time parsing ==========
    parsed_time = dateparser.parse(user_input)
    time = parsed_time.strftime("%Y-%m-%d %H:%M") if parsed_time else "Tomorrow 10 AM"

    # ========== Extract doctor type ==========
    user_lower = user_input.lower()
    if "gynecologist" in user_lower or "gynecology" in user_lower:
        doctor_type = "Gynecology"
    elif "pediatrician" in user_lower:
        doctor_type = "Pediatrics"
    elif "dentist" in user_lower:
        doctor_type = "Dentistry"
    elif "skin" in user_lower or "dermatologist" in user_lower:
        doctor_type = "Dermatology"
    elif "headache" in user_lower or "fever" in user_lower or "cold" in user_lower:
        doctor_type = "General Physician"
    else:
        doctor_type = "General Physician"

    # ========== Extract reason ==========
    reason_match = re.search(r"(?:for|about|with|have|need)\s(.+)", user_lower)
    reason = reason_match.group(1).capitalize() if reason_match else doctor_type + " consultation"

    # ========== Match a doctor ==========
    matched_doctor = find_doctor(location, doctor_type)

    if not matched_doctor:
        return jsonify({
            "response": "We couldn’t match a doctor right now based on your location and issue. Our team will get back to you shortly."
        }), 200

    # ========== Save to pending session ==========
    session['pending_appointment'] = {
        "patient": "New Patient",
        "time": time,
        "reason": reason,
        "location": location,
        "doctor": matched_doctor['name'],
        "doctor_id": matched_doctor["id"],
        "doctor_email": matched_doctor.get("email", "doctor@example.com"),
        "patient_email": "test@example.com"  # Replace with actual
    }

    # ========== Ask for confirmation ==========
    response_text = (
        f"Do you want to confirm an appointment with Dr. {matched_doctor['name']} "
        f"for '{reason}' at {time}? Reply with 'yes' to confirm."
    )

    return jsonify({"response": response_text})

@app.route('/api/confirm', methods=['POST'])
def confirm():
    from flask import session

    data = session.get("pending_appointment")

    if not data:
        return jsonify({"response": "No pending appointment found. Please start over."}), 400

    try:
        start_time = dateparser.parse(data['time'])
        if not start_time:
            return jsonify({"error": "Could not parse time."}), 400

        end_time = start_time + datetime.timedelta(minutes=30)

        # Send ICS to patient
        send_email_with_ics(
            to_email=data["patient_email"],
            subject="Your Clinic Appointment",
            body=f"Your appointment with Dr. {data['doctor']} is confirmed for {data['time']}",
            summary="Clinic Appointment",
            start_time=start_time,
            end_time=end_time,
            location=data["location"]
        )

        # Send ICS to doctor
        send_email_with_ics(
            to_email=data["doctor_email"],
            subject="New Patient Appointment",
            body=f"You have a new appointment with a patient at {data['time']}",
            summary="New Appointment",
            start_time=start_time,
            end_time=end_time,
            location=data["location"]
        )

        # Save appointment
        appointments.append({
            "patient": data["patient"],
            "time": data["time"],
            "reason": data["reason"],
            "location": data["location"],
            "doctor_id": data["doctor_id"]
        })

        # Clear session
        session.pop("pending_appointment", None)

        return jsonify({
            "response": f"Your appointment with Dr. {data['doctor']} for '{data['reason']}' is confirmed at {data['time']}."
        })

    except Exception as e:
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500



@app.route('/clinic')
@login_required
def clinic_dashboard():
    doc_id = current_user.get_id()
    filtered = [a for a in appointments if a.get("doctor_id") == doc_id]

    free_busy = []
    if 'credentials' in session:
        print("⛳️ Found credentials in session")

        creds = google.oauth2.credentials.Credentials(**session['credentials'])

        service = googleapiclient.discovery.build('calendar', 'v3', credentials=creds)

        now = datetime.datetime.utcnow().isoformat() + 'Z'
        later = (datetime.datetime.utcnow() + datetime.timedelta(days=1)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=later,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        print("🗓 Found events:", events)

        for event in events:
            free_busy.append({
                'summary': event['summary'],
                'start': event['start'].get('dateTime', event['start'].get('date')),
                'end': event['end'].get('dateTime', event['end'].get('date'))
            })
    else:
        print("⚠️ No credentials in session")

    return render_template("clinic.html", appointments=filtered, free_busy=free_busy)




@app.route('/api/clinic-ai', methods=['POST'])
def clinic_ai():
    data = request.json
    msg = data.get("message", "").lower()

    # Simple simulation without OpenAI
    if "block" in msg and "tomorrow" in msg:
        return jsonify({"response": "Tomorrow has been blocked from 2pm to 4pm."})
    elif "reschedule" in msg:
        return jsonify({"response": "Appointment rescheduled as requested."})
    elif "cancel" in msg:
        return jsonify({"response": "Appointment cancelled."})

    # Fallback OpenAI (very minimal usage)
    prompt = f"The doctor said: '{msg}'. What action should we take on the schedule?"
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You assist doctors in managing appointments at a clinic."},
                {"role": "user", "content": prompt}
            ]
        )
        reply = response.choices[0].message.content
    except Exception as e:
        reply = f"(AI failed. Error: {e})"

    return jsonify({"response": reply})


if __name__ == '__main__':
    app.run(debug=True)
