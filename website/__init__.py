from flask import Flask, session
from flask_sqlalchemy import SQLAlchemy
from os import path
from flask_mail import Mail

db = SQLAlchemy()
DB_NAME = "database.db"
mail = Mail()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'hjshjhdjah kjshkjdhjs'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_NAME}'
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'bookmydoc11@gmail.com'
    app.config['MAIL_PASSWORD'] = 'sjalamjygtofbrjh'
    db.init_app(app)
    mail.init_app(app)

    from .views import views
    from .auth import auth

    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/')

    from .models import User, Note, Patient, Doctor, Pharmacist, Appointment, WorkTime, MedicalRecord, PharmaMessage, Medicine

    create_database(app)

    @app.context_processor
    def inject_user():
        return dict(user=session.get('user'))

    return app

def create_database(app):
    if not path.exists('website/' + DB_NAME):
        with app.app_context():
            db.create_all()
        print('Created Database!')
