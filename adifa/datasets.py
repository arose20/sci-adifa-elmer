import os

from flask import Blueprint, current_app, flash, redirect, render_template, send_from_directory, session, request, url_for

from adifa import models


bp = Blueprint('datasets', __name__)

@bp.route("/")
def index():
    return render_template('index.html')
  
@bp.route('/dataset/<int:id>/scatterplot')
def scatterplot(id):
    dataset = models.Dataset.query.get(id)

    from collections import OrderedDict 
    from operator import getitem 
    obs = OrderedDict(sorted(dataset.data_obs.items(), key = lambda x: getitem(x[1], 'name'))) 
    return render_template('scatterplot.html', did=id, dataset=dataset, obs=obs)    
  
@bp.route('/dataset/<int:id>/heatmap')
def heatmap(id):
    dataset = models.Dataset.query.get(id)

    # Check protected status
    authenticated = session.get("auth_dataset_" + str(id), False)
    if dataset.password and not authenticated:
        return redirect(url_for('datasets.password', id=id))

    from collections import OrderedDict 
    from operator import getitem 
    obs = OrderedDict(sorted(dataset.data_obs.items(), key = lambda x: getitem(x[1], 'name'))) 
    return render_template('heatmap.html', did=id, dataset=dataset, obs=obs)    

@bp.route('/dataset/<int:id>/download', methods=['GET'])
def download(id):
    dataset = models.Dataset.query.get(id)

    # Check protected status
    authenticated = session.get("auth_dataset_" + str(id), False)
    if dataset.password and not authenticated:
        return redirect(url_for('datasets.password', id=id))

    if dataset.download_link:
        return redirect(dataset.download_link, code=302)
    else:
        if (os.path.isabs(current_app.config.get('DATA_PATH'))):
            directory = os.path.realpath(current_app.config.get('DATA_PATH'))
        else:
            directory = os.path.realpath(current_app.root_path + '/../' + current_app.config.get('DATA_PATH'))

        return send_from_directory(
            directory, dataset.filename, as_attachment=True
        )

@bp.route('/dataset/<int:id>/password', methods=['GET', 'POST'])
def password(id):
    dataset = models.Dataset.query.get(id)

    authenticated = session.get("auth_dataset_" + str(id), False)
    if dataset.password and authenticated:
        return redirect(url_for('datasets.password', id=id))

    # Handle the POST request
    if request.method == 'POST':
        password = request.form.get('password')
        if dataset.password == password:
            session["auth_dataset_" + str(id)] = True
            return redirect(url_for('datasets.scatterplot', id=id))
        else:
            flash('The password you entered is not correct')

    # Otherwise handle the GET request
    return render_template('password.html', did=id, dataset=dataset)    
