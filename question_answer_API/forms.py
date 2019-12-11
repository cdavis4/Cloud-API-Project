#example from: http://flask.palletsprojects.com/en/0.12.x/patterns/wtforms/
from wtforms import Form, SubmitField
class LoginForm(Form):
    submit = SubmitField('Google Authentication')