from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from .supabase_client import supabase
from flask_login import login_user, logout_user, login_required, current_user
from .models import User, Doctor, UserRole
from . import db

auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            result = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password,
            })
            if hasattr(result, 'session') and result.session:
                session['supabase_token'] = result.session.access_token
                # Always sync or fetch the local User record
                user = User.query.filter_by(email=email).first()
                if not user:
                    # If not found, create a new local user (for patients, default role)
                    first_name = result.user.user_metadata.get('first_name', '') if hasattr(result.user, 'user_metadata') else ''
                    last_name = result.user.user_metadata.get('last_name', '') if hasattr(result.user, 'user_metadata') else ''
                    role = result.user.user_metadata.get('role', 'patient')
                    user = User(
                        email=email,
                        password='',
                        first_name=first_name,
                        last_name=last_name,
                        role=role
                    )
                    db.session.add(user)
                    db.session.commit()
                # Set session['user']['id'] to local User.id (integer)
                session['user'] = {
                    'id': user.id,
                    'email': user.email,
                    'role': str(user.role).lower() if user.role else ''
                }
                print('Session user:', session['user'])
                # Force admin role for admin@gmail.com
                if session['user']['email'] == 'admin@gmail.com':
                    session['user']['role'] = 'admin'
                flash('Logged in successfully!', 'success')
                if session['user']['email'] == 'admin@gmail.com':
                    return redirect(url_for('views.admin_dashboard'))
                if session['user']['role'] == 'doctor':
                    # Sync User record from Supabase (already done above)
                    first_name = result.user.user_metadata.get('first_name', '') if hasattr(result.user, 'user_metadata') else ''
                    last_name = result.user.user_metadata.get('last_name', '') if hasattr(result.user, 'user_metadata') else ''
                    updated = False
                    if user.first_name != first_name:
                        user.first_name = first_name
                        updated = True
                    if user.last_name != last_name:
                        user.last_name = last_name
                        updated = True
                    if updated:
                        db.session.commit()
                    # Create Doctor profile if needed
                    doctor = Doctor.query.filter_by(user_id=user.id).first()
                    if not doctor:
                        doctor = Doctor(user_id=user.id, specialty='General')
                        db.session.add(doctor)
                        db.session.commit()
                    return redirect(url_for('views.view_appointments'))
                return redirect(url_for('views.home'))
            else:
                flash('Login failed. Please check your credentials.', 'error')
        except Exception as e:
            flash(str(e), 'error')
    return render_template("login.html", user=None)

@auth.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'success')
    return redirect(url_for('auth.login'))

@auth.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password1')
        role = 'patient'  # Force all sign-ups to be patient
        first_name = request.form.get('firstName')
        last_name = request.form.get('lastName')
        try:
            result = supabase.auth.sign_up({
                "email": email,
                "password": password,
                "options": {
                    "data": {
                        "role": role,
                        "first_name": first_name,
                        "last_name": last_name
                    }
                }
            })
            if hasattr(result, 'user') and result.user:
                flash('Account created! Please check your email to confirm.', 'success')
                return redirect(url_for('auth.login'))
            else:
                flash('Registration failed. Please try again.', 'error')
        except Exception as e:
            flash(str(e), 'error')
    return render_template("sign_up.html", user=None)
