import os
import random
from main import app, db, User, Job, Application, bcrypt
from datetime import datetime, timedelta

def seed():
    with app.app_context():
        # Ensure db exists
        db.create_all()

        # 1. Create Core Users
        def create_user(username, email, role):
            u = User.query.filter_by(email=email).first()
            if not u:
                pwd = bcrypt.generate_password_hash('password123').decode('utf-8')
                u = User(username=username, email=email, password=pwd, role=role)
                if role == 'seeker':
                    u.skills = 'Python, SQL, React, Node.js, AWS'
                    u.location = 'New York, USA'
                db.session.add(u)
                db.session.commit()
            return u

        admin = create_user('Admin', 'admin@example.com', 'admin')
        employer = create_user('DemoCorp', 'hr@democorp.com', 'employer')
        employer2 = create_user('TechNova', 'hiring@technova.com', 'employer')
        seeker = create_user('JohnDoe', 'john@example.com', 'seeker')

        # 2. Clear previous jobs and applications so we get fresh data
        Application.query.delete()
        Job.query.delete()
        db.session.commit()

        # Add Dummy Jobs
        tech_roles = ['Software Engineer', 'Frontend Developer', 'Backend Developer', 'Data Scientist', 'DevOps Engineer', 'Full-Stack Developer', 'Cloud Architect']
        non_tech_roles = ['Marketing Manager', 'HR Specialist', 'Sales Representative', 'Product Manager', 'Customer Support', 'Business Analyst']
        
        # Mapping companies to their typical regional hubs
        company_data = {
            'Google': ['New York', 'San Francisco', 'Seattle', 'London', 'Remote'],
            'Deloitte': ['London', 'Manchester', 'Berlin', 'Paris', 'New York'],
            'TCS': ['Bangalore', 'Mumbai', 'Hyderabad', 'London', 'Remote'],
            'Infosys': ['Bangalore', 'Mumbai', 'Hyderabad', 'Amsterdam', 'Seattle'],
            'TechNova': ['Berlin', 'Paris', 'Remote']
        }

        job_count = 0
        
        # Ensure EVERY company has multiple roles in EVERY one of its locations!
        for company, locations in company_data.items():
            for location in locations:
                # Add 3 unique jobs for each location config to guarantee rich data
                for _ in range(3):
                    is_tech = random.choice([True, False])
                    title = random.choice(tech_roles) if is_tech else random.choice(non_tech_roles)
                    
                    job_type = 'Technical' if is_tech else 'Non-Technical'
                    skills = 'Python, React, AWS' if is_tech else 'Communication, Management, Excel'
                    
                    # Make some jobs expire today, some in past, some in future
                    days_offset = random.randint(-5, 30)
                    last_date = datetime.utcnow().date() + timedelta(days=days_offset)
                    
                    if location in ['Bangalore', 'Mumbai', 'Hyderabad']:
                        salary_low = random.randint(8, 30)
                        salary_high = salary_low + random.randint(3, 15)
                        salary_str = f"INR {salary_low} LPA - {salary_high} LPA"
                    elif location in ['London', 'Manchester']:
                        salary_low = random.randint(40, 90)
                        salary_high = salary_low + random.randint(10, 30)
                        salary_str = f"GBP {salary_low}k - {salary_high}k"
                    elif location in ['Berlin', 'Paris', 'Amsterdam']:
                        salary_low = random.randint(50, 95)
                        salary_high = salary_low + random.randint(10, 25)
                        salary_str = f"EUR {salary_low}k - {salary_high}k"
                    else:
                        salary_low = random.randint(70, 160)
                        salary_high = salary_low + random.randint(20, 50)
                        salary_str = f"USD {salary_low}k - {salary_high}k"
                    
                    emp_id = employer.id if job_count % 2 == 0 else employer2.id

                    j = Job(
                        title=f"{title} - Level {random.randint(1,4)}",
                        company=company,
                        job_type=job_type,
                        skills_required=skills,
                        location=location,
                        description=f"We are looking for an experienced {title} to join our growing team at {company} in {location}. You will be responsible for defining and driving key initiatives. Excellent compensation and benefits.",
                        salary=salary_str,
                        last_date=last_date,
                        user_id=emp_id
                    )
                    db.session.add(j)
                    job_count += 1
        
        db.session.commit()
        print(f"{job_count} fresh demo jobs added across all cities.")

        # 3. Add Dummy Applications
        jobs = Job.query.all()
        if jobs:
            for i in range(5):
                j = random.choice(jobs)
                existing_app = Application.query.filter_by(user_id=seeker.id, job_id=j.id).first()
                if not existing_app:
                    demo_app = Application(
                        job_id=j.id,
                        user_id=seeker.id,
                        name=seeker.username,
                        email=seeker.email,
                        cover_letter='This is a demo application generated by the seeder. Very interested in this role!',
                        status=random.choice(['Pending', 'In Review', 'Accepted', 'Rejected']),
                        ai_score=random.choice([75.5, 82.0, 95.5, 60.0])
                    )
                    db.session.add(demo_app)
            db.session.commit()
            print("Demo applications added.")

        print("Success! Dummy jobs, admin accounts, and applications have been fully seeded!")

if __name__ == "__main__":
    seed()
