from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os

# Load environment variable (optional: only needed locally)
from dotenv import load_dotenv
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

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
        "location": location
    })

    response_text = f"Your appointment for '{reason}' is tentatively booked for {time}. We'll notify you once confirmed."

    return jsonify({"response": response_text})


@app.route('/clinic')
def clinic_dashboard():
    return render_template("clinic.html", appointments=appointments)


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
