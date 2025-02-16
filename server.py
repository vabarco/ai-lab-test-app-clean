from dotenv import load_dotenv
import os
import openai
import pytesseract
import traceback
import re
import threading
import uuid
import PyPDF2
from PIL import Image
from flask import Flask, request, jsonify, session, send_from_directory, redirect, url_for
from flask_dance.contrib.google import make_google_blueprint, google
from flask_cors import CORS
from fpdf import FPDF
from supabase import create_client, Client
from flask import Flask, send_from_directory

# ✅ Load environment variables from .env
load_dotenv()

# ✅ Debugging: Ensure environment variables are loaded
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SECRET_KEY = os.getenv("SECRET_KEY")

if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SECRET_KEY]):
    raise ValueError("Missing required environment variables. Check .env file.")

# ✅ Initialize Flask App
app = Flask(__name__, static_folder='public')
app.secret_key = SECRET_KEY
app.config["SESSION_TYPE"] = "filesystem"

# ✅ Allow CORS
CORS(app, origins=["*"])

# ✅ Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ✅ Google OAuth Setup
google_bp = make_google_blueprint(
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_to="google_login",
)
app.register_blueprint(google_bp, url_prefix="/login")

# ✅ Serve Frontend Files
@app.route('/')
def serve_index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    if filename.endswith('.js'):
        return send_from_directory('public', filename, mimetype='application/javascript')
    elif filename.endswith('.css'):
        return send_from_directory('public', filename, mimetype='text/css')
    return send_from_directory('public', filename)

# ✅ Google Login
@app.route("/google-login")
def google_login():
    if not google.authorized:
        return redirect(url_for("google.login"))

    resp = google.get("/oauth2/v2/userinfo")
    if not resp.ok:
        return f"Google login failed: {resp.text}", 400

    user_info = resp.json()
    user_email = user_info.get("email")
    user_name = user_info.get("name", "Unknown User")

    if not user_email:
        return "Error: Google did not return an email address.", 400

    # ✅ Check if user exists in Supabase
    existing_user = supabase.table("users").select("*").eq("email", user_email).execute()
    if not existing_user.data:
        supabase.table("users").insert({"email": user_email, "name": user_name}).execute()

    # ✅ Store user details in session
    session["user_email"] = user_email
    session["user_name"] = user_name
    session["user_id"] = user_info["id"]

    return redirect(url_for("serve_index"))

# ✅ Check Authentication Status
@app.route("/is_authenticated")
def is_authenticated():
    return jsonify({"authenticated": "user_email" in session, "user": session.get("user_name", "Unknown User")})

# ✅ Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("serve_index"))

# ✅ Extract Patient Info
def extract_patient_info(content):
    name_pattern = r"(?:Name|Patient Name|Nom du patient)[:\s]*([\w\s]+)"
    date_pattern = r"(?:Date|Test Date|Date du test)[:\s]*(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})"

    name_match = re.search(name_pattern, content, re.IGNORECASE)
    date_match = re.search(date_pattern, content, re.IGNORECASE)

    return name_match.group(1).strip() if name_match else "[Unknown]", date_match.group(1).strip() if date_match else "[Unknown]"

# ✅ Store analysis results
analysis_results = {}

# ✅ Function to process file & generate report asynchronously
def process_analysis(task_id, file_content, user_email):
    try:
        patient_name, test_date = extract_patient_info(file_content)

        # ✅ OpenAI Analysis
        prompt = f"""
        You are a medical assistant interpreting lab tests.
        Patient's Name: {patient_name}
        Test Date: {test_date}

        Lab Test Data:
        {file_content}
        """

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Analyze the following lab test results carefully."},
                {"role": "user", "content": prompt}
            ]
        )

        full_analysis = response["choices"][0]["message"]["content"].strip()

        # ✅ Save analysis to a PDF
        pdf_filename = f"static/reports/{task_id}.pdf"
        os.makedirs("static/reports", exist_ok=True)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", style='B', size=16)
        pdf.cell(200, 10, "Lab Test Analysis Report", ln=True, align='C')
        pdf.ln(10)

        pdf.set_font("Arial", style='B', size=12)
        pdf.cell(0, 10, f"Patient's Name: {patient_name}", ln=True)
        pdf.cell(0, 10, f"Test Date: {test_date}", ln=True)
        pdf.cell(0, 10, "Test Type: Comprehensive Lab Report", ln=True)
        pdf.ln(10)

        pdf.set_font("Arial", size=12)
        pdf.multi_cell(0, 8, full_analysis)
        pdf.ln(5)

        pdf.output(pdf_filename, 'F')

        # ✅ Store result
        analysis_results[task_id] = {
            "analysis": full_analysis,
            "download_link": f"/{pdf_filename}"
        }

    except Exception as e:
        analysis_results[task_id] = {"error": str(e)}

# ✅ Start Analysis & Return Task ID
@app.route('/analyze', methods=['POST'])
def analyze_data():
    if "user_email" not in session:
        return jsonify({"error": "You must be signed in to analyze files."}), 403

    file = request.files.get('file')
    if not file or file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    content = file.read().decode('utf-8')  # Assume text-based input for now

    # ✅ Generate a unique task ID
    task_id = str(uuid.uuid4())

    # ✅ Start background processing
    threading.Thread(target=process_analysis, args=(task_id, content, session["user_email"])).start()

    return jsonify({"message": "Processing started", "task_id": task_id})

# ✅ Run Flask App
if __name__ == "__main__":
    app.run(debug=True)
