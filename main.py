import re
from typing import List, Dict, Union, Optional 
from fastapi import FastAPI
from pydantic import BaseModel, Field
from fuzzywuzzy import fuzz
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

app = FastAPI()

geolocator = Nominatim(user_agent="job_recommender")


def calculate_location_scores(jobs: List['Job'], candidate_location: str) -> Dict[str, float]:
    distances = {}
    total_distance = 0
    for job in jobs:
        try:
            job_coords = geolocator.geocode(job.location)
            candidate_coords = geolocator.geocode(candidate_location)
            
            if job_coords and candidate_coords:
                distance = geodesic((job_coords.latitude, job_coords.longitude), 
                                    (candidate_coords.latitude, candidate_coords.longitude)).kilometers
                distances[job.location] = distance
                total_distance += distance
            else:
                distances[job.location] = float('inf')  
        except:
            distances[job.location] = float('inf')  
    scores = {}
    for location, distance in distances.items():
        if distance == float('inf'):
            scores[location] = 0
        else:
            scores[location] = 1 - (distance / total_distance)
    
    return scores

def parse_experience(experience_str: str) -> tuple:
    match = re.search(r'(\d+)\s*-\s*(\d+)', experience_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    single_match = re.search(r'(\d+)', experience_str)
    if single_match:
        return int(single_match.group(1)), int(single_match.group(1))
    return 0, 0

def calculate_experience_score(candidate_experience: float, job_experience: str) -> float:
    min_exp, max_exp = parse_experience(job_experience)
    if min_exp <= candidate_experience <= max_exp:
        return 1.0
    elif candidate_experience < min_exp:
        return max(0, 1 - (min_exp - candidate_experience) / min_exp)
    else:
        return max(0, 1 - (candidate_experience - max_exp) / max_exp)

def calculate_skill_score(resume_skills: List[str], job_skills: List[str]) -> float:
    if not resume_skills or not job_skills:
        return 0
    
    matched_scores = []
    for job_skill in job_skills:
        best_match = max(fuzz.token_set_ratio(job_skill.lower(), resume_skill.lower()) for resume_skill in resume_skills)
        matched_scores.append(best_match / 100)
    
    return sum(matched_scores) / len(job_skills)

def parse_salary(salary_str: str) -> tuple:
    match = re.findall(r'(\d+),?(\d+),?(\d+)', salary_str)
    if match:
        return float(''.join(match[0])), float(''.join(match[-1]))
    return 0, 0

def calculate_similarity(resume_skills: List[str], job_skills: List[str]) -> float:
    common_skills = set(resume_skills) & set(job_skills)
    return len(common_skills) / max(len(resume_skills), len(job_skills))

def calculate_salary_score(job_salary: str, candidate_expected_salary: Optional[float]) -> float:
    salary_min, salary_max = parse_salary(job_salary)
    
    if candidate_expected_salary is None:
        return 1  
    if salary_min <= candidate_expected_salary <= salary_max:
        return 1  
    elif candidate_expected_salary < salary_min:
        return max(0, 1 - (salary_min - candidate_expected_salary) / salary_min)
    else:  
        return max(0, 1 - (candidate_expected_salary - salary_max) / salary_max)
    
def calculate_notice_period_score(candidate_notice_period: Optional[int], job_required_joining_time: Optional[int]) -> float:
    if candidate_notice_period is None or job_required_joining_time is None:
        return 1  
    
    if candidate_notice_period < job_required_joining_time :
        return 1  
    
    difference = abs(candidate_notice_period - job_required_joining_time)
    max_difference = max(candidate_notice_period, job_required_joining_time)
    
    return max(0, 1 - (difference / max_difference))

def recommend_jobs(resume: 'Resume', jobs: List['Job'], liked_jobs: List['Job'], weights: Dict[str, float]) -> List[tuple]:
    print("Full resume object:", resume)
    resume_skills = resume.Skills
    candidate_experience = resume.Total_Experience
    candidate_location = resume.Current_Location
    candidate_expected_salary = getattr(resume, 'Expected_Salary', None)
    location_scores = calculate_location_scores(jobs, candidate_location)
    
    job_scores = []
    
    for job in jobs:
        skill_score = calculate_skill_score(resume_skills, job.skills)
        
        experience_score = calculate_experience_score(candidate_experience, job.experience)

        location_score = location_scores[job.location]
        
        salary_score = calculate_salary_score(job.salary, candidate_expected_salary)  
        
        notice_period_score = calculate_notice_period_score(resume.Notice_Period, job.required_joining_time)
        
        hybrid_score = (
            weights['skills'] * skill_score +
            weights['experience'] * experience_score +
            weights['location'] * location_score +
            weights['salary'] * salary_score +
            weights['notice_period'] * notice_period_score
        )
        if job in liked_jobs:
            hybrid_score += weights['liked_bonus']
        
        job_scores.append((job, hybrid_score, skill_score, experience_score, location_score, salary_score, notice_period_score))
    
    job_scores.sort(key=lambda x: x[1], reverse=True)
    
    return job_scores[:weights['top_n']]

class Education(BaseModel):
    Degree: str
    Specialization: str = ""
    Institute: str
    Start: Union[int, str]
    End: Union[int, str]

class Experience(BaseModel):
    Company_name: str = Field(alias="Company Name")
    Designation: str
    Start: Union[int, str]
    End: Union[int, str]
    Description: str

class Resume(BaseModel):
    Name: str
    Email: str
    phone_number: str = Field(alias="Phone-Number")
    Summary: str
    Current_Location: str = Field(alias="Current-Location")
    Current_Company: str = Field(alias="Current-Company")
    Skills: List[str]
    linkedin_id: str = Field(alias="Linkedin-Id")
    github_id: str = Field(alias="Github-Id")
    Total_Experience: float = Field(alias="Total-Experience")
    Education: List[Education]
    education_year: List[Union[int, str]] = Field(alias="Education-Year")
    Experiences: List[Experience]
    Projects: List[Dict[str, str]]
    roles_responsibility: List[str] = Field(alias="Roles-Responsibility")
    Certifications: List[str]
    Expected_Salary: Optional[float] = Field(None, alias="Expected-Salary")
    Notice_Period: Optional[int] = Field(None, description="Notice period in days")

class Job(BaseModel):
    job_title: str
    job_role: str
    work_mode: str
    skills: List[str]
    employment_type: str
    company_name: str
    location: str
    experience: str
    salary: str
    preferred_degree: str
    industry_type: str
    job_description: str
    required_joining_time: Optional[int] = Field(None, description="Required joining time in days")

class InitialRecommendationRequest(BaseModel):
    resume: Resume
    jobs: List[Job]

class UpdateRecommendationRequest(BaseModel):
    resume: Resume
    jobs: List[Job]
    liked_job_titles: List[str]

@app.post("/initial_recommend_jobs/")
async def initial_recommend_jobs(request: InitialRecommendationRequest):
    weights = {
        'skills': 0.75,
        'experience': 0.1,
        'location': 0.03,
        'salary': 0.05,
        'liked_bonus': 0.05,
        'notice_period': 0.02,
        'top_n': 5
    }
    
    recommended_jobs = recommend_jobs(request.resume, request.jobs, [], weights)

    result = []
    for job, hybrid_score, skill_score, experience_score, location_score, salary_score,notice_period_score in recommended_jobs:
        result.append({
            "job_title": job.job_title,
            "job_role": job.job_role,
            "company_name": job.company_name,
            "location": job.location,
            "skills": job.skills,
            "salary": job.salary,
            "experience": job.experience,
            "overall_similarity_score": hybrid_score,
            "skill_score": skill_score,
            "experience_score": experience_score,
            "location_score": location_score,
            "salary_score": salary_score,
            "notice_period_score": notice_period_score
        })

    return result

@app.post("/update_recommend_jobs/")
async def update_recommend_jobs(request: UpdateRecommendationRequest):
    weights = {
        'skills': 0.75,
        'experience': 0.1,
        'location': 0.03,
        'salary': 0.05,
        'liked_bonus': 0.05,
        'notice_period': 0.02,
        'top_n': 5
    }
    
    liked_jobs = [job for job in request.jobs if job.job_title in request.liked_job_titles]
    recommended_jobs = recommend_jobs(request.resume, request.jobs, liked_jobs, weights)

    result = []
    for job, hybrid_score, skill_score, experience_score, location_score, salary_score,notice_period_score in recommended_jobs:
        result.append({
            "job_title": job.job_title,
            "job_role": job.job_role,
            "company_name": job.company_name,
            "location": job.location,
            "skills": job.skills,
            "salary": job.salary,
            "experience": job.experience,
            "overall_similarity_score": hybrid_score,
            "skill_score": skill_score,
            "experience_score": experience_score,
            "location_score": location_score,
            "salary_score": salary_score,
            "notice_period_score": notice_period_score
        })

    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)