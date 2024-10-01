from flask import Flask, render_template, request, session, redirect, url_for
from flask_socketio import join_room, leave_room, send, SocketIO, emit
from flask_sqlalchemy import SQLAlchemy
import random
from string import ascii_uppercase
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
socketio = SocketIO(app)
db = SQLAlchemy(app)

class Room(db.Model):
    id = db.Column(db.String(4), primary_key=True)
    members = db.Column(db.Integer, default=0)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room = db.Column(db.String(4), db.ForeignKey('room.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'message': self.message,
            'timestamp': self.timestamp.isoformat()
        }

def generate_unique_code(length):
    while True:
        code = "".join(random.choices(ascii_uppercase, k=length))
        room = Room.query.get(code)
        if not room:
            return code

@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        name = request.form.get("name")
        code = request.form.get("code")
        join = request.form.get("join", False)
        create = request.form.get("create", False)

        if not name:
            return render_template("home.html", error="Please enter a name.", code=code, name=name)

        if join != False and not code:
            return render_template("home.html", error="Please enter a room code.", code=code, name=name)
        
        room = code
        if create != False:
            room = generate_unique_code(4)
            new_room = Room(id=room)
            db.session.add(new_room)
            db.session.commit()
        elif not Room.query.get(code):
            return render_template("home.html", error="Room does not exist.", code=code, name=name)
        
        session["room"] = room
        session["name"] = name
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    if room is None or session.get("name") is None or not Room.query.get(room):
        return redirect(url_for("home"))

    messages = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
    return render_template("room.html", code=room, messages=[msg.to_dict() for msg in messages])

@socketio.on("message")
def message(data):
    room = session.get("room")
    if not room:
        return

    content = {
        "name": session.get("name"),
        "message": data["message"]
    }
    send(content, to=room)
    new_message = Message(room=room, name=content["name"], message=content["message"])
    db.session.add(new_message)
    db.session.commit()

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    name = session.get("name")
    if not room or not name:
        return
    if not Room.query.get(room):
        leave_room(room)
        return
    
    join_room(room)
    send({"name": name, "message": "has entered the room"}, to=room)
    room_model = Room.query.get(room)
    room_model.members += 1
    db.session.commit()

@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = session.get("name")
    leave_room(room)

    room_model = Room.query.get(room)
    if room_model:
        room_model.members -= 1
        if room_model.members <= 0:
            db.session.delete(room_model)
        db.session.commit()

    send({"name": name, "message": "has left the room"}, to=room)

@socketio.on("update_message")
def update_message(data):
    room = session.get("room")
    if not room:
        return

    msg_id = data.get('msg_id')
    new_text = data.get('text')
    
    message = Message.query.filter_by(id=msg_id, room=room).first()
    if message:
        message.message = new_text
        db.session.commit()
        emit("message_updated", {
            "msg_id": msg_id,
            "new_text": new_text
        }, room=room)

@socketio.on("delete_message")
def delete_message(data):
    room = session.get("room")
    if not room:
        return

    msg_id = data.get('msg_id')
    
    message = Message.query.filter_by(id=msg_id, room=room).first()
    if message:
        db.session.delete(message)
        db.session.commit()
        emit("message_deleted", {
            "msg_id": msg_id
        }, room=room)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True)