from flask import Blueprint, render_template, request, flash, jsonify, redirect, url_for, current_app, send_from_directory, session
from .models import Note, User, UserRole, Doctor, Pharmacist, Patient, Appointment, WorkTime, MedicalRecord, PharmaMessage, Medicine
from . import db
import json
from datetime import datetime, time, timedelta
from dateutil import parser
from werkzeug.security import generate_password_hash
import os
from flask_mail import Message
from . import mail
from functools import wraps
from supabase import create_client
from .supabase_client import supabase

views = Blueprint('views', __name__)

# Custom login_required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash('Please log in to access this page.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper: role_required decorator
def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('user') or 'user' not in session:
                flash('Please log in to access this page.', 'error')
                return redirect(url_for('auth.login'))
            
            user_role = session['user'].get('role')
            if user_role not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('views.home'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@views.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST': 
        note = request.form.get('note')#Gets the note from the HTML 

        if len(note) < 1:
            flash('Note is too short!', category='error') 
        else:
            new_note = Note(data=note, user_id=session['user']['id'])  #providing the schema for the note 
            db.session.add(new_note) #adding the note to the database 
            db.session.commit()
            flash('Note added!', category='success')

    return render_template("home.html", user=session.get('user'))


@views.route('/delete-note', methods=['POST'])
def delete_note():  
    note = json.loads(request.data) # this function expects a JSON from the INDEX.js file 
    noteId = note['noteId']
    note = Note.query.get(noteId)
    if note:
        if note.user_id == session['user']['id']:
            db.session.delete(note)
            db.session.commit()

    return jsonify({})

# --- Admin Dashboard ---
@views.route('/admin')
@login_required
@role_required(UserRole.ADMIN.value)
def admin_dashboard():
    users = User.query.all()
    doctors = Doctor.query.all()
    pharmacists = Pharmacist.query.all()
    return render_template('admin_dashboard.html', users=users, doctors=doctors, pharmacists=pharmacists, user=session.get('user'))

# --- Add Doctor/Pharmacist ---
@views.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
@role_required(UserRole.ADMIN.value)
def add_user():
    if request.method == 'POST':
        try:
            # Get form data
            email = request.form.get('email')
            password = request.form.get('password')
            first_name = request.form.get('first_name')
            last_name = request.form.get('last_name')
            role = request.form.get('role')
            specialty = request.form.get('specialty') if role == UserRole.DOCTOR.value else None

            # Check if email already exists
            if User.query.filter_by(email=email).first():
                flash('Email already exists.', 'error')
                return redirect(url_for('views.add_user'))

            # Create user in Supabase first
            try:
                result = supabase.auth.admin.create_user({
                    "email": email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {
                        "role": role,
                        "first_name": first_name,
                        "last_name": last_name
                    }
                })
                if not result or not hasattr(result, 'user'):
                    raise Exception("Failed to create user in Supabase")
            except Exception as e:
                flash(f'Error creating user in Supabase: {str(e)}', 'error')
                return redirect(url_for('views.add_user'))

            # Create user in local database
            new_user = User(
                email=email,
                password=generate_password_hash(password, method='pbkdf2:sha256'),
                first_name=first_name,
                last_name=last_name,
                role=role
            )
            db.session.add(new_user)
            db.session.commit()

            # Create profile based on role
            if role == UserRole.DOCTOR.value:
                doctor = Doctor(
                    user_id=new_user.id,
                    specialty=specialty
                )
                db.session.add(doctor)
                db.session.commit()

                # Add work times
                i = 0
                while True:
                    day = request.form.get(f'work_times[{i}][day_of_week]')
                    start = request.form.get(f'work_times[{i}][start_time]')
                    end = request.form.get(f'work_times[{i}][end_time]')
                    # Check for 24/7 checkbox (simulate by checking if start==00:00 and end==23:59)
                    is_247 = (start == '00:00' and end == '23:59')
                    if not day or not start or not end:
                        break
                    wt_obj = WorkTime(
                        doctor_id=doctor.id,
                        day_of_week=day,
                        start_time=datetime.strptime('00:00' if is_247 else start, '%H:%M').time(),
                        end_time=datetime.strptime('23:59' if is_247 else end, '%H:%M').time()
                    )
                    db.session.add(wt_obj)
                    i += 1

            elif role == UserRole.PHARMACIST.value:
                pharmacist = Pharmacist(user_id=new_user.id)
                db.session.add(pharmacist)
                db.session.commit()

                # Add work times
                i = 0
                while True:
                    day = request.form.get(f'work_times[{i}][day_of_week]')
                    start = request.form.get(f'work_times[{i}][start_time]')
                    end = request.form.get(f'work_times[{i}][end_time]')
                    is_247 = (start == '00:00' and end == '23:59')
                    if not day or not start or not end:
                        break
                    wt_obj = WorkTime(
                        pharmacist_id=pharmacist.id,
                        day_of_week=day,
                        start_time=datetime.strptime('00:00' if is_247 else start, '%H:%M').time(),
                        end_time=datetime.strptime('23:59' if is_247 else end, '%H:%M').time()
                    )
                    db.session.add(wt_obj)
                    i += 1

            db.session.commit()
            flash(f'{role.capitalize()} added successfully!', 'success')
            return redirect(url_for('views.admin_dashboard'))

        except Exception as e:
            print(f"Error adding user: {str(e)}")
            db.session.rollback()
            flash('Error adding user. Please try again.', 'error')
            return redirect(url_for('views.add_user'))

    return render_template('add_user.html', user=session.get('user'))

# --- Appointment Booking ---
@views.route('/get_available_slots', methods=['GET'])
@login_required
def get_available_slots():
    doctor_id = request.args.get('doctor_id')
    date_str = request.args.get('date')
    
    if not doctor_id or not date_str:
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        date = parser.parse(date_str).date()
        doctor = Doctor.query.get_or_404(doctor_id)
        
        # Get the day of week for the selected date
        day_of_week = date.strftime('%A')
        
        # Fix: Match day_of_week case-insensitively
        work_times = WorkTime.query.filter(
            WorkTime.doctor_id == doctor_id,
            db.func.lower(WorkTime.day_of_week) == day_of_week.lower()
        ).all()
        
        if not work_times:
            return jsonify({'slots': []})
        
        # Get existing appointments for the selected date
        existing_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            db.func.date(Appointment.appointment_time) == date
        ).all()
        
        booked_times = {apt.appointment_time.time() for apt in existing_appointments}
        
        # Generate 30-minute slots
        available_slots = []
        for wt in work_times:
            current_time = wt.start_time
            end_time = wt.end_time
            
            while current_time < end_time:
                slot_end = (datetime.combine(date, current_time) + timedelta(minutes=30)).time()
                if slot_end <= end_time and current_time not in booked_times:
                    available_slots.append(current_time.strftime('%H:%M'))
                current_time = slot_end
        
        return jsonify({'slots': sorted(available_slots)})
    
    except Exception as e:
        print(f"Error in get_available_slots: {str(e)}")  # Add debug logging
        return jsonify({'error': str(e)}), 400

@views.route('/appointments/book', methods=['GET', 'POST'])
@login_required
@role_required(UserRole.PATIENT.value)
def book_appointment():
    # Get all doctors with their work times and user information
    doctors = Doctor.query.all()
    doctors_with_schedule = []
    for doctor in doctors:
        if doctor.user:  # Only include if user relationship exists
            work_times = WorkTime.query.filter_by(doctor_id=doctor.id).all()
            schedule = {}
            for wt in work_times:
                day = wt.day_of_week.lower()
                if day not in schedule:
                    schedule[day] = []
                schedule[day].append({
                    'start': wt.start_time.strftime('%H:%M'),
                    'end': wt.end_time.strftime('%H:%M')
                })
            doctors_with_schedule.append({
                'id': doctor.id,
                'name': doctor.user.first_name,
                'specialty': doctor.specialty,
                'schedule': schedule
            })

    if request.method == 'POST':
        try:
            # Get form data
            doctor_id = request.form.get('doctor')
            appointment_type = request.form.get('type')
            date = request.form.get('date')
            reason = request.form.get('reason')

            # Validate required fields (no time field)
            if not all([doctor_id, appointment_type, date]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('views.book_appointment'))

            # Get or create patient
            patient = Patient.query.filter_by(user_id=session['user']['id']).first()
            if not patient:
                patient = Patient(user_id=session['user']['id'])
                db.session.add(patient)
                db.session.commit()

            # Find doctor's work time for the selected day
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
            day_of_week = date_obj.strftime('%A')
            work_times = WorkTime.query.filter(
                WorkTime.doctor_id == doctor_id,
                db.func.lower(WorkTime.day_of_week) == day_of_week.lower()
            ).order_by(WorkTime.start_time).all()

            if not work_times:
                flash('Doctor is not available on the selected day.', 'error')
                return redirect(url_for('views.book_appointment'))

            if len(work_times) > 1:
                flash('Warning: Doctor has multiple work periods on this day. Only the first will be used.', 'warning')

            work_time = work_times[0]

            # Count existing appointments for that doctor on that day
            existing_appointments = Appointment.query.filter(
                Appointment.doctor_id == doctor_id,
                db.func.date(Appointment.appointment_time) == date_obj,
                Appointment.status != 'cancelled'
            ).order_by(Appointment.appointment_time).all()

            slot_number = len(existing_appointments) + 1
            slot_duration = 30  # minutes
            appointment_time = (datetime.combine(date_obj, work_time.start_time) +
                                timedelta(minutes=slot_duration * (slot_number - 1)))

            # Only allow slots that END before or at end_time
            slot_end_time = (appointment_time + timedelta(minutes=slot_duration)).time()
            if slot_end_time > work_time.end_time:
                flash('No more available slots for this day.', 'error')
                return redirect(url_for('views.book_appointment'))

            # Create appointment
            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor_id,
                appointment_time=appointment_time,
                type=appointment_type,
                reason=reason,
                status='scheduled'
            )
            db.session.add(appointment)
            db.session.commit()

            msg = Message(
                subject="Your Appointment Confirmation",
                sender="bookmydoc11@gmail.com",
                recipients=[session['user']['email']]
            )
            msg.body = f"""Hello {session['user'].get('first_name', session['user'].get('email', 'User'))},\n\nYour appointment has been booked successfully!\n\nAppointment Details:\n- Doctor: Dr. {getattr(appointment.doctor.user, 'first_name', '')} {getattr(appointment.doctor.user, 'last_name', '')}\n- Time: {appointment.appointment_time.strftime('%B %d, %Y at %I:%M %p')}\n- Your Appointment Number: {slot_number}\n\nThank you for using BookMyDoc!\n"""
            mail.send(msg)

            flash(f'Appointment booked! Your number is {slot_number}. Please come at {appointment_time.strftime("%I:%M %p")}.', 'success')
            return redirect(url_for('views.view_appointments'))

        except Exception as e:
            print(f"Error in book_appointment: {str(e)}")
            db.session.rollback()
            flash('Error booking appointment. Please try again.', 'error')
            return redirect(url_for('views.book_appointment'))

    return render_template('book_appointment.html', 
                         doctors=doctors_with_schedule, 
                         user=session.get('user'),
                         today_date=datetime.now().strftime('%Y-%m-%d'))

# --- View Appointments ---
@views.route('/appointments')
@login_required
def view_appointments():
    if session['user']['role'] == UserRole.PATIENT.value:
        patient = Patient.query.filter_by(user_id=session['user']['id']).first()
        appointments = patient.appointments if patient else []
    elif session['user']['role'] == UserRole.DOCTOR.value:
        doctor = Doctor.query.filter_by(user_id=session['user']['id']).first()
        appointments = doctor.appointments if doctor else []
    elif session['user']['role'] == UserRole.PHARMACIST.value:
        pharmacist = Pharmacist.query.filter_by(user_id=session['user']['id']).first()
        appointments = pharmacist.appointments if pharmacist else []
    else:
        appointments = []
    return render_template('appointments.html', appointments=appointments, user=session.get('user'))

# --- View Patient Medical Data (Doctors only) ---
@views.route('/patients/<int:patient_id>/medical_data')
@login_required
@role_required(UserRole.DOCTOR.value)
def view_medical_data(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    medical_records = MedicalRecord.query.filter_by(patient_id=patient_id).order_by(MedicalRecord.date.desc()).all()
    
    return render_template('medical_data.html', patient=patient, medical_records=medical_records)

@views.route('/get_doctor_schedule', methods=['GET'])
@login_required
def get_doctor_schedule():
    doctor_id = request.args.get('doctor_id')
    
    if not doctor_id:
        return jsonify({'error': 'Missing doctor_id parameter'}), 400
    
    try:
        doctor = Doctor.query.get_or_404(doctor_id)
        work_times = WorkTime.query.filter_by(doctor_id=doctor_id).all()
        
        # Organize work times by day of week
        schedule = {
            'mon': [], 'tue': [], 'wed': [], 'thu': [], 
            'fri': [], 'sat': [], 'sun': []
        }
        
        for wt in work_times:
            day = wt.day_of_week.lower()[:3]  # Convert to lowercase and get first 3 letters
            if day in schedule:
                schedule[day].append({
                    'start': wt.start_time.strftime('%H:%M'),
                    'end': wt.end_time.strftime('%H:%M')
                })
        
        return jsonify({'schedule': schedule})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@views.route('/appointments/edit/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
@role_required(UserRole.DOCTOR.value)
def edit_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    doctor = Doctor.query.filter_by(user_id=session['user']['id']).first()
    if not doctor or appointment.doctor_id != doctor.id:
        flash('Access denied.', 'error')
        return redirect(url_for('views.view_appointments'))

    if request.method == 'POST':
        try:
            # Update status
            status = request.form.get('status')
            if status in ['scheduled', 'completed', 'cancelled']:
                appointment.status = status
            # Update date/time
            date = request.form.get('date')
            time_slot = request.form.get('time')
            if date and time_slot:
                appointment.appointment_time = datetime.strptime(f"{date} {time_slot}", '%Y-%m-%d %H:%M')
            # Update notes
            notes = request.form.get('notes')
            if notes is not None:
                appointment.reason = notes
            db.session.commit()
            flash('Appointment updated successfully!', 'success')
            return redirect(url_for('views.view_appointments'))
        except Exception as e:
            db.session.rollback()
            flash('Error updating appointment.', 'error')
            return redirect(url_for('views.edit_appointment', appointment_id=appointment_id))

    # Pre-fill form with current values
    return render_template('edit_appointment.html', appointment=appointment, user=session.get('user'))

@views.route('/medical-data/add/<int:patient_id>', methods=['GET', 'POST'])
@login_required
def add_medical_record(patient_id):
    if session['user']['role'] != 'doctor':
        flash('Only doctors can add medical records.', 'error')
        return redirect(url_for('views.home'))
    
    patient = Patient.query.get_or_404(patient_id)
    doctor = Doctor.query.filter_by(user_id=session['user']['id']).first()
    
    if request.method == 'POST':
        title = request.form.get('title')
        type = request.form.get('type')
        description = request.form.get('description')
        prescription = request.form.get('prescription')
        
        new_record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=doctor.id,
            title=title,
            type=type,
            description=description,
            prescription=prescription
        )
        
        db.session.add(new_record)
        db.session.commit()
        
        flash('Medical record added successfully!', 'success')
        return redirect(url_for('views.view_medical_data', patient_id=patient_id))
    
    return render_template('add_medical_record.html', patient=patient)

@views.route('/medical-data/edit/<int:record_id>', methods=['GET', 'POST'])
@login_required
def edit_medical_record(record_id):
    record = MedicalRecord.query.get_or_404(record_id)
    
    # Check if user has permission to edit (either doctor who created it or the patient)
    if not (session['user']['role'] == 'doctor' and record.doctor.user.id == session['user']['id']) and \
       not (session['user']['role'] == 'patient' and record.patient.user.id == session['user']['id']):
        flash('You do not have permission to edit this record.', 'error')
        return redirect(url_for('views.home'))

    if request.method == 'POST':
        record.title = request.form.get('title')
        record.type = request.form.get('type')
        record.description = request.form.get('description')
        record.prescription = request.form.get('prescription')
        
        db.session.commit()
        flash('Medical record updated successfully!', 'success')
        
        if session['user']['role'] == 'patient':
            return redirect(url_for('views.view_profile'))
        return redirect(url_for('views.view_medical_data', patient_id=record.patient_id))

    return render_template("edit_medical_record.html", record=record, user=session.get('user'))

@views.route('/medical-data/delete/<int:record_id>', methods=['POST'])
@login_required
def delete_medical_record(record_id):
    if session['user']['role'] != 'doctor':
        flash('Only doctors can delete medical records.', 'error')
        return redirect(url_for('views.home'))
    
    record = MedicalRecord.query.get_or_404(record_id)
    doctor = Doctor.query.filter_by(user_id=session['user']['id']).first()
    
    if record.doctor_id != doctor.id:
        flash('You can only delete your own medical records.', 'error')
        return redirect(url_for('views.home'))
    
    patient_id = record.patient_id
    db.session.delete(record)
    db.session.commit()
    
    flash('Medical record deleted successfully!', 'success')
    return redirect(url_for('views.view_medical_data', patient_id=patient_id))

@views.route('/profile')
@login_required
def view_profile():
    if session['user']['role'] == 'patient':
        patient = Patient.query.filter_by(user_id=session['user']['id']).first()
        if not patient:
            # Automatically create a Patient profile for this user
            patient = Patient(user_id=session['user']['id'])
            db.session.add(patient)
            db.session.commit()
        # Get patient's appointments
        appointments = Appointment.query.filter_by(patient_id=patient.id).order_by(Appointment.appointment_time.desc()).all()
        # Get patient's medical records
        medical_records = MedicalRecord.query.filter_by(patient_id=patient.id).order_by(MedicalRecord.date.desc()).all()
        return render_template('patient_profile.html', 
                             patient=patient, 
                             appointments=appointments,
                             medical_records=medical_records)
    else:
        flash('Access denied.', 'error')
        return redirect(url_for('views.home'))

def allowed_file(filename):
    allowed = current_app.config['ALLOWED_EXTENSIONS']
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

def save_uploaded_file(file):
    if file and allowed_file(file.filename):
        filename = file.filename
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        # Ensure unique filename
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filename = f"{base}_{counter}{ext}"
            filepath = os.path.join(upload_folder, filename)
            counter += 1
        file.save(filepath)
        return filepath
    return None

@views.route('/pharma-messages', methods=['GET', 'POST'])
@login_required
@role_required(UserRole.PATIENT.value)
def pharma_messages():
    # Get all pharmacists
    pharmacists = Pharmacist.query.all()
    pharmacist_id = request.args.get('pharmacist_id')
    selected_pharmacist = None
    messages = []

    if pharmacist_id:
        selected_pharmacist = Pharmacist.query.get(int(pharmacist_id))
        if selected_pharmacist:
            # Get conversation (ordered by timestamp)
            messages = PharmaMessage.query.filter(
                ((PharmaMessage.sender_id == session['user']['id']) & (PharmaMessage.receiver_id == selected_pharmacist.user_id)) |
                ((PharmaMessage.sender_id == selected_pharmacist.user_id) & (PharmaMessage.receiver_id == session['user']['id']))
            ).order_by(PharmaMessage.timestamp).all()
            # Mark all unread messages addressed to the patient as read
            unread_msgs = [m for m in messages if m.receiver_id == session['user']['id'] and not m.is_read]
            for m in unread_msgs:
                m.is_read = True
            if unread_msgs:
                db.session.commit()

    if request.method == 'POST' and selected_pharmacist:
        content = request.form.get('content')
        file = request.files.get('file')
        file_path = None
        if file and file.filename:
            file_path = save_uploaded_file(file)
        msg = PharmaMessage(
            sender_id=session['user']['id'],
            receiver_id=selected_pharmacist.user_id,
            content=content,
            is_from_patient=True,
            file_path=file_path
        )
        db.session.add(msg)
        db.session.commit()
        flash('Message sent!', 'success')
        return redirect(url_for('views.pharma_messages', pharmacist_id=selected_pharmacist.id))

    return render_template('pharma_messages_patient.html', pharmacists=pharmacists, selected_pharmacist=selected_pharmacist, messages=messages)

@views.route('/pharma-messages-pharma', methods=['GET', 'POST'])
@login_required
@role_required(UserRole.PHARMACIST.value)
def pharma_messages_pharma():
    # Get all patients who have messaged this pharmacist
    pharmacist = Pharmacist.query.filter_by(user_id=session['user']['id']).first()
    # Find all unique patient user_ids who have messaged this pharmacist
    patient_ids = db.session.query(PharmaMessage.sender_id).filter(
        PharmaMessage.receiver_id == session['user']['id'],
        PharmaMessage.is_from_patient == True
    ).distinct().all()
    patient_ids = [pid[0] for pid in patient_ids]
    patients = User.query.filter(User.id.in_(patient_ids)).all()
    patient_id = request.args.get('patient_id')
    selected_patient = None
    messages = []

    if patient_id:
        selected_patient = User.query.get(int(patient_id))
        if selected_patient:
            # Get conversation (ordered by timestamp)
            messages = PharmaMessage.query.filter(
                ((PharmaMessage.sender_id == session['user']['id']) & (PharmaMessage.receiver_id == selected_patient.id)) |
                ((PharmaMessage.sender_id == selected_patient.id) & (PharmaMessage.receiver_id == session['user']['id']))
            ).order_by(PharmaMessage.timestamp).all()
            # Mark all unread messages addressed to the pharmacist as read
            unread_msgs = [m for m in messages if m.receiver_id == session['user']['id'] and not m.is_read]
            for m in unread_msgs:
                m.is_read = True
            if unread_msgs:
                db.session.commit()

    if request.method == 'POST' and selected_patient:
        content = request.form.get('content')
        file = request.files.get('file')
        file_path = None
        if file and file.filename:
            file_path = save_uploaded_file(file)
        msg = PharmaMessage(
            sender_id=session['user']['id'],
            receiver_id=selected_patient.id,
            content=content,
            is_from_patient=False,
            file_path=file_path
        )
        db.session.add(msg)
        db.session.commit()
        flash('Message sent!', 'success')
        return redirect(url_for('views.pharma_messages_pharma', patient_id=selected_patient.id))

    return render_template('pharma_messages_pharma.html', patients=patients, selected_patient=selected_patient, messages=messages)

@views.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@views.route('/api/medicine', methods=['POST'])
@login_required
def add_medicine():
    if session['user']['role'] != 'patient':
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.form
    medicine = Medicine(
        patient_id=session['user']['patient'].id,
        name=data.get('name'),
        notes=data.get('notes'),
        is_active=True,
        start_date=datetime.now()
    )
    db.session.add(medicine)
    db.session.commit()
    return jsonify({'message': 'Medicine added successfully'})

@views.route('/api/medicine/<int:medicine_id>', methods=['GET'])
@login_required
def get_medicine(medicine_id):
    medicine = Medicine.query.get_or_404(medicine_id)
    if medicine.patient_id != session['user']['patient'].id:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify({
        'id': medicine.id,
        'name': medicine.name,
        'notes': medicine.notes,
        'is_active': medicine.is_active,
        'start_date': medicine.start_date.strftime('%Y-%m-%d'),
        'end_date': medicine.end_date.strftime('%Y-%m-%d') if medicine.end_date else None
    })

@views.route('/api/medicine/<int:medicine_id>', methods=['PUT'])
@login_required
def update_medicine(medicine_id):
    medicine = Medicine.query.get_or_404(medicine_id)
    if medicine.patient_id != session['user']['patient'].id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.form
    medicine.name = data.get('name')
    medicine.notes = data.get('notes')
    db.session.commit()
    return jsonify({'message': 'Medicine updated successfully'})

@views.route('/api/medicine/<int:medicine_id>/archive', methods=['POST'])
@login_required
def archive_medicine(medicine_id):
    medicine = Medicine.query.get_or_404(medicine_id)
    if medicine.patient_id != session['user']['patient'].id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    medicine.is_active = False
    medicine.end_date = datetime.now()
    db.session.commit()
    return jsonify({'message': 'Medicine archived successfully'})

@views.route('/api/medicine/<int:medicine_id>/reactivate', methods=['POST'])
@login_required
def reactivate_medicine(medicine_id):
    medicine = Medicine.query.get_or_404(medicine_id)
    if medicine.patient_id != session['user']['patient'].id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    medicine.is_active = True
    medicine.end_date = None
    db.session.commit()
    return jsonify({'message': 'Medicine reactivated successfully'})

@views.route('/admin/delete_doctor/<int:doctor_id>', methods=['POST'])
@login_required
def delete_doctor(doctor_id):
    if not session.get('user') or session['user'].get('role') != 'admin':
        if request.is_json:
            return jsonify({'success': False, 'message': 'Access denied.'}), 403
        flash('Access denied.', 'error')
        return redirect(url_for('views.admin_dashboard'))
    doctor = Doctor.query.get_or_404(doctor_id)
    user = doctor.user
    db.session.delete(doctor)
    if user:
        db.session.delete(user)
    db.session.commit()
    msg = 'Doctor and related user deleted successfully.'
    if request.is_json:
        return jsonify({'success': True, 'message': msg})
    flash(msg, 'success')
    return redirect(url_for('views.admin_dashboard'))

@views.route('/admin/delete_patient/<int:patient_id>', methods=['POST'])
@login_required
def delete_patient(patient_id):
    if not session.get('user') or session['user'].get('role') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('views.admin_dashboard'))
    patient = Patient.query.get_or_404(patient_id)
    db.session.delete(patient)
    db.session.commit()
    flash('Patient deleted successfully.', 'success')
    return redirect(url_for('views.admin_dashboard'))

@views.route('/admin/delete_pharmacist/<int:pharmacist_id>', methods=['POST'])
@login_required
def delete_pharmacist(pharmacist_id):
    if not session.get('user') or session['user'].get('role') != 'admin':
        if request.is_json:
            return jsonify({'success': False, 'message': 'Access denied.'}), 403
        flash('Access denied.', 'error')
        return redirect(url_for('views.admin_dashboard'))
    pharmacist = Pharmacist.query.get_or_404(pharmacist_id)
    user = pharmacist.user
    db.session.delete(pharmacist)
    if user:
        db.session.delete(user)
    db.session.commit()
    msg = 'Pharmacist and related user deleted successfully.'
    if request.is_json:
        return jsonify({'success': True, 'message': msg})
    flash(msg, 'success')
    return redirect(url_for('views.admin_dashboard'))

@views.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not session.get('user') or session['user'].get('role') != 'admin':
        flash('Access denied.', 'error')
        return redirect(url_for('views.admin_dashboard'))
    user = User.query.get_or_404(user_id)
    email = user.email
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('views.admin_dashboard'))

@views.route('/appointments/cancel/<int:appointment_id>', methods=['POST'])
@login_required
@role_required(UserRole.PATIENT.value)
def cancel_appointment(appointment_id):
    appointment = Appointment.query.get_or_404(appointment_id)
    patient = Patient.query.filter_by(user_id=session['user']['id']).first()
    if not patient or appointment.patient_id != patient.id:
        flash('You do not have permission to cancel this appointment.', 'error')
        return redirect(url_for('views.view_appointments'))
    if appointment.status != 'scheduled':
        flash('Only scheduled appointments can be cancelled.', 'error')
        return redirect(url_for('views.view_appointments'))
    appointment.status = 'cancelled'
    db.session.commit()
    flash('Appointment cancelled successfully.', 'success')
    return redirect(url_for('views.view_appointments'))
