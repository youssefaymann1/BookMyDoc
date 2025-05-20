from website import db, create_app
from website.models import User, UserRole, Patient, Doctor, Pharmacist
from werkzeug.security import generate_password_hash

from flask_login import current_user
from flask import Flask
app = Flask(__name__)

# باقي الكود...

app = create_app()

# Add context processor to make user available to all templates
@app.context_processor
def inject_user():
    return dict(user=current_user)

# Create tables if they don't exist
with app.app_context():
    db.create_all()  # This will only create tables if they don't exist
    
    # Create admin user if not exists
    admin_email = 'admin@gmail.com'
    admin_password = 'admin123'
    if not User.query.filter_by(email=admin_email).first():
        admin_user = User(
            email=admin_email,
            password=generate_password_hash(admin_password, method='pbkdf2:sha256'),
            first_name='Admin',
            last_name='User',
            role=UserRole.ADMIN.value
        )
        db.session.add(admin_user)
        db.session.commit()
        print('Admin user created!')
    else:
        print('Admin user already exists.')

if __name__ == '__main__':
    app.run(debug=True)
