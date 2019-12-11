from flask import Flask, render_template, request, redirect, json, session, url_for,jsonify
from google.cloud import datastore
import requests
client = datastore.Client('personalityprofile')
#import helper,forms and config file
import importlib
helper = importlib.import_module('helper')
if helper is None:
    print("can't find tbe helper module")
form = importlib.import_module('forms')
if form is None:
    print("can't find tbe forms module")
config = importlib.import_module('config')
if config is None:
    print("can't find the configuration settings module")

app = Flask(__name__)
app.secret_key = config.STATE
auth_uri = ('https://accounts.google.com/o/oauth2/v2/auth?response_type=code'
            '&client_id={}&redirect_uri={}&scope={}&state={}').format(config.CLIENT_ID, config.REDIRECT_URI,
                                                                      config.SCOPE, app.secret_key)
@app.route('/oauth2callback', methods=['GET'])
def oauth2callback():
    """Trys again to get credentials from server"""
    if 'credentials' not in session:
        return redirect(url_for('token'))
    credentials = json.loads(session['credentials'])
    if credentials['expires_in'] <= 0:
        return redirect(url_for('token'))
    else:
        headers = {'Authorization': 'Bearer {}'.format(credentials['access_token'])}
        req_uri = 'https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses'
        response = requests.get(req_uri, headers=headers)
        userprofile = json.loads(response.text)
        token = credentials['id_token']
        user_id = str(userprofile['names'][0]['metadata']['source']['id'])
        profile = {"first_name": userprofile['names'][0]['givenName'],
                                   "last_name": userprofile['names'][0]['familyName'], 'user_id': user_id}
        boolval = helper.CheckIfDuplicate('users', 'user_id', user_id)
        if boolval == 0:
            users = datastore.entity.Entity(key=client.key('users'))
            users.update(profile)
            client.put(users)
        output = {"profile": profile}
        output['id_token'] = token
        return jsonify(output), '302 Found'

@app.route('/token', methods=['GET', 'POST'])
def token():
    """Sends POST to Google API Token Server to Get Token"""
    if 'code' not in request.args:
        return redirect(auth_uri)
    else:
        if request.args.get('state') != app.secret_key:
            return jsonify(Error='State Returned does Not match that of client '), '403'
        auth_code = request.args.get('code')
        data = {'code': auth_code,
                'client_id': config.CLIENT_ID,
                'client_secret': config.CLIENT_SECRET,
                'redirect_uri': config.REDIRECT_URI,
                'grant_type': 'authorization_code'}
        req = requests.post('https://oauth2.googleapis.com/token', data=data)
        session['credentials'] = req.text
        return redirect(url_for('oauth2callback'))

@app.route('/users', methods=['GET', 'POST'])
@app.route('/users/', methods=['GET','POST'])
def oauth_Google():
    """POST request to Google authorization url on submit of form button"""
    if request.method == 'POST':
        return redirect(auth_uri)
    else:
        """Starting Login Page sent at GET request"""
        form_info = form.LoginForm()
        return render_template('signin.html', form=form_info)

@app.route('/',methods=['GET','POST','DELETE'])
def index():
    # Returns a not found html page with info on endpoints
    return render_template('404.html')

@app.route('/questions',methods=['POST','PUT','DELETE','GET'])
@app.route('/questions/', methods=['DELETE','PUT','PATCH'])
@app.route('/questions?pages=<int:page>',methods=['GET'])
def questions_post_get(page=1):
    url = str(request.base_url)
    if request.method == 'PUT' or request.method == 'DELETE'or request.method == 'PATCH':
        return helper.NotSupported405()
    if request.method == 'POST' or request.method == 'GET':
        if request.mimetype != 'application/json':
            return helper.NotAccepted406('Content-Type', request.mimetype)
        if not request.accept_mimetypes['application/json']:
            return helper.NotAccepted406('Accept', request.accept_mimetypes)
    if request.method == 'POST':
        # This will fail and return error if JWT is missing or incorrect. otherwise it will continue
        if 'Authorization' not in request.headers:
            return helper.Unauthorized401()
        req, token = helper.GetToken()
        if token is None:
            return helper.Unauthorized401()
        try:
            userid = helper.GetID(token, req)
        except ValueError:
            return helper.Unauthorized401()
        content = request.get_json(silent=True)
        if not content:
            return helper.BadRequest400()
        #Error Checks on input json
        if len(content) == 3:
            if 'text' in content and 'type' in content and 'date' in content:
                correct_text = helper.CheckVal(content["text"],str)
                bool_val = helper.CheckIfDuplicate('questions','text',content['text'])
                if bool_val == 1:
                    return helper.Duplicate403('question',content['text'])
                correct_type = helper.CheckType(content["type"])
                correct_date = helper.is_date(content["date"])
                if correct_text and correct_type and correct_date is True:
                    questions = datastore.entity.Entity(key=client.key('questions'))
                    questions.update({"text": content["text"],"type": content["type"],"date": content["date"],'created_by': userid})
                    client.put(questions)
                    return jsonify(id=questions.key.id,text=content["text"],type=content["type"],date=content["date"],created_by=userid, answers=None,
                               self=url+"/"+str(questions.key.id)),'201 Created'
                else:
                    return helper.BadRequest400()
            else:
                return helper.BadRequest400()
        else:
            return helper.BadRequest400()
    elif request.method == 'GET':
        page_num = request.args.get('pages')
        if page_num is None:
            page_num = page
        #This will return even if JWT is missing or incorrect
        next_url, results, number = helper.PaginationResultsAndLink(url, int(page_num), 'questions')
        for e in results:
            e["id"] = e.key.id
            e['self'] = url + "/" + str(e.key.id)
        # In the future here we will include related answers and their self links
            answers = helper.ReturnRelatedObjects(url, 'question_answer', 'question_id',int(e.key.id),'answer_id', 2, '/answers/')
            if not answers:
                e['answers'] = None
            else:
                e['answers'] = answers  # as list to the list
        output = {"results": results}
        if next_url:
            output['next'] = next_url
        output['number'] = number
        return jsonify(output),'200 OK'
    else:
        return helper.BadRequest400()

@app.route('/answers',methods=['POST','PUT','DELETE','GET'])
@app.route('/answers/', methods=['DELETE','PUT','PATCH'])
@app.route('/answers?pages=<int:page>',methods=['GET'])
def answers_post_get(page=1):
    url = str(request.base_url)
    if request.method == 'PUT' or request.method == 'DELETE'or request.method == 'PATCH':
        return helper.NotSupported405()
    if request.method == 'POST' or request.method == 'GET':
        if request.mimetype != 'application/json':
            return helper.NotAccepted406('Content-Type', request.mimetype)
        if not request.accept_mimetypes['application/json']:
            return helper.NotAccepted406('Accept', request.accept_mimetypes)
    if request.method == 'POST':
        # This will fail and return error if JWT is missing or incorrect. otherwise it will continue
        if 'Authorization' not in request.headers:
            return helper.Unauthorized401()
        req, token = helper.GetToken()
        if token is None:
            return helper.Unauthorized401()
        try:
            userid = helper.GetID(token, req)
        except ValueError:
            return helper.Unauthorized401()
        content = request.get_json(silent=True)
        if not content:
            return helper.BadRequest400()
        #Error Checks on input json
        if len(content) == 3:
            if 'text' in content and 'score' in content and 'date' in content:
                correct_text = helper.CheckVal(content["text"],str)
                correct_score = helper.CheckVal(content["score"],int)
                if content["score"] <= 0:
                    correct_score = False
                correct_date = helper.is_date(content["date"])
                if correct_text and correct_score and correct_date is True:
                    answers = datastore.entity.Entity(key=client.key('answers'))
                    answers.update({"text": content["text"],"score": content["score"], "date": content["date"],"created_by": userid})
                    client.put(answers)
                    return jsonify(id=answers.key.id,text=content["text"],score=content["score"],date=content["date"],created_by=userid, questions=None,
                               self=url+"/"+str(answers.key.id)),'201 Created'
                else:
                    return helper.BadRequest400()
            else:
                return helper.BadRequest400()
        else:
            return helper.BadRequest400()
    elif request.method == 'GET':
        page_num = request.args.get('pages')
        if page_num is None:
            page_num = page
        #This will return even if JWT is missing or incorrect
        next_url, results, number = helper.PaginationResultsAndLink(url, int(page_num), 'answers')
        for e in results:
            e["id"] = e.key.id
            e['self'] = url + "/" + str(e.key.id)
        # Get the related question, return null if none
            questions = helper.ReturnRelatedObjects(url, 'question_answer', 'answer_id',int(e.key.id),'question_id', 2, '/questions/')
            if not questions:
                e['questions'] = None
            else:
                e['questions'] = questions  # as list to the list
        output = {"results": results}
        if next_url:
            output['next'] = next_url
        output['number'] = number
        return jsonify(output),'200 OK'
    else:
        return helper.BadRequest400()

@app.route('/questions/<id>', methods=['GET','DELETE','PUT','PATCH'])
def question_get_put_patch_delete(id):
    if not id:
        return helper.BadRequest400()
    url = str(request.base_url)
    question_key = client.key("questions", int(id))
    question = client.get(key=question_key)
    if question is None:
        return helper.NotFound404('question', 'question_id')
    if request.method == 'GET' or request.method == 'PUT' or request.method == 'PATCH':
        if request.mimetype != 'application/json':
            return helper.NotAccepted406('Content-Type', request.mimetype)
        if not request.accept_mimetypes['application/json']:
            return helper.NotAccepted406('Accept', request.accept_mimetypes)
    if request.method == 'GET':
        question["id"] = int(id)
        question['self'] = url
        answers = helper.ReturnRelatedObjects(url, 'question_answer', 'question_id',int(id),'answer_id', 2, '/answers/')
        if not answers:
            question['answers'] = None
        else:
            question['answers'] = answers  # as list to the list
        return jsonify(question), '200 OK'
    elif request.method == 'DELETE' or request.method == 'PUT' or request.method == 'PATCH':
        if 'Authorization' not in request.headers:
            return helper.Unauthorized401()
        req, token = helper.GetToken()
        if token is None:
            return helper.Unauthorized401()
        try:
            userid = helper.GetID(token, req)
            if question['created_by'] != str(userid):
                return helper.Unauthorized401()
        except ValueError:
            return helper.Unauthorized401()
        if request.method == 'DELETE':
            #delete question answer relationships
            query = client.query(kind='question_answer')
            query.add_filter('question_id', '=', int(id))
            results = list(query.fetch())
            for e in results:
                question_answer_key = client.key("question_answer", e.key.id)
                client.delete(question_answer_key)
            client.delete(question_key)
            return jsonify(),"204 No Content"
        #fully edit the question
        elif request.method == 'PUT':
            content = request.get_json(silent=True)
            if not content:
                return helper.BadRequest400()
            if len(content) == 3:
                if 'text' in content and 'type' in content and 'date' in content:
                    correct_text = helper.CheckVal(content["text"], str)
                    bool_val = helper.CheckIfDuplicate('questions', 'text', content['text'])
                    if bool_val == 1:
                        return helper.Duplicate403('question', content['text'])
                    correct_type = helper.CheckType(content["type"])
                    correct_date = helper.is_date(content["date"])
                    if correct_text and correct_type and correct_date is True:
                        question['text'] = content['text']
                        question['date'] = content['date']
                        question['type'] = content['type']
                        question.update({"text": question["text"], "type": question["type"], "date": question["date"],'created_by': question['created_by']})
                        client.put(question)
                        answers = helper.ReturnRelatedObjects(url, 'question_answer', 'question_id', int(id), 'answer_id', 2, '/answers/')
                        if not answers:
                            question['answers'] = None
                        else:
                            question['answers'] = answers  # as list to the list
                        question["id"] = int(id)
                        question['self'] = url
                        return jsonify(question), 303
                    else:
                        return helper.BadRequest400()
                else:
                    return helper.BadRequest400()
            else:
                return helper.BadRequest400()
        elif request.method == 'PATCH':
            content = request.get_json(silent=True)
            if not content:
                return helper.BadRequest400()
            if 'text' in content:
                correct_text = helper.CheckVal(content["text"], str)
                bool_val = helper.CheckIfDuplicate('questions','text',content['text'])
                if bool_val == 1:
                    return helper.Duplicate403('question',content['text'])
                if correct_text is True:
                    question['text'] = content['text']
                else:
                    return helper.BadRequest400()
            if 'date' in content:
                correct_date = helper.is_date(content["date"])
                if correct_date is True:
                    question['date'] = content['date']
                else:
                    return helper.BadRequest400()
            if 'type' in content:
                correct_type = helper.CheckType(content["type"])
                if correct_type is True:
                    question['type'] = content['type']
                else:
                    return helper.BadRequest400()
            question.update({"text": question["text"], "type": question["type"], "date": question["date"], 'created_by': question['created_by']})
            client.put(question)
            answers = helper.ReturnRelatedObjects(url, 'question_answer', 'question_id', int(id), 'answer_id', 2,'/answers/')
            if not answers:
                question['answers'] = None
            else:
                question['answers'] = answers  # as list to the list
            question["id"] = int(id)
            question['self'] = url
            return jsonify(question), 303
        else:
            return helper.BadRequest400()
    else:
        return helper.NotFound404('question', 'question_id')

@app.route('/answers/<id>', methods=['GET','DELETE','PUT','PATCH'])
def answers_get_put_patch_delete(id):
    if not id:
        return helper.BadRequest400()
    url = str(request.base_url)
    answer_key = client.key("answers", int(id))
    answer = client.get(key=answer_key)
    if answer is None:
        return helper.NotFound404('answer', 'answer_id')
    if request.method == 'GET' or request.method == 'PUT' or request.method == 'PATCH':
        if request.mimetype != 'application/json':
            return helper.NotAccepted406('Content-Type', request.mimetype)
        if not request.accept_mimetypes['application/json']:
            return helper.NotAccepted406('Accept', request.accept_mimetypes)
    if request.method == 'GET':
        answer["id"] = int(id)
        answer['self'] = url
        questions = helper.ReturnRelatedObjects(url, 'question_answer', 'answer_id',int(id),'question_id', 2, '/questions/')
        if not questions:
            answer['questions'] = None
        else:
            answer['questions'] = questions  # as list to the list
        return jsonify(answer), '200 OK'
    elif request.method == 'DELETE' or request.method == 'PUT' or request.method == 'PATCH':
        if 'Authorization' not in request.headers:
            return helper.Unauthorized401()
        req, token = helper.GetToken()
        if token is None:
            return helper.Unauthorized401()
        try:
            userid = helper.GetID(token, req)
            if answer['created_by'] != str(userid):
                return helper.Unauthorized401()
        except ValueError:
            return helper.Unauthorized401()
        # checks if the user id matches the user resources requested
        if request.method == 'DELETE':
            #delete answer question relationships
            query = client.query(kind='question_answer')
            query.add_filter('answer_id', '=', int(id))
            results = list(query.fetch())
            for e in results:
                question_answer_key = client.key("question_answer", e.key.id)
                client.delete(question_answer_key)
            client.delete(answer_key)
            return jsonify(),"204 No Content"
            # fully edit the answer
        elif request.method == 'PUT':
            content = request.get_json(silent=True)
            if not content:
                return helper.BadRequest400()
            if len(content) == 3:
                if 'text' in content and 'score' in content and 'date' in content:
                    correct_text = helper.CheckVal(content["text"], str)
                    correct_score = helper.CheckVal(content["score"], int)
                    if content["score"] <= 0:
                        correct_score = False
                    correct_date = helper.is_date(content["date"])
                    if correct_text and correct_score and correct_date is True:
                        answer['text'] = content['text']
                        answer['date'] = content['date']
                        answer['score'] = content['score']
                        answer.update({"text":answer["text"], "score": answer["score"], "date": answer["date"]})
                        client.put(answer)
                        questions = helper.ReturnRelatedObjects(url, 'question_answer', 'answer_id', int(id),
                                                              'question_id', 2, '/questions/')
                        if not questions:
                            answer['questions'] = None
                        else:
                            answer['questions'] = questions  # as list to the list
                        answer["id"] = int(id)
                        answer['self'] = url
                        return jsonify(answer), 303
                    else:
                        return helper.BadRequest400()
                else:
                    return helper.BadRequest400()
            else:
                return helper.BadRequest400()
        elif request.method == 'PATCH':
            content = request.get_json(silent=True)
            if not content:
                return helper.BadRequest400()
            if 'text' in content:
                correct_text = helper.CheckVal(content["text"], str)
                if correct_text is True:
                    answer['text'] = content['text']
                else:
                    return helper.BadRequest400()
            if 'date' in content:
                correct_date = helper.is_date(content["date"])
                if correct_date is True:
                    answer['date'] = content['date']
                else:
                    return helper.BadRequest400()
            if 'score' in content:
                correct_score = helper.CheckVal(content["score"], int)
                if content["score"] <= 0:
                    correct_score = False
                if correct_score is True:
                    answer['score'] = content['score']
                else:
                    return helper.BadRequest400()
            answer.update({"text": answer["text"], "score": answer["score"], "date": answer["date"]})
            client.put(answer)
            questions = helper.ReturnRelatedObjects(url, 'question_answer', 'answer_id', int(id),
                                                    'question_id', 2, '/questions/')
            if not questions:
                answer['questions'] = None
            else:
                answer['questions'] = questions  # as list to the list
            answer["id"] = int(id)
            answer['self'] = url
            return jsonify(answer), 303
        else:
            return helper.NotFound404('answer', 'answer_id')
    else:
        return helper.NotFound404('answer', 'answer_id')

#get User's answers and questions created
@app.route('/users/<id>', methods=['GET'])
def users_get(id):
    url = str(request.base_url)
    if not id:
        return helper.BadRequest400()
    if request.mimetype != 'application/json':
        return helper.NotAccepted406('Content-Type', request.mimetype)
    if not request.accept_mimetypes['application/json']:
        return helper.NotAccepted406('Accept', request.accept_mimetypes)
    if request.method == 'GET':
        # This will fail and return error if JWT is missing or incorrect. otherwise it will continue
        if 'Authorization' not in request.headers:
            return helper.Unauthorized401()
        req, token = helper.GetToken()
        if token is None:
            return helper.Unauthorized401()
        try:
            userid = helper.GetID(token, req)
            print(userid)
            # check if correct user.
        except ValueError:
            return helper.Unauthorized401()
        # checks if the user id matches the user resources requested
        if userid != str(id):
            return helper.Unauthorized401()
        #get users answers
        query = client.query(kind='answers')
        query.add_filter('created_by', '=', str(id))
        answers_results = list(query.fetch())
        if answers_results is None:
            answers_results = None
        else:
            # View User's Answers
            for answer in answers_results:
                answer["id"] = answer.key.id
                answer['self'] = url.rsplit('/', 2)[0] + '/answers/' + str(answer.key.id)
        #get users questions
        query = client.query(kind='questions')
        query.add_filter('created_by', '=', str(id))
        questions_results = list(query.fetch())
        if questions_results is None:
            questions_results = None
        else:
            # View User's questions
            for question in questions_results:
                question["id"] = question.key.id
                question['self'] =  url.rsplit('/', 2)[0] + '/questions/' + str(question.key.id)
        results = {"answers":answers_results,'questions': questions_results}
        return jsonify(results), '200 OK'
    else:
        return helper.NotSupported405()

'''Managing answers related to questions'''
@app.route('/questions/<question_id>/<answer_id>', methods=['PUT','DELETE'])
def question_answer_put_delete(question_id,answer_id):
    # Then lets check if each of these exist first
    question_key = client.key("questions", int(question_id))
    answer_key = client.key("answers", int(answer_id))
    question = client.get(key=question_key)
    answer = client.get(key=answer_key)
    if question is None:
        return helper.NotFound404(question, question_id)
    if answer is None:
        return helper.NotFound404(answer, answer_id)
    # let's check if the user is authorized to manage these items
    if 'Authorization' not in request.headers:
        return helper.Unauthorized401()
    req, token = helper.GetToken()
    if token is None:
        return helper.Unauthorized401()
    try:
        userid = helper.GetID(token, req)
        # check if correct user.
    except ValueError:
        return helper.Unauthorized401()
    # checks if the user id matches the user resources requested
    if question['created_by'] == str(userid) and answer['created_by'] == str(userid):
        if request.method == 'PUT':
            query = client.query(kind='question_answer')
            query.add_filter('question_id', '=', int(question_id))
            query.add_filter('answer_id', '=', int(answer_id))
            results = list(query.fetch())
            if not results:
                #create a relationship entity in question_answer
                question_answer = datastore.entity.Entity(key=client.key('question_answer'))
                question_answer.update({"question_id": int(question_id), "answer_id": int(answer_id)})
                client.put(question_answer)
                return jsonify(),'204 No Content'
            else:
                return helper.Forbidden403PUT('answer', 'question')

        elif request.method == 'DELETE':
            # delete boat load relationships
            query = client.query(kind='question_answer')
            query.add_filter('answer_id', '=', int(answer_id))
            query.add_filter('question_id', '=', int(question_id))
            results = list(query.fetch())
            print(results)
            if not results:
                return helper.Forbidden403('question','answer')
            # delete relationship entity in question_answer
            for e in results:
                question_answer_key = client.key("question_answer", e.key.id)
                client.delete(question_answer_key)
            return jsonify(), "204 No Content"
        else:
            return helper.BadRequest400()
    else:
        return helper.Unauthorized401()

if __name__ == '__main__':
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.
    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host='127.0.0.1', port=8080, debug=True)