from flask import Flask, render_template, request, redirect, flash, g
import sqlite3
import os
import click

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Database connection handler
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect('student_tracker.db')
        g.db.row_factory = sqlite3.Row
    return g.db

# Close database connection
@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Initialize database
def init_db():
    with app.app_context():
        db = get_db()
        try:
            db.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    roll_number TEXT UNIQUE NOT NULL
                )
            ''')
            db.execute('''
                CREATE TABLE IF NOT EXISTS grades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    grade REAL NOT NULL,
                    FOREIGN KEY (student_id) REFERENCES students (id),
                    CHECK (grade BETWEEN 0 AND 100)
                )
            ''')
            db.commit()
        except sqlite3.Error as e:
            flash(f"Database error: {str(e)}", "error")

# CLI command to initialize DB
@app.cli.command('init-db')
def init_db_command():
    init_db()
    click.echo("Database initialized.")

# Add this for Render deployment
@app.route('/health')
def health_check():
    return 'OK', 200    

@app.route('/')
def index():
    db = get_db()
    try:
        students = db.execute('SELECT * FROM students ORDER BY name').fetchall()
        subjects = db.execute('''
            SELECT DISTINCT subject 
            FROM grades 
            ORDER BY subject
        ''').fetchall()
        
        return render_template(
            'index.html',
            students=students,
            subjects=subjects
        )
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return render_template('index.html', students=[], subjects=[])

@app.route('/add_student', methods=['POST'])
def add_student():
    name = request.form['name']
    roll_number = request.form['roll_number']
    db = get_db()
    try:
        db.execute('INSERT INTO students (name, roll_number) VALUES (?, ?)', 
                  (name, roll_number))
        db.commit()
        flash('Student added successfully!', 'success')
    except sqlite3.IntegrityError:
        flash('Roll number must be unique!', 'error')
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
    return redirect('/')

@app.route('/add_grade', methods=['POST'])
def add_grade():
    roll_number = request.form['roll_number']
    subject = request.form['subject'].strip()
    try:
        grade = float(request.form['grade'])
    except ValueError:
        flash('Grade must be a number!', 'error')
        return redirect('/')
    
    db = get_db()
    try:
        student = db.execute(
            'SELECT id FROM students WHERE roll_number = ?', 
            (roll_number,)
        ).fetchone()
        
        if not student:
            flash('Student not found!', 'error')
            return redirect('/')
            
        # Check if grade already exists
        existing = db.execute(
            'SELECT 1 FROM grades WHERE student_id = ? AND subject = ?',
            (student['id'], subject)
        ).fetchone()
        
        if existing:
            flash(f'Grade for {subject} already exists! Use edit instead.', 'error')
            return redirect('/')
            
        db.execute(
            'INSERT INTO grades (student_id, subject, grade) VALUES (?, ?, ?)',
            (student['id'], subject, grade)
        )
        db.commit()
        flash('Grade added successfully!', 'success')
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
    return redirect('/')

@app.route('/student/<roll_number>')
def student_details(roll_number):
    db = get_db()
    try:
        student = db.execute(
            'SELECT * FROM students WHERE roll_number = ?', 
            (roll_number,)
        ).fetchone()
        if not student:
            flash('Student not found!', 'error')
            return redirect('/')
        
        grades = db.execute(
            'SELECT subject, grade FROM grades WHERE student_id = ? ORDER BY subject',
            (student['id'],)
        ).fetchall()
        
        return render_template(
            'student_details.html',
            student=student,
            grades=grades
        )
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect('/')

@app.route('/edit_student/<roll_number>', methods=['GET', 'POST'])
def edit_student(roll_number):
    db = get_db()
    if request.method == 'POST':
        new_name = request.form['name']
        new_roll = request.form['roll_number']
        try:
            # Check if new roll number exists (excluding current student)
            existing = db.execute(
                'SELECT 1 FROM students WHERE roll_number = ? AND roll_number != ?',
                (new_roll, roll_number)
            ).fetchone()
            
            if existing:
                flash('Roll number already exists!', 'error')
            else:
                db.execute(
                    'UPDATE students SET name = ?, roll_number = ? WHERE roll_number = ?',
                    (new_name, new_roll, roll_number)
                )
                # Update foreign keys if roll number changed
                if new_roll != roll_number:
                    student_id = db.execute(
                        'SELECT id FROM students WHERE roll_number = ?',
                        (new_roll,)
                    ).fetchone()['id']
                    db.execute(
                        'UPDATE grades SET student_id = ? WHERE student_id IN '
                        '(SELECT id FROM students WHERE roll_number = ?)',
                        (student_id, roll_number)
                    )
                db.commit()
                flash('Student updated successfully!', 'success')
                return redirect('/')
        except sqlite3.Error as e:
            flash(f"Database error: {str(e)}", "error")
    
    # GET request handling
    try:
        student = db.execute(
            'SELECT * FROM students WHERE roll_number = ?',
            (roll_number,)
        ).fetchone()
        if not student:
            flash('Student not found!', 'error')
            return redirect('/')
        return render_template('edit_student.html', student=student)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect('/')

@app.route('/edit_grade/<roll_number>/<subject>', methods=['GET', 'POST'])
def edit_grade(roll_number, subject):
    db = get_db()
    if request.method == 'POST':
        try:
            new_grade = float(request.form['grade'])
        except ValueError:
            flash('Grade must be a number!', 'error')
            return redirect(f'/student/{roll_number}')
            
        try:
            db.execute(
                'UPDATE grades SET grade = ? WHERE student_id = '
                '(SELECT id FROM students WHERE roll_number = ?) AND subject = ?',
                (new_grade, roll_number, subject)
            )
            db.commit()
            flash('Grade updated successfully!', 'success')
            return redirect(f'/student/{roll_number}')
        except sqlite3.Error as e:
            flash(f"Database error: {str(e)}", "error")
    
    # GET request handling
    try:
        grade = db.execute(
            'SELECT grade FROM grades WHERE student_id = '
            '(SELECT id FROM students WHERE roll_number = ?) AND subject = ?',
            (roll_number, subject)
        ).fetchone()
        if not grade:
            flash('Grade not found!', 'error')
            return redirect('/')
        return render_template(
            'edit_grade.html',
            roll_number=roll_number,
            subject=subject,
            current_grade=grade['grade']
        )
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect('/')

@app.route('/delete_student/<roll_number>', methods=['POST'])
def delete_student(roll_number):
    db = get_db()
    try:
        with db:
            # First delete all grades for the student
            db.execute(
                'DELETE FROM grades WHERE student_id IN '
                '(SELECT id FROM students WHERE roll_number = ?)',
                (roll_number,)
            )
            # Then delete the student
            db.execute(
                'DELETE FROM students WHERE roll_number = ?',
                (roll_number,)
            )
        flash('Student and all associated grades deleted successfully!', 'success')
    except sqlite3.Error as e:
        flash(f"Error deleting student: {str(e)}", "error")
    return redirect('/')

@app.route('/delete_subject/<subject>', methods=['POST'])
def delete_subject(subject):
    db = get_db()
    try:
        db.execute('DELETE FROM grades WHERE subject = ?', (subject,))
        db.commit()
        flash(f'All grades for subject {subject} deleted successfully!', 'success')
    except sqlite3.Error as e:
        flash(f"Error deleting subject grades: {str(e)}", "error")
    return redirect('/')

@app.route('/delete_grade/<roll_number>/<subject>', methods=['POST'])
def delete_grade(roll_number, subject):
    db = get_db()
    try:
        db.execute(
            'DELETE FROM grades WHERE student_id = '
            '(SELECT id FROM students WHERE roll_number = ?) AND subject = ?',
            (roll_number, subject)
        )
        db.commit()
        flash(f'Grade for {subject} deleted successfully!', 'success')
    except sqlite3.Error as e:
        flash(f"Error deleting grade: {str(e)}", "error")
    return redirect(f'/student/{roll_number}')

@app.route('/topper/<subject>')
def subject_topper(subject):
    db = get_db()
    try:
        topper = db.execute('''
            SELECT students.name, grades.grade 
            FROM grades 
            JOIN students ON grades.student_id = students.id 
            WHERE grades.subject = ? 
            ORDER BY grades.grade DESC 
            LIMIT 1
        ''', (subject,)).fetchone()
        return render_template('topper.html', topper=topper, subject=subject)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect('/')

@app.route('/class_avg/<subject>')
def class_average(subject):
    db = get_db()
    try:
        avg = db.execute(
            'SELECT AVG(grade) FROM grades WHERE subject = ?',
            (subject,)
        ).fetchone()[0]
        return render_template('class_avg.html', avg=avg or 0, subject=subject)
    except sqlite3.Error as e:
        flash(f"Database error: {str(e)}", "error")
        return redirect('/')

@app.route('/export')
def export_data():
    db = get_db()
    try:
        students = db.execute('SELECT * FROM students').fetchall()
        with open('student_data_backup.txt', 'w') as f:
            for student in students:
                grades = db.execute(
                    'SELECT subject, grade FROM grades WHERE student_id = ?',
                    (student['id'],)
                ).fetchall()
                f.write(f"Student: {student['name']} (Roll: {student['roll_number']})\n")
                for grade in grades:
                    f.write(f"{grade['subject']}: {grade['grade']}\n")
                f.write("\n")
        flash('Data exported to student_data_backup.txt!', 'success')
    except Exception as e:
        flash(f"Export error: {str(e)}", "error")
    return redirect('/')

if __name__ == '__main__':
    if not os.path.exists('student_tracker.db'):
        init_db()
    app.run(debug=True)