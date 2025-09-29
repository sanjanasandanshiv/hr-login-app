# app.py
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_from_directory
from flask_cors import CORS
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import os
from werkzeug.utils import secure_filename
import analyzer
import io

app = Flask(__name__)
CORS(app)

# Read the secret key from an environment variable for security
app.secret_key = os.environ.get('SECRET_KEY', 'a_default_secret_key_for_local_dev')

DATABASE = 'hr_users.db'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# --- Page Routes ---
@app.route('/')
def register_page():
    return render_template('register.html')

@app.route('/login')
def login_page():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    conn = get_db_connection()
    jobs = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('dashboard.html', username=session['username'], jobs=jobs)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/create-job', methods=['GET'])
def create_job_page():
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    return render_template('create_job.html')

@app.route('/apply/<link_id>', methods=['GET'])
def apply_page(link_id):
    conn = get_db_connection()
    job = conn.execute('SELECT * FROM jobs WHERE unique_link_id = ?', (link_id,)).fetchone()
    conn.close()
    if job is None: return "Job not found", 404
    return render_template('apply.html', job=job)

@app.route('/applicant/<int:applicant_id>')
def applicant_details(applicant_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    conn = get_db_connection()
    applicant = conn.execute('SELECT * FROM applications WHERE id = ?', (applicant_id,)).fetchone()
    conn.close()
    if applicant is None: return "Applicant not found", 404
    return render_template('applicant_details.html', applicant=applicant)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # Note: For a real production app, you'd want a more secure way to handle file access
    # This is fine for this project.
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    
@app.route('/job/<int:job_id>/applicants')
def view_applicants(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    conn = get_db_connection()
    job = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    applicants = conn.execute('SELECT * FROM applications WHERE job_id = ? ORDER BY applied_at DESC', (job_id,)).fetchall()
    conn.close()
    if job is None: return "Job not found", 404
    return render_template('view_applicants.html', job=job, applicants=applicants)

@app.route('/applicant/<int:applicant_id>/delete', methods=['POST'])
def delete_applicant(applicant_id):
    if 'user_id' not in session: return redirect(url_for('login_page'))
    conn = get_db_connection()
    application = conn.execute('SELECT * FROM applications WHERE id = ?', (applicant_id,)).fetchone()
    if application:
        job_id = application['job_id']
        if application['resume_filename']:
            resume_path = os.path.join(app.config['UPLOAD_FOLDER'], application['resume_filename'])
            if os.path.exists(resume_path): os.remove(resume_path)
        if application['photo_filename']:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], application['photo_filename'])
            if os.path.exists(photo_path): os.remove(photo_path)
        conn.execute('DELETE FROM applications WHERE id = ?', (applicant_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('view_applicants', job_id=job_id))

@app.route('/job/<int:job_id>/delete', methods=['POST'])
def delete_job(job_id):
    if 'user_id' not in session:
        return redirect(url_for('login_page'))
    conn = get_db_connection()
    applications = conn.execute('SELECT * FROM applications WHERE job_id = ?', (job_id,)).fetchall()
    for application in applications:
        if application['resume_filename']:
            resume_path = os.path.join(app.config['UPLOAD_FOLDER'], application['resume_filename'])
            if os.path.exists(resume_path): os.remove(resume_path)
        if application['photo_filename']:
            photo_path = os.path.join(app.config['UPLOAD_FOLDER'], application['photo_filename'])
            if os.path.exists(photo_path): os.remove(photo_path)
    conn.execute('DELETE FROM applications WHERE job_id = ?', (job_id,))
    conn.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('dashboard'))

# --- API Routes ---
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username, password = data.get('username'), data.get('password')
    if not username or not password: return jsonify({"message": "Username and password are required!"}), 400
    hashed_password = generate_password_hash(password)
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"message": "Username already exists!"}), 400
    finally: conn.close()
    return jsonify({"message": "User created successfully!"}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username, password = data.get('username'), data.get('password')
    if not username or not password: return jsonify({"message": "Invalid credentials!"}), 400
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if user and check_password_hash(user['password'], password):
        session['user_id'], session['username'] = user['id'], user['username']
        return jsonify({"message": "Login successful!"}), 200
    else:
        return jsonify({"message": "Invalid credentials!"}), 401

@app.route('/create-job', methods=['POST'])
def create_job():
    if 'user_id' not in session: return jsonify({"message": "Unauthorized"}), 401
    data = request.get_json()
    link_id = str(uuid.uuid4())
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO jobs (job_title, job_description, location, required_skills, resume_keywords, unique_link_id, created_by_user_id) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (data['job_title'], data['job_description'], data['location'], data['required_skills'], data['resume_keywords'], link_id, session['user_id'])
    )
    conn.commit()
    conn.close()
    full_link = url_for('apply_page', link_id=link_id, _external=True)
    return jsonify({"message": "Job link created!", "link": full_link}), 201

@app.route('/apply/<link_id>', methods=['POST'])
def handle_application(link_id):
    conn = get_db_connection()
    job = conn.execute('SELECT * FROM jobs WHERE unique_link_id = ?', (link_id,)).fetchone()
    if job is None: conn.close(); return jsonify({"message": "Job not found"}), 404
    if 'resume' not in request.files: conn.close(); return jsonify({"message": "Resume file is required"}), 400
    resume_file = request.files['resume']
    if resume_file.filename == '': conn.close(); return jsonify({"message": "No resume selected"}), 400

    if resume_file and allowed_file(resume_file.filename):
        resume_content = resume_file.read()
        resume_file.seek(0)
        unique_resume_filename = str(uuid.uuid4()) + "_" + secure_filename(resume_file.filename)
        resume_file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_resume_filename))
        
        try:
            resume_text = analyzer.parser.extract_text(unique_resume_filename, resume_content)
            resume_keywords = analyzer.parser.extract_keywords(resume_text)
            jd_text = job['job_description'] + " " + job['required_skills']
            match_data = analyzer.calculate_match(resume_keywords, jd_text)
            ai_feedback = analyzer.get_ats_feedback(resume_text, jd_text)
            xai_chart = analyzer.get_shap_explanation_base64(match_data['resume_embeddings'], match_data['jd_keywords'], match_data['jd_embeddings'])
        except Exception as e:
            print(f"Error during analysis: {e}")
            match_data = {'score': 0, 'matches': [], 'misses': []}
            ai_feedback = "Error during analysis. Please check server logs for details."
            xai_chart = None

        photo_filename = None
        photo_file = request.files.get('photo')
        if photo_file and allowed_file(photo_file.filename):
            photo_filename = str(uuid.uuid4()) + "_" + secure_filename(photo_file.filename)
            photo_file.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))

        conn.execute(
            'INSERT INTO applications (job_id, applicant_name, applicant_email, applicant_contact, resume_filename, photo_filename, match_score, matched_skills, missing_skills, ai_feedback, xai_chart_base64) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (job['id'], request.form['applicant_name'], request.form['applicant_email'], request.form.get('applicant_contact'), unique_resume_filename, photo_filename, match_data['score'], ", ".join(match_data.get('matches', [])), ", ".join(match_data.get('misses', [])), ai_feedback, xai_chart)
        )
        conn.commit()
        conn.close()
        return jsonify({"message": "Application submitted successfully!"}), 201
    else:
        conn.close()
        return jsonify({"message": "File type not allowed"}), 400

# NOTE: The __main__ block is not needed for deployment on Render, 
# but it's good to keep for local testing.
if __name__ == '__main__':
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(host='0.0.0.0', debug=True, port=5000)