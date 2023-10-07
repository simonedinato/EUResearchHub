from flask import Blueprint, request, render_template, url_for, redirect, flash, current_app, session
from sqlalchemy import text
from flask_wtf.csrf import CSRFProtect
from app.models.database import db, Researchers, Evaluators
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_login import login_user, logout_user, login_required, current_user
from app.utils.utils import check_email
from shutil import copy
import os
from flask import render_template, request, redirect, url_for, flash, Markup
from markupsafe import escape
from bleach import clean

auth = Blueprint('auth', __name__)


# login route
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email') # email from the form
        password = request.form.get('password') # password from the form
        sanitized_email = clean(email)
        sanitized_password = clean(password)
        usertype = request.form.get('usertype') # type of user that whants to login

        evaluator = Evaluators.query.filter_by(email=sanitized_email).first()
        researcher = Researchers.query.filter_by(email=sanitized_email).first()

        if evaluator and check_password_hash(evaluator.password, sanitized_password):
            login_user(evaluator)
            db.session.close()
            current_app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('EVALUATOR_DATABASE_URI')
            session['user_type'] = 'evaluator'
            return redirect(url_for('views.projects'))
        elif researcher and check_password_hash(researcher.password, sanitized_password):
            login_user(researcher)
            db.session.close()
            current_app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('RESEARCHER_DATABASE_URI')
            session['user_type'] = 'researcher'
            return redirect(url_for('views.projects'))
        else:
            flash('Invalid email or password', 'error')
    return render_template('login.html')


# register route
@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        choice = request.form.get('choice')
        if choice:
            if choice == 'Researcher':
                return render_template('register.html', user='researcher')
            else:
                return render_template('register.html', user='Evaluator')

        name = request.form.get('name') # name from the form
        surname = request.form.get('surname') # surname from the form
        email = request.form.get('email') # email from the form
        password = request.form.get('password') # password from the form
        affiliation = request.form.get('affiliation') # affiliation from the form
        sanitized_name = clean(name)
        sanitized_surname = clean(surname)
        sanitized_email = clean(email)
        sanitized_password = clean(password)


        
        # if the affiliation is not set, the user is an evaluator, otherwise a researcher
        # also check if email is already registerd on other table, error in case
        if affiliation is None:
            user = Evaluators.query.filter_by(email=sanitized_email).first()
            user_other = Researchers.query.filter_by(email=sanitized_email).first()
        else:
            user = Researchers.query.filter_by(email=sanitized_email).first()
            user_other = Evaluators.query.filter_by(email=sanitized_email).first()
            
        if user or user_other:
            flash('Email already registered', category='error')
        elif not check_email(sanitized_email):
            flash('Email format not valid', category='error')
        elif len(password) < 7:
            flash('Password must be 8 characters', category='error')
        else:

            profile_picture = request.files.get('profile_picture')
            if profile_picture and profile_picture.filename != '':
                current_directory = os.path.dirname(os.path.realpath(__file__))
                current_app.config['UPLOAD_FOLDER'] = os.path.join(current_directory,
                                                                   '../static/uploads/profile_images')
                filename = f'{sanitized_email}.jpg'
                profile_picture.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            else:
                filename = 'default.jpg'

            if affiliation is None:
                new_user = Evaluators(name=sanitized_name, surname=sanitized_surname, email=sanitized_email,
                                      password=generate_password_hash(sanitized_password, method='sha256'), profile_picture=filename)
            else:
                new_user = Researchers(name=sanitized_name, surname=sanitized_surname, email=sanitized_email,
                                       password=generate_password_hash(sanitized_password, method='sha256'),
                                       affiliation=affiliation, profile_picture=filename)

            db.session.add(new_user)
            db.session.commit()

            login_user(new_user, remember=True)
            if affiliation is None:
                session['user_type'] = 'evaluator'
            else:
                session['user_type'] = 'researcher'
            return redirect(url_for('views.projects'))
        return render_template('register.html', user=session['user_type'])
    return render_template('register.html', user='none')


# logout route
@auth.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('auth.login'))
