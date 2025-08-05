from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from utils.email_invite import send_email_with_ics
from openai import OpenAI
import os
import datetime
import json
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


@app.route('/authorize')
@login_required
def authorize():
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES
    )
    flow.redirect_uri = url_for('oauth2callback', _external=True)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
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

    # Basic parsing: simulate extracting name, time, reason
    name = "New Patient"
    reason = user_input
    time = "Tomorrow 10 AM"  # Default placeholder

    # Append to shared appointment list
    appointments.append({
        "patient": name,
        "time": time,
        "reason": reason,
        "location": location,
        "doctor_id": current_user.get_id() if current_user.is_authenticated else "drlee"
    })

    # dummy email for now (can enhance with user input later)
    patient_email = "test@example.com"
    doctor_email = "doctor@example.com"

    # Generate time slots (for ICS)
    start_time = dateparser.parse(time)
    if not start_time:
        return jsonify({"error": "Could not understand time format"}), 400

    end_time = start_time + datetime.timedelta(minutes=30)

    send_email_with_ics(
        to_email=patient_email,
        subject="Your Clinic Appointment",
        body=f"You have an appointment with {doctor} at {time}",
        summary="Clinic Appointment",
        start_time=start_time,
        end_time=end_time,
        location=location
    )


    response_text = f"Your appointment for '{reason}' is tentatively booked for {time}. We'll notify you once confirmed."

    return jsonify({"response": response_text})


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
