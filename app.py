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



if __name__ == '__main__':
    app.run(debug=True)
