from website import db, create_app
from website.models import User, UserRole, Patient, Doctor, Pharmacist
from werkzeug.security import generate_password_hash
from flask_migrate import Migrate

app = create_app()
migrate = Migrate(app, db)

if __name__ == '__main__':
    with app.app_context():
        # The following create_all is not needed with migrations, 
        # but leaving it doesn't harm anything for now.
        db.create_all()
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
    app.run(debug=True)
