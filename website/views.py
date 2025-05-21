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
            clinic_address = request.form.get('clinic_address') if role == UserRole.DOCTOR.value else None
            phone_number = request.form.get('phone_number') if role == UserRole.DOCTOR.value else None
            certification = request.form.get('certification') if role == UserRole.DOCTOR.value else None

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
                    specialty=specialty,
                    clinic_address=clinic_address,
                    phone_number=phone_number,
                    certification=certification
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
    """
    Returns available 30-min slots for a doctor on a given date.
    Only returns slots that are not already booked.
    """
    doctor_id = request.args.get('doctor_id')
    date_str = request.args.get('date')
    if not doctor_id or not date_str:
        return jsonify({'error': 'Missing required parameters'}), 400
    try:
        doctor_id = int(doctor_id)
        date = parser.parse(date_str).date()
        day_of_week = date.strftime('%A')
        # Find all work times for this doctor on this day
        work_times = WorkTime.query.filter(
            WorkTime.doctor_id == doctor_id,
            db.func.lower(WorkTime.day_of_week) == day_of_week.lower()
        ).all()
        if not work_times:
            return jsonify({'slots': [], 'message': 'Doctor is not available on this day.'})
        # Get all booked times for this doctor on this date
        existing_appointments = Appointment.query.filter(
            Appointment.doctor_id == doctor_id,
            db.func.date(Appointment.appointment_time) == date,
            Appointment.status != 'cancelled'
        ).all()
        booked_times = {apt.appointment_time.time() for apt in existing_appointments}
        # Generate 30-min slots for each work period
        available_slots = []
        for wt in work_times:
            current_dt = datetime.combine(date, wt.start_time)
            end_dt = datetime.combine(date, wt.end_time)
            while current_dt < end_dt:
                slot_time = current_dt.time()
                if slot_time not in booked_times:
                    available_slots.append(slot_time.strftime('%H:%M'))
                current_dt += timedelta(minutes=30)
        if not available_slots:
            return jsonify({'slots': [], 'message': 'All time slots for this day are booked.'})
        return jsonify({'slots': sorted(available_slots)})
    except Exception as e:
        print(f"[ERROR] get_available_slots: {str(e)}")
        return jsonify({'error': str(e)}), 400

@views.route('/appointments/book', methods=['GET', 'POST'])
@login_required
@role_required(UserRole.PATIENT.value)
def book_appointment():
    """
    Booking page: GET shows form, POST books appointment if slot is available.
    """
    # Prepare doctor list with schedule for frontend
    doctors = Doctor.query.all()
    doctors_with_schedule = []
    for doctor in doctors:
        if doctor.user:
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
                'name': f"{doctor.user.first_name} {doctor.user.last_name}",
                'specialty': doctor.specialty,
                'schedule': schedule
            })
    if request.method == 'POST':
        try:
            doctor_id = int(request.form.get('doctor'))
            appointment_type = request.form.get('type')
            date = request.form.get('date')
            reason = request.form.get('reason')
            selected_time = request.form.get('selected_time') or request.form.get('time')
            if not all([doctor_id, appointment_type, date, reason, selected_time]):
                flash('Please fill in all required fields.', 'error')
                return redirect(url_for('views.book_appointment'))
            # Check if the selected time slot is still available
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
            appointment_datetime = datetime.strptime(f"{date} {selected_time}", '%Y-%m-%d %H:%M')
            # Check for double booking
            existing = Appointment.query.filter_by(doctor_id=doctor_id, appointment_time=appointment_datetime, status='scheduled').first()
            if existing:
                flash('This time slot is already booked. Please select another slot.', 'error')
                return redirect(url_for('views.book_appointment'))
            # Get or create patient
            patient = Patient.query.filter_by(user_id=session['user']['id']).first()
            if not patient:
                patient = Patient(user_id=session['user']['id'])
                db.session.add(patient)
                db.session.commit()
            # Book appointment
            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor_id,
                appointment_time=appointment_datetime,
                type=appointment_type,
                reason=reason,
                status='scheduled'
            )
            db.session.add(appointment)
            db.session.commit()
            flash('Appointment booked successfully!', 'success')
            return redirect(url_for('views.view_appointments'))
        except Exception as e:
            print(f"[ERROR] book_appointment: {str(e)}")
            db.session.rollback()
            flash('Error booking appointment. Please try again. ' + str(e), 'error')
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
            'monday': [], 'tuesday': [], 'wednesday': [], 'thursday': [], 
            'friday': [], 'saturday': [], 'sunday': []
        }
        
        for wt in work_times:
            day = wt.day_of_week.lower()  # Convert to lowercase
            if day in schedule:
                schedule[day].append({
                    'start': wt.start_time.strftime('%H:%M'),
                    'end': wt.end_time.strftime('%H:%M')
                })
        
        return jsonify({'schedule': schedule})
    
    except Exception as e:
        print(f"[ERROR] get_doctor_schedule: {str(e)}")
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
    if session['user']['role'] not in ['doctor', 'pharmacist']:
        flash('Only doctors and pharmacists can add medical records.', 'error')
        return redirect(url_for('views.home'))
    
    patient = Patient.query.get_or_404(patient_id)
    doctor = Doctor.query.filter_by(user_id=session['user']['id']).first() if session['user']['role'] == 'doctor' else None
    pharmacist = Pharmacist.query.filter_by(user_id=session['user']['id']).first() if session['user']['role'] == 'pharmacist' else None
    
    if request.method == 'POST':
        title = request.form.get('title')
        type = request.form.get('type')
        description = request.form.get('description')
        prescription = request.form.get('prescription')
        
        new_record = MedicalRecord(
            patient_id=patient_id,
            doctor_id=doctor.id if doctor else None,
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
    
    # Check if user has permission to edit (doctor who created it or pharmacist)
    if not (
        (session['user']['role'] == 'doctor' and record.doctor and record.doctor.user.id == session['user']['id']) or
        (session['user']['role'] == 'pharmacist')
    ):
        flash('You do not have permission to edit this record.', 'error')
        return redirect(url_for('views.home'))

    if request.method == 'POST':
        record.title = request.form.get('title')
        record.type = request.form.get('type')
        record.description = request.form.get('description')
        record.prescription = request.form.get('prescription')
        
        db.session.commit()
        flash('Medical record updated successfully!', 'success')
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
        if not content:
            flash('Message cannot be empty.', 'error')
            return redirect(url_for('views.pharma_messages', pharmacist_id=selected_pharmacist.id))
            
        file = request.files.get('file')
        file_path = None
        if file and file.filename:
            file_path = save_uploaded_file(file)
        # Debug print for sender and receiver IDs
        print("[DEBUG] Patient sending message: sender_id =", session['user']['id'], "receiver_id =", selected_pharmacist.user_id)
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

    # DEBUG: Print patient_ids and patients
    print("[DEBUG] Pharmacist user_id:", session['user']['id'])
    print("[DEBUG] Patient IDs who messaged:", patient_ids)
    print("[DEBUG] Patients found:", [f'{p.first_name} {p.last_name} ({p.email})' for p in patients])

    # Fallback for testing: show all patients if none found
    if not patients:
        patients = User.query.filter_by(role='patient').all()
        print("Fallback: All patients in DB:", [f'{p.first_name} {p.last_name} ({p.email})' for p in patients])
        print("Total fallback patients:", len(patients))

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
        if not content:
            flash('Message cannot be empty.', 'error')
            return redirect(url_for('views.pharma_messages_pharma', patient_id=selected_patient.id))
            
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

@views.route('/debug_worktimes/<int:doctor_id>')
def debug_worktimes(doctor_id):
    work_times = WorkTime.query.filter_by(doctor_id=doctor_id).all()
    if not work_times:
        return f"No work times found for doctor_id {doctor_id}"
    return '<br>'.join([f"{wt.day_of_week}: {wt.start_time} - {wt.end_time}" for wt in work_times])

@views.route('/debug_doctors')
def debug_doctors():
    doctors = Doctor.query.all()
    return '<br>'.join([f"ID: {doc.id}, Name: {doc.user.first_name} {doc.user.last_name}, Email: {doc.user.email}" for doc in doctors if doc.user])

@views.route('/admin/get_doctor/<int:doctor_id>')
@login_required
@role_required(UserRole.ADMIN.value)
def get_doctor(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    user = doctor.user
    work_times = WorkTime.query.filter_by(doctor_id=doctor.id).all()
    return jsonify({
        'id': doctor.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'specialty': doctor.specialty,
        'clinic_address': doctor.clinic_address,
        'phone_number': doctor.phone_number,
        'certification': doctor.certification,
        'work_times': [
            {
                'id': wt.id,
                'day_of_week': wt.day_of_week,
                'start_time': wt.start_time.strftime('%H:%M'),
                'end_time': wt.end_time.strftime('%H:%M')
            } for wt in work_times
        ]
    })

@views.route('/admin/update_doctor', methods=['POST'])
@login_required
@role_required(UserRole.ADMIN.value)
def update_doctor():
    doctor_id = request.form.get('doctor_id')
    doctor = Doctor.query.get_or_404(doctor_id)
    user = doctor.user

    # Update user fields
    user.first_name = request.form.get('first_name')
    user.last_name = request.form.get('last_name')
    user.email = request.form.get('email')

    # Update doctor fields
    doctor.specialty = request.form.get('specialty')
    doctor.clinic_address = request.form.get('clinic_address')
    doctor.phone_number = request.form.get('phone_number')
    doctor.certification = request.form.get('certification')

    # Update work times
    work_times_json = request.form.get('work_times_json')
    if work_times_json is not None:
        import json
        from .models import WorkTime
        try:
            new_work_times = json.loads(work_times_json)
            if not new_work_times:
                return jsonify({'success': False, 'error': 'At least one work time slot is required.'})
            # Remove old work times
            WorkTime.query.filter_by(doctor_id=doctor.id).delete()
            # Add new work times
            for wt in new_work_times:
                start_time = datetime.strptime(wt['start_time'], '%H:%M').time()
                end_time = datetime.strptime(wt['end_time'], '%H:%M').time()
                work_time = WorkTime(
                    doctor_id=doctor.id,
                    day_of_week=wt['day_of_week'],
                    start_time=start_time,
                    end_time=end_time
                )
                db.session.add(work_time)
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)})

    try:
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@views.route('/doctor/profile', methods=['GET', 'POST'])
@login_required
@role_required(UserRole.DOCTOR.value)
def doctor_own_profile():
    doctor = Doctor.query.filter_by(user_id=session['user']['id']).first()
    if not doctor:
        flash('Doctor profile not found.', 'error')
        return redirect(url_for('views.home'))
    if request.method == 'POST':
        try:
            # Update doctor info from form fields
            doctor.user.first_name = request.form.get('first_name')
            doctor.user.last_name = request.form.get('last_name')
            doctor.user.email = request.form.get('email')
            doctor.specialty = request.form.get('specialty')
            doctor.clinic_address = request.form.get('clinic_address')
            doctor.phone_number = request.form.get('phone_number')
            doctor.certification = request.form.get('certification')
            # Update work schedule
            # Remove old work times
            WorkTime.query.filter_by(doctor_id=doctor.id).delete()
            db.session.flush()  # Ensure deletion before adding new
            # Add new work times from form
            work_time_indices = set()
            for key in request.form:
                if key.startswith('work_times[') and key.endswith('][day_of_week]'):
                    idx = key.split('[')[1].split(']')[0]
                    work_time_indices.add(idx)
            for idx in work_time_indices:
                day = request.form.get(f'work_times[{idx}][day_of_week]')
                start = request.form.get(f'work_times[{idx}][start_time]')
                end = request.form.get(f'work_times[{idx}][end_time]')
                if day and start and end:
                    wt = WorkTime(
                        doctor_id=doctor.id,
                        day_of_week=day,
                        start_time=datetime.strptime(start, '%H:%M').time(),
                        end_time=datetime.strptime(end, '%H:%M').time()
                    )
                    db.session.add(wt)
            db.session.commit()
            flash('Profile updated successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
        return redirect(url_for('views.doctor_own_profile'))
    return render_template('doctor_profile.html', doctor=doctor, can_edit=True)

@views.route('/doctor/<int:doctor_id>')
@login_required
def view_doctor_profile(doctor_id):
    doctor = Doctor.query.get_or_404(doctor_id)
    return render_template('doctor_profile.html', doctor=doctor)
