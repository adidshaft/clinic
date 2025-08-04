from flask import Flask, render_template, request, jsonify
import os
import openai
from dotenv import load_dotenv
load_dotenv()


app = Flask(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/ask', methods=['POST'])
def ask():
    user_input = request.json.get("message")
    print("USER INPUT:", user_input)

    response = openai.ChatCompletion.create(
        model="gpt-4",  # or "gpt-3.5-turbo"
        messages=[
            {"role": "system", "content": "You are a helpful medical booking assistant."},
            {"role": "user", "content": user_input}
        ]
    )
    print("GPT RESPONSE:", response)

    return jsonify({"response": response.choices[0].message.content})


if __name__ == '__main__':
    app.run(debug=True)
