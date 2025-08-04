from flask import Flask, render_template, request, jsonify
from openai import OpenAI
import os

# Load environment variable (optional: only needed locally)
from dotenv import load_dotenv
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

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

    prompt = f"User said: '{user_input}'\nTheir location is: {location}.\nRecommend a nearby doctor and time."

    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful AI that books appointments at local clinics."},
            {"role": "user", "content": prompt}
        ]
    )

    return jsonify({"response": response.choices[0].message.content})

@app.route('/clinic')
def clinic_dashboard():
    # Temporary static data
    appointments = [
        {"patient": "John Doe", "time": "2025-08-05 10:00 AM", "reason": "fever"},
        {"patient": "Jane Smith", "time": "2025-08-05 11:30 AM", "reason": "back pain"},
    ]
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
