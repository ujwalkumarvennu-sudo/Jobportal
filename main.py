from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, SubmitField
from wtforms.validators import DataRequired, Length
from dotenv import load_dotenv
from datetime import datetime, date
import requests
import random
import re
import os
from werkzeug.utils import secure_filename
import ai_matcher

load_dotenv()

app = Flask(__name__)

db_url = os.environ.get('DATABASE_URL', 'sqlite:///jobs.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default_secret_key_fallback')
app.config['CACHE_TYPE'] = 'FileSystemCache'
app.config['CACHE_DIR'] = '.flask_cache'
app.config['UPLOAD_FOLDER'] = 'static/resumes'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 # 5MB max
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'pdf'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)
cache = Cache(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Seekers
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    cover_letter = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending')
    ai_score = db.Column(db.Float, nullable=True) # AI Resumer Match Percentage
    applied_on = db.Column(db.DateTime, default=datetime.utcnow)

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    resume_path = db.Column(db.String(200), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

saved_jobs = db.Table('saved_jobs',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('job_id', db.Integer, db.ForeignKey('job.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='seeker') # 'seeker', 'employer', 'admin'
    skills = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    jobs = db.relationship('Job', backref='author', lazy=True)
    resumes = db.relationship('Resume', backref='user', lazy=True)
    applications = db.relationship('Application', backref='applicant', lazy=True)
    saved_jobs = db.relationship('Job', secondary=saved_jobs, backref=db.backref('savers', lazy=True))

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    job_type = db.Column(db.String(20), nullable=False)  # 'Technical' or 'Non-Technical'
    skills_required = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=False)
    salary = db.Column(db.String(50), nullable=True)
    last_date = db.Column(db.Date, nullable=False)
    posted_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    applications = db.relationship('Application', backref='job', lazy=True)
    
    def __repr__(self):
        return f'<Job {self.title}>'

class JobForm(FlaskForm):
    title = StringField('Job Title', validators=[DataRequired(), Length(max=100)])
    company = StringField('Company Name', validators=[DataRequired(), Length(max=100)])
    job_type = SelectField('Job Type', choices=[('Technical', 'Technical'), ('Non-Technical', 'Non-Technical')], validators=[DataRequired()])
    skills_required = StringField('Skills Required (comma-separated)', validators=[DataRequired()])
    location = StringField('Location', validators=[DataRequired()])
    description = TextAreaField('Job Description', validators=[DataRequired()])
    salary = StringField('Salary (Optional)', validators=[Length(max=50)])
    last_date = DateField('Application Deadline', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Publish Job Listing')

class ApplicationForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Length(max=120)])
    cover_letter = TextAreaField('Cover Letter', validators=[DataRequired()])
    submit = SubmitField('Apply for this position')

class ProfileForm(FlaskForm):
    skills = StringField('Your Skills (comma-separated)', validators=[DataRequired()])
    location = StringField('Your Location', validators=[DataRequired()])
    submit = SubmitField('Update Profile')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def clean_html(raw_html):
    cleaner = re.compile('<.*?>')
    cleantext = re.sub(cleaner, '', raw_html)
    return cleantext

@cache.cached(timeout=300, key_prefix=lambda: f"external_jobs_{request.args.get('q', '')}")
def get_external_jobs(query=""):
    external_jobs = []
    
    # Source 1: Arbeitnow API
    try:
        response = requests.get('https://arbeitnow.com/api/job-board-api')
        data = response.json()
        
        for item in data.get('data', [])[:30]:
            title = item['title']
            company = item['company_name']
            
            if query and query.lower() not in title.lower() and query.lower() not in company.lower():
                continue
                
            is_tech = any(keyword in title.lower() or keyword in item['tags'] for keyword in ['developer', 'engineer', 'data', 'tech', 'software'])
            job_type = 'Technical' if is_tech else 'Non-Technical'
            
            description = clean_html(item['description'])
            
            job = {
                'title': title,
                'company': company,
                'job_type': job_type,
                'description': description[:200] + '...', 
                'last_date': 'Open (Arbeitnow)', 
                'apply_link': item['url'],
                'is_external': True,
                'location': item.get('location', 'Remote')
            }
            external_jobs.append(job)
    except Exception as e:
        print(f"Error fetching Arbeitnow jobs: {e}")

    # Source 2: Remotive API (Remote Jobs)
    try:
        remotive_url = f'https://remotive.com/api/remote-jobs?search={query}&limit=15' if query else 'https://remotive.com/api/remote-jobs?limit=5'
        response = requests.get(remotive_url)
        data = response.json()
        
        # Remotive returns list in 'jobs'
        for item in data.get('jobs', [])[:5]:
            is_tech = any(keyword in item['title'].lower() or keyword in item.get('category', '').lower() for keyword in ['developer', 'engineer', 'data', 'tech', 'software'])
            job_type = 'Technical' if is_tech else 'Non-Technical'

            clean_desc = clean_html(item.get('description', ''))
            salary = item.get('salary', '')
            
            if salary:
                final_desc = f"Salary: {salary}. " + clean_desc
            else:
                final_desc = clean_desc

            job = {
                'title': item['title'],
                'company': item['company_name'],
                'job_type': job_type,
                'description': final_desc[:150] + '...',
                'last_date': 'Open (Remotive)',
                'apply_link': item['url'],
                'is_external': True,
                'location': item.get('candidate_required_location', 'Remote')
            }
            external_jobs.append(job)
    except Exception as e:
        print(f"Error fetching Remotive jobs: {e}")

    random.shuffle(external_jobs)
    return external_jobs

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/jobs')
def jobs():
    query = request.args.get('q', '').strip()
    page = request.args.get('page', 1, type=int)
    
    # Local Jobs
    if query:
        jobs_pagination = Job.query.filter(
            (Job.title.ilike(f'%{query}%')) | 
            (Job.company.ilike(f'%{query}%')) |
            (Job.description.ilike(f'%{query}%'))
        ).order_by(Job.last_date).paginate(page=page, per_page=6, error_out=False)
    else:
        jobs_pagination = Job.query.order_by(Job.last_date).paginate(page=page, per_page=6, error_out=False)
        
    jobs = jobs_pagination.items
    today = date.today()
    
    # Check for jobs expiring today for "notifications"
    expiring_soon = [job for job in jobs if job.last_date == today]
    
    # External Jobs
    external_jobs = get_external_jobs(query=query)
    
    return render_template('index.html', jobs=jobs, external_jobs=external_jobs, expiring_soon=expiring_soon, today=today, pagination=jobs_pagination)

@app.route('/api/jobs')
def api_jobs():
    query = request.args.get('q', '').strip()
    if query:
        jobs = Job.query.filter(
            (Job.title.ilike(f'%{query}%')) | 
            (Job.company.ilike(f'%{query}%')) |
            (Job.description.ilike(f'%{query}%'))
        ).order_by(Job.last_date).all()
    else:
        jobs = Job.query.order_by(Job.last_date).all()
    
    output = []
    for j in jobs:
        output.append({
            'id': j.id, 'title': j.title, 'company': j.company, 
            'type': j.job_type, 'location': j.location, 'salary': j.salary,
            'last_date': str(j.last_date), 'description': j.description[:100] + '...'
        })
    return {'jobs': output}

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'seeker':
        return redirect(url_for('seeker_dashboard'))
    jobs = Job.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', jobs=jobs)

@app.route('/boost_job/<int:id>', methods=['GET', 'POST'])
@login_required
def boost_job(id):
    if current_user.role != 'employer':
        return redirect(url_for('dashboard'))
    job = Job.query.get_or_404(id)
    if job.user_id != current_user.id:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        # Mock payment success
        flash(f'Success! {job.title} has been boosted across the network.', 'success')
        return redirect(url_for('dashboard'))
    
    return render_template('checkout.html', job=job)

@app.route('/seeker_dashboard', methods=['GET', 'POST'])
@login_required
def seeker_dashboard():
    if current_user.role != 'seeker':
        return redirect(url_for('dashboard'))
    
    form = ProfileForm(obj=current_user)
    
    if request.method == 'POST':
        # Handle resume upload
        if 'resume' in request.files:
            file = request.files['resume']
            if file and allowed_file(file.filename):
                filename = secure_filename(f"{current_user.id}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                
                # Check if resume exists
                existing_resume = Resume.query.filter_by(user_id=current_user.id).first()
                if existing_resume:
                    existing_resume.resume_path = filename
                    existing_resume.uploaded_at = datetime.utcnow()
                else:
                    new_resume = Resume(user_id=current_user.id, resume_path=filename)
                    db.session.add(new_resume)
                db.session.commit()
                flash('Resume uploaded successfully!', 'success')
                return redirect(url_for('seeker_dashboard'))
                
        # Handle profile update
        elif form.validate_on_submit():
            current_user.skills = form.skills.data
            current_user.location = form.location.data
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('seeker_dashboard'))
    
    # Matching Algorithm
    recommended_jobs = []
    if current_user.skills:
        user_skills = set([s.strip().lower() for s in current_user.skills.split(',')])
        all_jobs = Job.query.order_by(Job.posted_date.desc()).all()
        for job in all_jobs:
            if job.skills_required:
                job_skills = set([s.strip().lower() for s in job.skills_required.split(',')])
                if user_skills.intersection(job_skills):
                    recommended_jobs.append(job)
    
    my_applications = Application.query.filter_by(user_id=current_user.id).all()
    resume = Resume.query.filter_by(user_id=current_user.id).first()
    return render_template('seeker_dashboard.html', form=form, resume=resume, recommended=recommended_jobs, applications=my_applications)

@app.route('/job/<int:id>', methods=['GET'])
def job_detail(id):
    job = Job.query.get_or_404(id)
    form = ApplicationForm()
    
    # If the user is logged in, autofill name and email
    if current_user.is_authenticated:
        form.name.data = current_user.username
        form.email.data = current_user.email
        
    return render_template('job_detail.html', job=job, form=form)

@app.route('/apply/<int:id>', methods=['POST'])
@login_required
def apply_job(id):
    if current_user.role != 'seeker':
        flash('Only Job Seekers can apply for roles!', 'danger')
        return redirect(url_for('index'))
        
    job = Job.query.get_or_404(id)
    form = ApplicationForm()
    if form.validate_on_submit():
        # Score calculation
        score = None
        if current_user.resumes:
            resume_path = os.path.join(app.config['UPLOAD_FOLDER'], current_user.resumes[0].resume_path)
            resume_text = ai_matcher.extract_text_from_pdf(resume_path)
            score = ai_matcher.calculate_match_score(resume_text, job.description)
            
        application = Application(
            job_id=job.id,
            user_id=current_user.id,
            name=form.name.data,
            email=form.email.data,
            cover_letter=form.cover_letter.data,
            ai_score=score
        )
        db.session.add(application)
        db.session.commit()
        flash(f'Successfully applied for {job.title} at {job.company}!', 'success')
        return redirect(url_for('index'))
    
    flash('There were errors in your application.', 'danger')
    return render_template('job_detail.html', job=job, form=form)

@app.route('/update_app_status/<int:app_id>', methods=['POST'])
@login_required
def update_app_status(app_id):
    if current_user.role != 'employer':
        return redirect(url_for('dashboard'))
    application = Application.query.get_or_404(app_id)
    if application.job.user_id != current_user.id:
        flash('Unauthorized', 'danger')
        return redirect(url_for('dashboard'))
    new_status = request.form.get('status')
    if new_status in ['Pending', 'In Review', 'Rejected', 'Accepted']:
        application.status = new_status
        db.session.commit()
        flash(f'Application status updated to {new_status}.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/save_job/<int:job_id>', methods=['POST'])
@login_required
def save_job(job_id):
    if current_user.role != 'seeker':
        return redirect(url_for('index'))
    job = Job.query.get_or_404(job_id)
    if job in current_user.saved_jobs:
        current_user.saved_jobs.remove(job)
        message = 'Job removed from saved list.'
    else:
        current_user.saved_jobs.append(job)
        message = 'Job saved successfully!'
    db.session.commit()
    flash(message, 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        role = request.form.get('role', 'seeker')
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Super simple validation
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, email=email, password=hashed_password, role=role)
        db.session.add(user)
        db.session.commit()
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user, remember=True)
            return redirect(url_for('index'))
        else:
            flash('Login unsuccessful. Check email and password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Admin access only', 'danger')
        return redirect(url_for('index'))
    total_users = User.query.count()
    total_jobs = Job.query.count()
    total_applications = Application.query.count()
    return render_template('admin_dashboard.html', u_count=total_users, j_count=total_jobs, a_count=total_applications)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_job():
    if current_user.role != 'employer':
        flash('Only Employers can post jobs.', 'danger')
        return redirect(url_for('index'))
        
    form = JobForm()
    if form.validate_on_submit():
        new_job = Job(
            title=form.title.data, 
            company=form.company.data, 
            job_type=form.job_type.data, 
            skills_required=form.skills_required.data,
            location=form.location.data,
            description=form.description.data, 
            salary=form.salary.data, 
            last_date=form.last_date.data, 
            author=current_user
        )
        db.session.add(new_job)
        db.session.commit()
        flash('Your job listing has been published!', 'success')
        return redirect(url_for('index'))
    return render_template('add_job.html', form=form)

@app.route('/seed')
@login_required
def seed_db():
    if not current_user.is_authenticated or current_user.id != 1:
        flash('Unauthorized.', 'danger')
        return redirect(url_for('index'))

    # clear existing data
    db.session.remove()
    db.drop_all()
    db.create_all()
    
    # recreate the admin user so we don't lock ourselves out
    admin = User(username='admin', email='a@a.com', password=bcrypt.generate_password_hash('admin').decode('utf-8'))
    db.session.add(admin)
    db.session.commit()
    
    today = date.today()
    
    jobs = [
        Job(title="Python Developer", company="Tech Corp", job_type="Technical", description="Backend python dev needed.", salary="$100k - $140k", last_date=today),
        Job(title="HR Manager", company="People Inc", job_type="Non-Technical", description="Manage hiring process.", salary="$70k", last_date=today),
        Job(title="Frontend Engineer", company="Web Solutions", job_type="Technical", description="React/Vue expert.", salary="$90k - $120k", last_date=date(2026, 12, 31)),
        Job(title="Sales Executive", company="Market Leaders", job_type="Non-Technical", description="Drive sales growth.", salary="Commission Based", last_date=date(2027, 1, 15))
    ]
    
    db.session.add_all(jobs)
    db.session.commit()
    flash('Database reset and populated with sample jobs including salaries!', 'success')
    return redirect(url_for('index'))

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)
