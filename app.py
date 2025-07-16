import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Database configuration (with Render compatibility)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///student_tracker.db').replace(
    'postgres://', 'postgresql://')  # Critical for Render
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

db = SQLAlchemy(app)

# ===== Models =====
class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(20), unique=True, nullable=False)
    grades = db.relationship('Grade', backref='student', lazy=True, cascade="all, delete-orphan")

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Float, nullable=False)

# ===== Routes =====
@app.route('/')
def index():
    students = Student.query.all()
    return render_template('index.html', students=students)

@app.route('/add_student', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        name = request.form['name']
        roll_number = request.form['roll_number']
        
        if Student.query.filter_by(roll_number=roll_number).first():
            flash('❌ Roll number already exists!', 'error')
        else:
            new_student = Student(name=name, roll_number=roll_number)
            db.session.add(new_student)
            db.session.commit()
            flash('✅ Student added successfully!', 'success')
            return redirect(url_for('index'))
    
    return render_template('add_student.html')

@app.route('/edit_student/<int:student_id>', methods=['GET', 'POST'])
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    if request.method == 'POST':
        try:
            student.name = request.form['name']
            new_roll = request.form['roll_number']
            
            if Student.query.filter(Student.roll_number == new_roll, Student.id != student.id).first():
                flash('❌ Roll number already exists!', 'error')
            else:
                student.roll_number = new_roll
                db.session.commit()
                flash('✅ Student updated!', 'success')
                return redirect(url_for('index'))
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'error')
    
    return render_template('edit_student.html', student=student)

@app.route('/delete_student/<int:student_id>')
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    db.session.delete(student)
    db.session.commit()
    flash('✅ Student and all their grades deleted!', 'success')
    return redirect(url_for('index'))

@app.route('/student/<int:student_id>')
def view_student(student_id):
    student = Student.query.get_or_404(student_id)
    return render_template('student.html', student=student)

@app.route('/add_grade/<int:student_id>', methods=['GET', 'POST'])
def add_grade(student_id):
    student = Student.query.get_or_404(student_id)
    
    if request.method == 'POST':
        subject = request.form['subject']
        try:
            score = float(request.form['score'])
            if not (0 <= score <= 100):
                flash('❌ Score must be between 0 and 100!', 'error')
                return redirect(url_for('add_grade', student_id=student.id))
        except ValueError:
            flash('❌ Please enter a valid number for score', 'error')
            return redirect(url_for('add_grade', student_id=student.id))
        
        new_grade = Grade(
            student_id=student.id,
            subject=subject,
            score=score
        )
        db.session.add(new_grade)
        db.session.commit()
        flash('✅ Grade added successfully!', 'success')
        return redirect(url_for('view_student', student_id=student.id))
    
    return render_template('add_grade.html', student=student)

@app.route('/edit_grade/<int:grade_id>', methods=['GET', 'POST'])
def edit_grade(grade_id):
    grade = Grade.query.get_or_404(grade_id)
    if request.method == 'POST':
        try:
            new_score = float(request.form['score'])
            if not (0 <= new_score <= 100):
                flash('❌ Score must be between 0-100!', 'error')
                return redirect(url_for('edit_grade', grade_id=grade.id))
            
            grade.subject = request.form['subject']
            grade.score = new_score
            db.session.commit()
            flash('✅ Grade updated!', 'success')
            return redirect(url_for('view_student', student_id=grade.student_id))
        except ValueError:
            flash('❌ Invalid score format', 'error')
    
    return render_template('edit_grade.html', grade=grade)

@app.route('/delete_grade/<int:grade_id>')
def delete_grade(grade_id):
    grade = Grade.query.get_or_404(grade_id)
    student_id = grade.student_id
    db.session.delete(grade)
    db.session.commit()
    flash('✅ Grade deleted!', 'success')
    return redirect(url_for('view_student', student_id=student_id))

@app.route('/averages')
def view_averages():
    subject_avg = db.session.query(
        Grade.subject,
        func.avg(Grade.score).label('average')
    ).group_by(Grade.subject).all()
    
    toppers = []
    subjects = {grade.subject for grade in Grade.query.distinct(Grade.subject)}
    for subject in subjects:
        top = Grade.query.filter_by(subject=subject)\
               .order_by(Grade.score.desc()).first()
        if top:
            toppers.append({
                'subject': subject,
                'student': top.student.name,
                'score': top.score
            })
    
    return render_template('averages.html', 
                         subject_avg=subject_avg,
                         toppers=toppers)

@app.route('/export_data')
def export_data():
    try:
        students = Student.query.all()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"student_backup_{timestamp}.txt"
        backup_path = os.path.join('backups', filename)
        
        os.makedirs('backups', exist_ok=True)
        
        with open(backup_path, 'w') as f:
            f.write("=== STUDENT PERFORMANCE TRACKER BACKUP ===\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for student in students:
                f.write(f"STUDENT: {student.name} (Roll: {student.roll_number})\n")
                f.write("GRADES:\n")
                
                if student.grades:
                    for grade in student.grades:
                        f.write(f"  - {grade.subject}: {grade.score}\n")
                else:
                    f.write("  No grades recorded\n")
                
                f.write("\n" + "="*50 + "\n\n")
        
        flash(f'✅ Backup saved to backups/{filename}', 'success')
    except Exception as e:
        flash(f'❌ Backup failed: {str(e)}', 'error')
    
    return redirect(url_for('index'))

# ===== Database Initialization =====
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True)