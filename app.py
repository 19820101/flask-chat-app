from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'
socketio = SocketIO(app, cors_allowed_origins="*")

messages = []

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    for msg in messages:
        emit('message', msg)

@socketio.on('send_message')
def handle_message(data):
    message = {
        'username': data['username'],
        'text': data['text'],
        'timestamp': datetime.now().strftime('%H:%M')
    }
    messages.append(message)
    if len(messages) > 100:
        messages.pop(0)
    emit('message', message, broadcast=True)

@socketio.on('typing')
def handle_typing(data):
    emit('user_typing', {'username': data['username']}, broadcast=True, include_self=False)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
