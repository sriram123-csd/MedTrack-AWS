from flask import Flask, request, jsonify, session, render_template, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from dotenv import load_dotenv
import boto3
import logging
import os
import uuid
from functools import wraps
from boto3.dynamodb.conditions import Key, Attr

# Load environment variables
load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(_name_)

# Flask App
app = Flask(_name_)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

# AWS config
AWS_REGION = os.environ.get('AWS_REGION_NAME', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)

# Table accessors
def get_users_table():
    return dynamodb.Table(os.getenv('USERS_TABLE_NAME', 'MedTrackUsers'))

def get_appointments_table():
    return dynamodb.Table(os.getenv('APPOINTMENTS_TABLE_NAME', 'MedTrackAppointments'))

# Decorators
def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if 'user' not in session:
                flash("Login required", 'warning')
                return redirect(url_for('login', role='patient'))
            if role and session.get('role') != role:
                flash("Unauthorized", 'danger')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return wrapper
    return decorator

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup/<role>', methods=['GET', 'POST'])
def signup(role):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        table = get_users_table()
        response = table.get_item(Key={'email': email})
        if 'Item' in response:
            flash('User already exists.', 'danger')
            return render_template('signup.html', role=role)

        user_id = str(uuid.uuid4())
        hashed = generate_password_hash(password)

        table.put_item(Item={
            'email': email,
            'user_id': user_id,
            'name': name,
            'password_hash': hashed,
            'role': role,
            'created_at': datetime.utcnow().isoformat(),
        })

        flash('Signup successful!', 'success')
        return redirect(url_for('login', role=role))

    return render_template('signup.html', role=role)

@app.route('/login/<role>', methods=['GET', 'POST'])
def login(role):
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        table = get_users_table()
        response = table.get_item(Key={'email': email})
        user = response.get('Item')

        if not user or user['role'] != role:
            flash('Invalid credentials', 'danger')
            return render_template('login.html', role=role)

        if not check_password_hash(user['password_hash'], password):
            flash('Wrong password', 'danger')
            return render_template('login.html', role=role)

        session['user'] = user['email']
        session['name'] = user['name']
        session['role'] = user['role']
        session['user_id'] = user['user_id']

        flash('Login successful', 'success')
        return redirect(url_for(f'{role}_dashboard'))

    return render_template('login.html', role=role)

@app.route('/logout')
@login_required()
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))

@app.route('/patient_dashboard')
@login_required(role='patient')
def patient_dashboard():
    user_email = session['user']
    table = get_users_table()
    user = table.get_item(Key={'email': user_email}).get('Item')

    appointments_table = get_appointments_table()
    response = appointments_table.scan(
        FilterExpression=Attr('patient').eq(user_email)
    )
    appointments = response.get('Items', [])

    return render_template('patient_dashboard.html', name=user['name'], appointments=appointments)

@app.route('/doctor_dashboard')
@login_required(role='doctor')
def doctor_dashboard():
    user_email = session['user']
    table = get_users_table()
    user = table.get_item(Key={'email': user_email}).get('Item')

    appointments_table = get_appointments_table()
    response = appointments_table.scan(
        FilterExpression=Attr('doctor').eq(user_email)
    )
    appointments = response.get('Items', [])

    return render_template('doctor_dashboard.html', name=user['name'], appointments=appointments)

@app.route('/book_appointment', methods=['GET', 'POST'])
@login_required(role='patient')
def book_appointment():
    if request.method == 'POST':
        doctor_email = request.form['doctor']
        date = request.form['date']
        time = request.form['time']

        appointment_id = str(uuid.uuid4())
        appointments_table = get_appointments_table()
        appointments_table.put_item(Item={
            'AppointmentID': appointment_id,
            'patient': session['user'],
            'doctor': doctor_email,
            'date': date,
            'time': time,
            'status': 'Booked'
        })

        flash('Appointment booked.', 'success')
        return redirect(url_for('patient_dashboard'))

    return render_template('book_appointment.html')

if _name_ == '_main_':
    app.run(debug=True)
