from flask import jsonify, request
from dateutil.parser import parse
from google.cloud import datastore
from google.auth.transport import requests as google_auth_request
client = datastore.Client('personalityprofile')
from google.oauth2 import id_token
import importlib
config = importlib.import_module('config')
if config is None:
    print("can't find the configuration settings module")

'''Sample from https://stackoverflow.com/questions/25341945/check-if-string-has-date-any-format'''
def is_date(string, fuzzy=False):
    try:
        parse(string, fuzzy=fuzzy)
        return True
    except ValueError:
        return False

def BadRequest400():
    return jsonify(Error='The request object is missing at least one of the required attributes'), '400 Bad Request'

def Forbidden403(entity,entity2):
    error_message = f'{entity} does not have an existing relationship with {entity2}.'
    return jsonify(Error=str(error_message)), '403'

def Unauthorized401():
    error_message =  f'Unauthorized, Missing or Invalid JWT Token used.'
    return jsonify(Error=str(error_message)), '401'

def NotFound404(object,id):
    error_message = f'No {object} with this {id} exists'
    return jsonify(Error=str(error_message)), '404 Not Found'
def NotSupported405():
    error_message = f"PUT, PATCH or DELETE methods are not supported at root of this URL."
    return jsonify(Error=str(error_message)),405
def NotAccepted406(type,inrequest):
    error_message = f"{type} {inrequest} is not supported. Use application\u002Fjson"
    return jsonify(Error=error_message), 406

def CheckIfDuplicate(kind,attribute,value):
    query = client.query(kind= kind)
    query.add_filter(attribute, '=', str(value))
    object = list(query.fetch())
    if object:
        return 1
    else:
        return 0

def Forbidden403PUT(object1,object2):
    error_message = f'The {object1} is already assigned to this {object2}'
    return jsonify(Error=str(error_message)), '403 Forbidden'

def Duplicate403(entity,value):
    error_message = f'{value} is duplicate to an existing value for {entity}.'
    return jsonify(Error=str(error_message)), '403 Forbidden'


def CheckType(value):
    if value == 1 or value == 2 or value == 3:
        return True
    else:
        return False

def CheckVal(value,type):
    boolval = isinstance(value,type)
    length = len(str(value))
    print(length)
    if length > 500:
        boolval = False
    return boolval

def GetID(intoken,inrequest):
    id_info = id_token.verify_oauth2_token(intoken, inrequest, config.CLIENT_ID)
    return id_info['sub']

def GetToken():
    req = google_auth_request.Request()
    bearer_token = request.headers['Authorization']
    token = bearer_token.rsplit(' ', 1)[1]
    return req,token

def PaginationResultsAndLink(url,page,entity):
    offset = (page-1)*config.LIMIT
    # get each entity in enity
    query = client.query(kind= entity)
    iterator = query.fetch(limit=config.LIMIT, offset=offset)
    pages = iterator.pages
    results = list(next(pages))
    query_total = client.query(kind=entity)
    objects = list(query_total.fetch())
    number = len(objects)
    next_page = page + 1
    if iterator.next_page_token:
        next_url = url + "?pages=" + str(next_page)
    else:
        next_url = None
    return next_url,results,number

#helper.ReturnRelatedObjects(url, 'question_answer', 'question_id',int(id),'answer_id', 2, '/answers/')
def ReturnRelatedObjects(url,kind,data_id,input_id,object_id,split,url_part):
    query = client.query(kind=kind)
    query.add_filter(data_id, '=', input_id)
    objects = list(query.fetch())
    for object in objects:
        object['id'] = object[object_id]
        object['self'] = url.rsplit('/', split)[0] + url_part + str(object[object_id])
        # remove unrequired properties
        object.pop(data_id)
        object.pop(object_id)
    return objects

