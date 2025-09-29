# setup_database.py
import sqlite3

conn = sqlite3.connect('hr_users.db')
cursor = conn.cursor()

# Create the 'users' table
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL
)
''')

# Create the 'jobs' table
cursor.execute('''
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_title TEXT NOT NULL,
    job_description TEXT NOT NULL,
    location TEXT,
    required_skills TEXT,
    resume_keywords TEXT,
    unique_link_id TEXT NOT NULL UNIQUE,
    created_by_user_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by_user_id) REFERENCES users (id)
)
''')

# Create the 'applications' table WITHOUT the xai_chart_base64 column
cursor.execute('''
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    applicant_name TEXT NOT NULL,
    applicant_email TEXT NOT NULL,
    applicant_contact TEXT,
    resume_filename TEXT NOT NULL,
    photo_filename TEXT,
    match_score INTEGER,
    matched_skills TEXT,
    missing_skills TEXT,
    ai_feedback TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs (id)
)
''')

print("Database tables are ready.")
conn.commit()
conn.close()