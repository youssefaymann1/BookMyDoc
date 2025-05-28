from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from enum import Enum


class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.String(10000))
    date = db.Column(db.DateTime(timezone=True), default=func.now())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


class UserRole(Enum):
    ADMIN = 'admin'
    DOCTOR = 'doctor'
    PATIENT = 'patient'
    PHARMACIST = 'pharmacist'


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    first_name = db.Column(db.String(150))
    last_name = db.Column(db.String(150))
    role = db.Column(db.String(50), default=UserRole.PATIENT.value)
    photo_path = db.Column(db.String(255), nullable=True)  # New: profile photo
    id_photo_path = db.Column(db.String(255), nullable=True)  # National ID or passport photo
    notes = db.relationship('Note')
    doctor_profile = db.relationship('Doctor', uselist=False, back_populates='user')
    pharmacist_profile = db.relationship('Pharmacist', uselist=False, back_populates='user')
    patient_profile = db.relationship('Patient', uselist=False, back_populates='user')


class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    specialty = db.Column(db.String(150))
    clinic_address = db.Column(db.String(255))  # New: Clinic address
    certification = db.Column(db.Text)          # New: Certification
    phone_number = db.Column(db.String(50))     # New: Phone number
    certificate_path = db.Column(db.String(255), nullable=True)  # Certificate file path
    user = db.relationship('User', back_populates='doctor_profile')
    work_times = db.relationship('WorkTime', back_populates='doctor')
    appointments = db.relationship('Appointment', back_populates='doctor')


class Pharmacist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', back_populates='pharmacist_profile')
    work_times = db.relationship('WorkTime', back_populates='pharmacist')
    appointments = db.relationship('Appointment', back_populates='pharmacist')
    pharmacy_name = db.Column(db.String(255), nullable=True)  # New: pharmacy name
    certificate_path = db.Column(db.String(255), nullable=True)  # Certificate file path


class Patient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    medical_data = db.Column(db.Text)
    user = db.relationship('User', back_populates='patient_profile')
    appointments = db.relationship('Appointment', back_populates='patient')
    medicines = db.relationship('Medicine', back_populates='patient', order_by='Medicine.start_date.desc()')


class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=True)
    pharmacist_id = db.Column(db.Integer, db.ForeignKey('pharmacist.id'), nullable=True)
    appointment_time = db.Column(db.DateTime(timezone=True))
    type = db.Column(db.String(50))  # consultation, follow-up, checkup, emergency
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='scheduled')  # scheduled, completed, cancelled
    created_at = db.Column(db.DateTime(timezone=True), default=func.now())
    updated_at = db.Column(db.DateTime(timezone=True), default=func.now(), onupdate=func.now())
    
    patient = db.relationship('Patient', back_populates='appointments')
    doctor = db.relationship('Doctor', back_populates='appointments')
    pharmacist = db.relationship('Pharmacist', back_populates='appointments')


class WorkTime(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=True)
    pharmacist_id = db.Column(db.Integer, db.ForeignKey('pharmacist.id'), nullable=True)
    day_of_week = db.Column(db.String(20))
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    doctor = db.relationship('Doctor', back_populates='work_times')
    pharmacist = db.relationship('Pharmacist', back_populates='work_times')


class MedicalRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'))
    title = db.Column(db.String(255))
    type = db.Column(db.String(50))  # diagnosis, prescription, test, etc.
    description = db.Column(db.Text)
    prescription = db.Column(db.Text)
    date = db.Column(db.DateTime(timezone=True), default=func.now())
    file_path = db.Column(db.String(255), nullable=True)  # New: file upload support

    patient = db.relationship('Patient', back_populates='medical_records')
    doctor = db.relationship('Doctor', back_populates='medical_records')

# Add the relationships to Doctor and Patient after MedicalRecord is defined
Doctor.medical_records = db.relationship('MedicalRecord', back_populates='doctor')
Patient.medical_records = db.relationship('MedicalRecord', back_populates='patient')

class PharmaMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime(timezone=True), default=func.now())
    is_from_patient = db.Column(db.Boolean, default=True)
    file_path = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_pharma_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_pharma_messages')

class Medicine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    name = db.Column(db.String(255), nullable=False)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    start_date = db.Column(db.DateTime(timezone=True), default=func.now())
    end_date = db.Column(db.DateTime(timezone=True), nullable=True)
    
    patient = db.relationship('Patient', back_populates='medicines')

# Add the relationship to Patient after Medicine is defined
Patient.medicines = db.relationship('Medicine', back_populates='patient', order_by='Medicine.start_date.desc()')

class DoctorAppointmentPrice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    appointment_type = db.Column(db.String(50), nullable=False)  # consultation, follow-up, checkup, emergency
    price = db.Column(db.Float, nullable=False, default=0.0)
    doctor = db.relationship('Doctor', backref='appointment_prices')
    __table_args__ = (db.UniqueConstraint('doctor_id', 'appointment_type', name='_doctor_type_uc'),)
