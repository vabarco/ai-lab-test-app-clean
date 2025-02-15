from dotenv import load_dotenv
import os
# ✅ Allow OAuth to work over HTTP (for local development)
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from flask import Flask, request, jsonify, session, send_from_directory, redirect, url_for
from flask_dance.contrib.google import make_google_blueprint, google
from supabase import create_client, Client
import openai
import pytesseract
from PIL import Image
import PyPDF2
import traceback
import re
from fpdf import FPDF
from flask_cors import CORS
import threading
import uuid

# Load environment variables from .env file
load_dotenv()

# Debugging: Check if variables are loaded
print("SUPABASE_URL:", os.getenv("SUPABASE_URL"))
print("SUPABASE_KEY:", "Loaded!" if os.getenv("SUPABASE_KEY") else "Missing!")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# Check if variables are loaded
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# ✅ Create Supabase Client
from supabase import create_client, Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SECRET_KEY = os.getenv("SECRET_KEY")

# ✅ Flask App Setup
app = Flask(__name__, static_folder="public", static_url_path="/")
app.secret_key=os.getenv("SECRET_KEY")
app.config["SESSION_TYPE"] = "filesystem"
CORS(app)

# ✅ Supabase Setup
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ✅ Google OAuth Setup
google_bp = make_google_blueprint(
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    scope=["openid", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/userinfo.profile"],
    redirect_to="google_login",  # Keep this!
)
app.register_blueprint(google_bp, url_prefix="/login")

# ✅ Serve Frontend Files
@app.route("/")
def serve_index():
    return send_from_directory("public", "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory("public", filename)

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
        # ✅ Insert new user
        supabase.table("users").insert({"email": user_email, "name": user_name}).execute()

    # ✅ Store user details in session
    session["user_email"] = user_email
    session["user_name"] = user_name
    session["user_id"] = user_info["id"]

    return redirect(url_for("serve_index"))

# ✅ Check Authentication Status
@app.route("/is_authenticated")
def is_authenticated():
    if "user_email" in session:
        return jsonify({"authenticated": True, "user": session.get("user_name", "Unknown User")})
    return jsonify({"authenticated": False})

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

    patient_name = name_match.group(1).strip() if name_match else "[Unknown]"
    test_date = date_match.group(1).strip() if date_match else "[Unknown]"

    return patient_name, test_date

@app.route('/analyze', methods=['POST'])
def analyze_data():
    print("📤 Received analyze request")  # Debugging log

    if "user_email" not in session:
        print("🚫 User not authenticated!")
        return jsonify({"error": "You must be signed in to analyze files."}), 403

    if 'file' not in request.files:
        print("🚫 No file received")
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        print("🚫 No file selected")
        return jsonify({"error": "No selected file"}), 400

    try:
        print("📄 Processing file:", file.filename)
        file_extension = file.filename.split('.')[-1].lower()
        content = ""

        if file_extension == 'pdf':
            print("📑 Extracting text from PDF...")
            pdf_reader = PyPDF2.PdfReader(file)
            content = "\n".join([page.extract_text() or '' for page in pdf_reader.pages])

        elif file_extension == 'txt':
            print("📜 Extracting text from TXT file...")
            content = file.read().decode('utf-8')

        elif file_extension == 'jpg':
            print("🖼 Extracting text from Image using OCR...")
            image = Image.open(file)
            content = pytesseract.image_to_string(image)

        else:
            print("🚫 Unsupported file format")
            return jsonify({"error": "Unsupported file format. Please upload a .txt, .pdf, or .jpg file."}), 400

        if not content.strip():
            print("🚫 No readable text found in file")
            return jsonify({"error": "No readable text found in the file"}), 400

        # Debugging OpenAI request
        print("📝 Sending request to OpenAI...")
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Analyze the following lab test results carefully."},
                {"role": "user", "content": content}
            ]
        )

        full_analysis = response.choices[0].message.content.strip()
        print("✅ OpenAI response received!")

        return jsonify({"analysis": full_analysis})

    except Exception as e:
        print("❌ ERROR TRACEBACK:", traceback.format_exc())
        return jsonify({"error": f"Internal Server Error: {str(e)}"}), 500

# ✅ Store analysis results
analysis_results = {}

# ✅ Function to process file & generate report asynchronously
def process_analysis(task_id, file, file_extension, user_email):
    try:
        content = ""

        # ✅ Extract text from the uploaded file
        if file_extension == 'pdf':
            pdf_reader = PyPDF2.PdfReader(file)
            content = "\n".join([page.extract_text() or '' for page in pdf_reader.pages])
        elif file_extension == 'txt':
            content = file.read().decode('utf-8')
        elif file_extension == 'jpg':
            image = Image.open(file)
            content = pytesseract.image_to_string(image)
        else:
            analysis_results[task_id] = {"error": "Unsupported file format."}
            return

        if not content.strip():
            analysis_results[task_id] = {"error": "No readable text found in the file."}
            return

        patient_name, test_date = extract_patient_info(content)

        # ✅ OpenAI Analysis
        prompt = f"""
        You are a medical assistant interpreting lab tests.
        Patient's Name: {patient_name}
        Test Date: {test_date}

        Lab Test Data:
        {content}
        """

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Analyze the following lab test results carefully."},
                {"role": "user", "content": prompt}
            ]
        )

        full_analysis = response.choices[0].message.content.strip()

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
        utf8_analysis = full_analysis.encode("latin-1", "ignore").decode("latin-1")
        pdf.multi_cell(0, 8, utf8_analysis)
        pdf.ln(5)

        pdf.output(pdf_filename, 'F')

        # ✅ Store result
        analysis_results[task_id] = {
            "analysis": full_analysis,
            "download_link": f"/{pdf_filename}"
        }

    except Exception as e:
        analysis_results[task_id] = {"error": str(e)}

# ✅ New API: Start Analysis & Return Task ID
@app.route('/analyze', methods=['POST'])
def analyze_data_v2():
    if "user_email" not in session:
        return jsonify({"error": "You must be signed in to analyze files."}), 403

    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    file_extension = file.filename.split('.')[-1].lower()

    # ✅ Generate a unique task ID
    task_id = str(uuid.uuid4())

    # ✅ Start background processing
    thread = threading.Thread(target=process_analysis, args=(task_id, file, file_extension, session["user_email"]))
    thread.start()

    return jsonify({"message": "Processing started", "task_id": task_id})

# ✅ New API: Check Analysis Status
@app.route('/analysis_status/<task_id>', methods=['GET'])
def get_analysis_status(task_id):
    if task_id in analysis_results:
        return jsonify(analysis_results[task_id])
    return jsonify({"status": "Processing, please wait..."}), 202

# ✅ Run Flask App
if __name__ == "__main__":
    app.run(debug=True)
