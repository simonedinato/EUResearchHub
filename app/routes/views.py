import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, get_flashed_messages, session, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from app.models.database import *
import os
from flask import render_template, request, redirect, url_for, flash, Markup
from markupsafe import escape
from bleach import clean

views = Blueprint('views', __name__)


@views.route('/')
@login_required
def home():
    return render_template('index.html')

@views.route('/projects')
@login_required
def projects():
    projects2show = Projects.query.all()
    user_type = session['user_type']
    # delete the get params

    user = current_user

    counts_by_status = {
        'approved': 0,
        'require changes': 0,
        'submitted for evaluation': 0,
        'not approved': 0
    }

    if user_type == 'evaluator':
        print('evaluator')
        projects2show = Projects.query.all()
        project_counts = ProjectsStatusCount.query.all()
        for row in project_counts:
            counts_by_status[row.status.value] = row.count

    elif user_type == 'researcher':
        print('researcher')
        projects2show = db.session.query(Projects).join(Researchers_Projects).filter(Researchers_Projects.fk_researchers == user.id).all()
        project_counts = db.session.query(Projects.status, func.count()).join(Researchers_Projects).filter(Researchers_Projects.fk_researchers == user.id).group_by(Projects.status).all()
        aux = {status.value: count for status, count in project_counts}
        counts_by_status = {**counts_by_status, **aux}

        print (counts_by_status)



    researcher_profile_pictures = []
    for project in projects2show:
        project_id = project.id
        profile_pictures = db.session.query(Researchers.profile_picture) \
            .join(Researchers_Projects) \
            .filter(Researchers_Projects.fk_projects == project_id) \
            .all()
        researcher_profile_pictures.append(profile_pictures)

    # Aggiungi la query per ottenere la percentuale di documenti valutati per ogni progetto
    evaluation_percentages = {}
    for project in projects2show:
        project_id = project.id
        total_documents = Documents.query.filter_by(fk_project=project_id).count()
        evaluated_documents = Evaluation_Reports.query.join(Documents).filter(
            Documents.fk_project == project_id).count()

        if total_documents > 0:
            evaluation_percentage = int((evaluated_documents / total_documents) * 100)
        else:
            evaluation_percentage = 100

        evaluation_percentages[project_id] = evaluation_percentage

    from sqlalchemy import desc

    evaluation_window = db.session.query(Evaluation_Windows).order_by(desc(Evaluation_Windows.evaluation_windows_to)).first()
    evaluation_window_from = evaluation_window.evaluation_windows_from.strftime("%Y/%m")
    evaluation_window_to = evaluation_window.evaluation_windows_to.strftime("%Y/%m")



    return render_template('projects.html',
                           name=user.name,
                           surname=user.surname,
                           from_date=evaluation_window_from,
                           to_date=evaluation_window_to,
                           counts_by_status=counts_by_status,
                           projects=projects2show,
                           researcher_profile_pictures=researcher_profile_pictures,
                           user_type=user_type,
                           profile_picture=user.profile_picture,

                           evaluation_percentages=evaluation_percentages)


@views.route('/update_project_status', methods=['POST'])
@login_required
def update_project_status():

    project_id = request.form.get('project_id')
    new_status = request.form.get('new_status')
    valid_update = request.form.get('valid_update')

    project = Projects.query.get(project_id)
    if project:
        if valid_update == '1':
            sanitized_status = escape(new_status)
            project.status = sanitized_status
            project.status = new_status
            db.session.commit()
            flash('Project status updated successfully.', 'success')
        else:
            flash('Cannot change the status of a project if not all documents have been evaluated.', 'error')
    else:
        flash('Project not found.', 'error')

    return render_template(url_for('views.projects'))



@views.route('/add_participant', methods=['POST'])
@login_required
def add_participant():
    # Get data from the post request
    data = request.get_json()

    # Get project_id and email from the posted data
    project_id = data.get('projectId')
    email = data.get('email')
    print(project_id)
    print(email)
    sanitized_project_id = escape(project_id)
    sanitized_email = escape(email)
    # Check if the project and the researcher with the provided email exist
    project = Projects.query.get(sanitized_project_id)
    researcher = Researchers.query.filter_by(email=sanitized_email).first()

    if not project or not researcher:
        flash('Project or researcher does not exist.', 'error')
        # If either the project or researcher does not exist, return an error


    # Check if the researcher is already added to the project
    researcher_project = Researchers_Projects.query.filter_by(fk_projects=sanitized_project_id,
                                                              fk_researchers=researcher.id).first()
    if researcher_project:
        # If the researcher is already added, return an error
        flash('Researcher is already added to this project.', 'error')

    # Create a new record
    new_researcher = Researchers_Projects(fk_researchers=researcher.id, fk_projects=sanitized_project_id)

    # Add the new record to the session and commit it to the database
    db.session.add(new_researcher)
    db.session.commit()



    # Return a success response
    return redirect(url_for('views.projects'))


@views.route('/create_project', methods=['POST'])
@login_required
def create_project():
    # Extract the project details from the form data
    title = request.form.get('title')
    description = request.form.get('description')
    sanitized_title = clean(title)
    sanitized_description = clean(description)
    max_evaluation_id = db.session.query(func.max(Evaluation_Windows.id)) # trovo l'ultima evaluation window disponibile

    # creo e aggiungo il progetto al database
    new_project = Projects(title=sanitized_title, description=sanitized_description, status=EnumStatus.submitted_for_evaluation, fk_evaluation_window = max_evaluation_id)

    db.session.add(new_project)
    db.session.commit()

    # collego il progetto all'utente
    project_creator = Researchers_Projects(fk_researchers=current_user.id, fk_projects=new_project.id)
    db.session.add(project_creator)
    db.session.commit()

    return redirect(url_for('views.project', project_id=new_project.id))


@views.route('/project/<int:project_id>', methods=['GET', 'POST'])

@login_required
def project(project_id):
    document_id = request.args.get('document_id')
    if request.method == 'POST':

        message_text = request.form.get('message')
        user_type = session['user_type']
        sanitized_message_text = clean(message_text)
        # Create a new message object
        message = Messages(text=sanitized_message_text, fk_projects=project_id)
        db.session.add(message)
        db.session.commit()

        # Associate the message with the current user based on the user type
        if user_type == 'evaluator':
            evaluator_message = Evaluators_Messages(fk_evaluators=current_user.id, fk_messages=message.id)
            db.session.add(evaluator_message)
        elif user_type == 'researcher':
            researcher_message = Researchers_Messages(fk_researchers=current_user.id, fk_messages=message.id)
            db.session.add(researcher_message)

        db.session.commit()
        redirect_url = url_for('views.project', project_id=project_id)
        if document_id:
            redirect_url += f"?document_id={document_id}"


        # Redirect the user to the URL with query parameters
        return redirect(redirect_url)


    # Controllo se l'utente è un ricercatore
    messages = Messages.query.filter_by(fk_projects=project_id).all()

    researchers = []
    evaluators = []

    for message in messages:
        researcher = Researchers.query.join(Researchers_Messages).filter_by(fk_messages=message.id).first()
        evaluator = Evaluators.query.join(Evaluators_Messages).filter_by(fk_messages=message.id).first()
        researchers.append(researcher)
        evaluators.append(evaluator)

    # Ottengo le informazioni relative al progetto corrente
    project = Projects.query.filter_by(id=project_id).first()

    # Ottengo la lista dei documenti del progetto
    documents = Documents.query.filter_by(fk_project=project_id).all()
    # Per ogni documento voglio sapere il tipo
    docs = []
    for doc in documents:
        doc_type = Document_Types.query.filter_by(id=doc.fk_document_type).first()
        # ho bisogno di doc_version.max_id per quel documento
        doc_version = db.session.query(func.max(Document_Versions.id)).filter_by(fk_document=doc.id).first()

        doc_id = db.session.query(Document_Versions.fk_document).filter_by(id=doc_version[0]).first()
        ev_doc_type = db.session.query(Documents.fk_document_type).filter_by(id=doc_id[0]).first()
        # controllo se esiste un evaluation report per quel documento
        if(os.path.exists(os.path.join(os.path.dirname(__file__), '../static/uploads/projects/' + str(project_id) + '/' + str(ev_doc_type[0]) + '/evaluation_report.pdf'))):
            ev_rep = str(project_id) + '/' +  str(ev_doc_type[0]) + '/evaluation_report.pdf'
        else:
            ev_rep = None

        docs.append({
            'id': doc_type.id,
            'nome': doc_type.nome,
            'descrizione': doc_type.descrizione,
            'file_path': doc.file_path + '/' + str(doc_version[0]) + '.pdf',
            'ev_rep': ev_rep
        })

    # Get the view_document data
    if request.args.get('document_id'):
        document_id = request.args.get('document_id')
        document = Documents.query.filter_by(fk_document_type=document_id, fk_project=project_id).first()
        #document = Documents.query.get_or_404(document_id)

        nome_tipo_documento = Document_Types.query.filter_by(id=document.fk_document_type).first()
        versions = Document_Versions.query.filter_by(fk_document=document.id).all()

        return render_template('project.html',
                               profile_picture=current_user.profile_picture,
                               name=current_user.name,
                               surname=current_user.surname,
                               messages=messages,
                               researchers=researchers,
                               evaluators=evaluators,
                               project=project,
                               documents=docs,
                               selected_document=document,
                               versions=versions,
                               name_document_selected=nome_tipo_documento.nome
                               )

    session['project_id'] = project_id
    return render_template('project.html',
                           profile_picture=current_user.profile_picture,
                           name=current_user.name,
                           surname=current_user.surname,
                           messages=messages,
                           researchers=researchers,
                           evaluators=evaluators,
                           project=project,
                           documents=docs
                           )

