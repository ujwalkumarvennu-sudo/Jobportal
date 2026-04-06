import os
import PyPDF2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re

def extract_text_from_pdf(pdf_path):
    try:
        if not os.path.exists(pdf_path):
            return ""
        text = ""
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + " "
        return text.strip()
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def calculate_match_score(resume_text, job_description):
    if not resume_text or not job_description:
        return 0
        
    # Clean texts
    def clean_text(text):
        if not text:
            return ""
        text = text.lower()
        # Remove non-alphanumeric and retain spaces
        text = re.sub(r'[^a-z0-9\s]', '', text)
        return text

    clean_resume = clean_text(resume_text)
    clean_jd = clean_text(job_description)
    
    if not clean_resume or not clean_jd:
        return 0

    vectorizer = TfidfVectorizer(stop_words='english')
    try:
        tfidf_matrix = vectorizer.fit_transform([clean_jd, clean_resume])
        similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        # Return as a percentage rounded to 1 decimal
        return round(similarity * 100, 1) 
    except Exception as e:
        print(f"Error calculating score: {e}")
        return 0
