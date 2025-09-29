# analyzer.py
import spacy, fitz, docx, io, re, numpy as np
from keybert import KeyBERT
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')  # Set non-interactive backend
import matplotlib.pyplot as plt
import shap
import base64
import os # New import

# ========== CONFIG ==========
# Read the API key from an environment variable for security
GOOGLE_API_KEY = os.environ.get('AIzaSyB6tASzks_TKN0GQaYfmpheO2drPcnMV6s')

# Check if the key exists before configuring
if GOOGLE_API_KEY:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        llm = genai.GenerativeModel('gemini-1.5-flash-latest')
    except Exception as e:
        print(f"CRITICAL: Error configuring Google AI. Check API Key. Error: {e}")
        llm = None
else:
    print("CRITICAL: GOOGLE_API_KEY environment variable not set.")
    llm = None

# ========== RESUME PARSER ==========
class ResumeParser:
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            print("Downloading 'en_core_web_sm' model for spaCy...")
            from spacy.cli import download
            download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
        self.kw_model = KeyBERT()

    def extract_text(self, file_path, file_content):
        if file_path.lower().endswith(".pdf"):
            doc = fitz.open(stream=file_content, filetype="pdf")
            return "".join(page.get_text() for page in doc)
        elif file_path.lower().endswith(".docx"):
            doc = docx.Document(io.BytesIO(file_content))
            return "\n".join(para.text for para in doc.paragraphs)
        return ""

    def extract_keywords(self, text, top_n=50):
        if not text or not text.strip():
            return []
        keywords = self.kw_model.extract_keywords(
            text, keyphrase_ngram_range=(1, 2), stop_words="english",
            use_mmr=True, diversity=0.7, top_n=top_n
        )
        return [kw for kw, score in keywords]

parser = ResumeParser()
embedder = SentenceTransformer("all-MiniLM-L6-v2")

# ========== ANALYSIS HELPERS ==========
def calculate_match(resume_keywords, jd_text):
    if not resume_keywords or not jd_text:
        return {"score": 0, "matches": [], "misses": [], "jd_keywords": [], "resume_embeddings": [], "jd_embeddings": []}
    
    jd_keywords = parser.extract_keywords(jd_text, top_n=30)
    
    if not jd_keywords:
        return {"score": 0, "matches": [], "misses": [], "jd_keywords": [], "resume_embeddings": [], "jd_embeddings": []}

    resume_embeddings = embedder.encode(resume_keywords)
    jd_embeddings = embedder.encode(jd_keywords)
    
    similarity_matrix = cosine_similarity(resume_embeddings, jd_embeddings)
    match_percentage, matched_skills, missing_skills = 0, [], []
    
    if similarity_matrix.size > 0:
        max_similarity_scores = np.max(similarity_matrix, axis=0)
        match_percentage = round(np.mean(max_similarity_scores) * 100)
        for i, jd_word in enumerate(jd_keywords):
            if max_similarity_scores[i] >= 0.5:
                matched_skills.append(jd_word)
            else:
                missing_skills.append(jd_word)
            
    return {
        "score": match_percentage, "matches": matched_skills, "misses": missing_skills,
        "jd_keywords": jd_keywords, "resume_embeddings": resume_embeddings, "jd_embeddings": jd_embeddings
    }

def get_ats_feedback(resume_text, jd_text):
    if not llm:
        return "LLM not configured. Please check your API key."
    if not resume_text or not jd_text:
        return "Resume or Job Description was empty, could not generate feedback."
    
    prompt = f"""
    You are an expert ATS and career coach. Analyze the resume against the job description.
    Provide: 1. Overall Summary (2-3 sentences). 2. Years of Experience (estimate). 3. Actionable Suggestions (3-4 bullets).
    --- Job Description: {jd_text} --- Resume: {resume_text}
    """
    try:
        response = llm.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Could not generate AI feedback. Error: {e}"

def get_shap_explanation_base64(resume_embeddings, jd_keywords, jd_embeddings):
    num_jd_keywords = len(jd_keywords)
    if num_jd_keywords < 2 or len(resume_embeddings) == 0:
        return None

    def predict_score(x):
        scores = []
        for row in x:
            active_indices = np.where(row == 1)[0]
            if len(active_indices) == 0:
                scores.append(0); continue
            
            active_jd_embeddings = jd_embeddings[active_indices]
            similarity_matrix = cosine_similarity(resume_embeddings, active_jd_embeddings)
            
            if similarity_matrix.size > 0:
                scores.append(np.mean(np.max(similarity_matrix, axis=0)))
            else:
                scores.append(0)
        return np.array(scores) * 100

    explainer = shap.KernelExplainer(predict_score, np.zeros((1, num_jd_keywords)))
    shap_values = explainer.shap_values(np.ones((1, num_jd_keywords)))

    explanation = shap.Explanation(
        values=shap_values[0], base_values=explainer.expected_value,
        data=np.ones((1, num_jd_keywords)), feature_names=jd_keywords
    )

    fig, ax = plt.subplots()
    shap.waterfall_plot(explanation, max_display=15, show=False)
    plt.title("How Job Description Keywords Impact the Match Score", fontsize=10)
    fig.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    plt.close(fig)
    buf.seek(0)
    
    return base64.b64encode(buf.getvalue()).decode('utf-8')