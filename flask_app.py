from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
from anthropic import Anthropic
from dotenv import load_dotenv
from models import db, Workspace, Chat
import os

# Load environment variables
load_dotenv()
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")

# Initialize Flask app
app = Flask(__name__)

# Configure SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bob_project.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configure Flask-Session
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = 'your-secret-key-here'

# Initialize extensions
db.init_app(app)
Session(app)

# Initialize Anthropic Client
client = Anthropic(api_key=CLAUDE_API_KEY)

def init_db():
    with app.app_context():
        db.create_all()
        # Create default workspace if none exists
        if not Workspace.query.first():
            default_workspace = Workspace(
                name="Default Workspace",
                instructions="Default instructions for this workspace."
            )
            db.session.add(default_workspace)
            db.session.commit()

@app.route("/")
def index():
    workspaces = Workspace.query.all()
    current_workspace_id = session.get('current_workspace_id')
    
    if not current_workspace_id and workspaces:
        current_workspace_id = workspaces[0].id
        session['current_workspace_id'] = current_workspace_id

    current_workspace = Workspace.query.get(current_workspace_id) if current_workspace_id else None
    chats = Chat.query.filter_by(workspace_id=current_workspace_id).order_by(Chat.created_at.desc()).all() if current_workspace_id else []

    return render_template("index.html", 
                         workspaces=workspaces,
                         current_workspace_id=current_workspace_id,
                         workspace=current_workspace,
                         chats=chats)
@app.route("/generate", methods=["POST"])
def generate():
    try:
        prompt = request.form.get("prompt")
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        current_workspace_id = session.get('current_workspace_id')
        if not current_workspace_id:
            return jsonify({"error": "No workspace selected"}), 400
        
        workspace = Workspace.query.get(current_workspace_id)
        if not workspace:
            return jsonify({"error": "Invalid workspace"}), 400

        # Debug print
        print(f"Sending prompt to Claude: {prompt}")
        print(f"Using API key: {CLAUDE_API_KEY[:8]}...") # Print first 8 chars of API key to verify it's loaded

        # Format system prompt with workspace instructions
        system_prompt = f"""Please follow these specific instructions for this workspace:

{workspace.instructions}

Maintain this role and these instructions throughout our conversation."""

        # Generate response using Claude
        try:
            response = client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )
            
            # Debug print
            print(f"Received response from Claude")

            # Save chat to database
            chat = Chat(
                prompt=prompt,
                response=response.content[0].text,
                workspace_id=current_workspace_id
            )
            db.session.add(chat)
            db.session.commit()

            return jsonify({
                "success": True,
                "prompt": prompt,
                "response": response.content[0].text
            })

        except Exception as api_error:
            print(f"Claude API error: {str(api_error)}")
            return jsonify({"error": f"Claude API error: {str(api_error)}"}), 500

    except Exception as e:
        print(f"Server error: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route("/workspace/switch", methods=["POST"])
def switch_workspace():
    workspace_id = request.form.get("workspace_id")
    session['current_workspace_id'] = int(workspace_id)
    return jsonify({"success": True})

@app.route("/workspace/create", methods=["POST"])
def create_workspace():
    name = request.form.get("name")
    workspace = Workspace(name=name)
    db.session.add(workspace)
    db.session.commit()
    return jsonify({"success": True})

@app.route("/clear", methods=["POST"])
def clear_history():
    current_workspace_id = session.get('current_workspace_id')
    if current_workspace_id:
        Chat.query.filter_by(workspace_id=current_workspace_id).delete()
        db.session.commit()
    return jsonify({"success": True})

@app.route("/workspace/<int:workspace_id>/instructions", methods=["POST"])
def update_instructions(workspace_id):
    workspace = Workspace.query.get_or_404(workspace_id)
    workspace.instructions = request.form.get("instructions")
    db.session.commit()
    return jsonify({"success": True})

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
