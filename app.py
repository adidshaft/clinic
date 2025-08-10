from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from openai import OpenAI
import os

# Load environment variable (optional: only needed locally)
from dotenv import load_dotenv
load_dotenv()

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
        elif "tomorrow" in original_message.lower():
            time = "Tomorrow 10:00 AM"
        elif "today" in original_message.lower():
            time = "Today (if available)"

        # Check if this time slot is already taken
        existing_appointment = next((apt for apt in appointments if apt.get("time") == time and apt.get("doctor_id") == "drlee"), None)
        
        if existing_appointment:
            response_text = f"❌ Sorry, the {time} slot is already booked. Please choose a different time."
        else:
            # Add to appointments
            appointments.append({
                "patient": name,
                "time": time,
                "reason": reason,
                "location": location,
                "doctor_id": "drlee",  # Default doctor
                "status": "confirmed"
            })
            
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


@app.route('/clinic')
@login_required
def clinic_dashboard():
    doc_id = current_user.get_id()
    filtered = [a for a in appointments if a.get("doctor_id") == doc_id]
    return render_template("clinic.html", appointments=filtered)



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

    # Fallback response (removed OpenAI dependency for simplicity)
    return jsonify({"response": f"I'll help you with: '{msg}'. What specific action would you like me to take?"})


if __name__ == '__main__':
    app.run(debug=True)