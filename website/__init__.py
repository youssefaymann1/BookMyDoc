from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from os import path
from flask_mail import Mail
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
DB_NAME = "database.db"
mail = Mail()
login_manager = LoginManager()
migrate = Migrate()

@login_manager.user_loader
def load_user(id):
    from .models import User
    return User.query.get(int(id))

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'hjshjhdjah kjshkjdhjs'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'bookmydoc11@gmail.com'
    app.config['MAIL_PASSWORD'] = 'sjalamjygtofbrjh'
    app.config['ALLOWED_EXTENSIONS'] = {'pdf', 'png', 'jpg', 'jpeg', 'gif'}
    app.config['UPLOAD_FOLDER'] = 'website/static/uploads'
    
    # Initialize extensions with the app
    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    from .models import User, Note, Patient, Doctor, Pharmacist, Appointment, WorkTime, MedicalRecord, PharmaMessage, Medicine

    create_database(app)

    @app.context_processor
    def inject_user():
        user = session.get('user')
        unread_pharma_count = 0
        if user:
            from .models import PharmaMessage
            from . import db
            if user['role'] == 'patient':
                unread_pharma_count = db.session.query(PharmaMessage).filter_by(receiver_id=user['id'], is_from_patient=False, is_read=False).count()
            elif user['role'] == 'pharmacist':
                unread_pharma_count = db.session.query(PharmaMessage).filter_by(receiver_id=user['id'], is_from_patient=True, is_read=False).count()
        print('CTX user:', user, 'unread_pharma_count:', unread_pharma_count)
        return dict(user=user, unread_pharma_count=unread_pharma_count)

    return app

def create_database(app):
    if not path.exists('website/' + DB_NAME):
        with app.app_context():
            db.create_all()
        print('Created Database!')
