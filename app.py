import datetime
import json
import os
import shelve

from apiclient.discovery import build
from flask import Flask, request
from httplib2 import Http
from oauth2client.client import SignedJwtAssertionCredentials
from slacker import Slacker

app = Flask(__name__)

client_email = 'calendar-inviter@calendar-inviter.iam.gserviceaccount.com'
with open("client_secret.json") as f:
   private_key = json.load(f)['private_key']
credentials = SignedJwtAssertionCredentials(client_email, private_key,
    'https://www.googleapis.com/auth/calendar')
http = credentials.authorize(Http())
service = build('calendar', 'v3', http=http)

@app.route('/auth', methods=['GET'])
def oauth():
    db = shelve.open('db')
    code = request.args.get('code')
    oauth_info = Slacker.oauth.access(os.environ['CLIENT_ID'], os.environ['CLIENT_SECRET'], code).body
    db[str(oauth_info['team_id'])] = str(oauth_info['access_token'])
    db.close()
    return 'successfully authenticated'

@app.route('/event', methods=['POST'])
def make_event():
    if not request.form.get('token') == os.environ['token']:
       return 'Could not validate request'
    try:
        text = request.form['text']
        if text == "help":
            return "Input is formatted in following way. EVENT NAME from HH:MM PM to HH:MM PM on MM/DD/YY at LOCATION(optional) with @users @to @invite OR @channel to invite everyone"
        db = shelve.open('db')
        slack = Slacker(db[request.form['team_id']])
        db.close()
        channel_id = request.form['channel_id']
        if channel_id.startswith('C'):
            members = slack.channels.info(channel_id).body['channel']['members']
        elif channel_id.startswith('G'):
            members = slack.groups.info(channel_id).body['group']['members']
        user_id = request.form['user_id']
        attendees = get_attendees(slack, text, members, user_id)
        text = text.replace(" from ", ",,,,").replace(" to ", ",,,,").replace(" on ", ",,,,").replace(" at ", ",,,,").replace(" with ", ",,,,").split(',,,,') #unfortunately hideous. returns [name, start_time, end_time, date, location(if provided)]
        summary = text[0]
        date = datetime.datetime.strptime(text[3], "%m/%d/%y")
        start = sanitize_time(date, text[1])
        end = sanitize_time(date, text[2])
        event = {'summary': summary, 'start': start, 'end': end, 'attendees': attendees}
        if len(text) > 5:
            location = text[4]
            event['location'] = location
        eventsResult = service.events().insert(calendarId='primary', body=event, sendNotifications=True).execute()
        return 'Event created!'
    except Exception as e:
        print str(e)
        return 'Input Not Formatted Correctly! Input must come in in the following format: EVENT NAME from HH:MM PM to HH:MM PM on MM/DD/YY at LOCATION(optional) gwith @users @to @invite OR @channel to invite everyone.'

def sanitize_time(date, time):
    time = time.split(':')
    suffix = time[1].split(' ')
    if int(time[0]) > 0 and int(time[0]) < 12 and suffix[1].lower() == 'pm':
        time[0] = int(time[0]) + 12
    time = datetime.time(int(time[0]), int(time[1][0]))
    time = datetime.datetime.combine(date, time)
    time_dict = {'dateTime' : time.isoformat(), 'timeZone': 'America/Los_Angeles'}
    return time_dict

def get_attendees(slack, text, members, user_id):
    words = text.split()
    names = set()
    attendees = []
    for word in words:
        if word.startswith('@'):
            if word == "@channel":
                for member in members:
                    if slack.users.info(member).body['user']['profile'].get('email'):
                        attendees.append({'email': slack.users.info(member).body['user']['profile']['email']})
                return attendees
            else:
                names.add(word.strip('@'))
    if names:
        for member in members:
            user = slack.users.info(member).body['user']
            if user['name'] in names and user['profile'].get('email'):
                attendees.append({'email': slack.users.info(member).body['user']['profile']['email']})
            if len(attendees) >= len(names): #save some API calls and time if you've invited as many people as there are
                break
    attendees.append({'email': slack.users.info(user_id).body['user']['profile']['email']})
    return attendees

if __name__ == '__main__':
    app.run()