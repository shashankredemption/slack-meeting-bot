import datetime
import json
import os

from apiclient.discovery import build
from httplib2 import Http
from flask import Flask, request
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

@app.route('/', methods=['POST'])
def make_event():
    try:
        slack = Slacker(os.environ['SLACK_KEY'])
        channel = request.form['channel_id']
        text = request.form['text'] # CURRENT FORMAT: EVENT/12-31-16/9:00 PM/11:00 PM/(OPTIONAL) LOCATION'
        if channel.startswith('C'):
            members = slack.channels.info(channel).body['channel']['members']
        elif channel.startswith('G'):
            members = slack.groups.info(channel).body['group']['members']
        attendees = []
        for member in members:
            attendees.append({'email': slack.users.info(member).body['user']['profile']['email']})
        text = text.split('/')
        summary = text[0]
        date = datetime.datetime.strptime(text[1], "%m-%d-%y")
        start = sanitize_time(date, text[2])
        end = sanitize_time(date, text[3])
        event = {'summary': summary, 'start': start, 'end': end, 'attendees': attendees}
        if len(text) > 4:
            location = text[4]
            event['location'] = location
        eventsResult = service.events().insert(calendarId='primary', body=event, sendNotifications=True).execute()
        return 'Event created!'
    except:
        return 'Input Not Formatted Correctly! Input must come in in the following format: EVENT/12-31-16/9:00 PM/11:00 PM/(OPTIONAL) LOCATION'

def sanitize_time(date, time):
    time = time.split(':')
    suffix = time[1].split(' ')
    if int(time[0]) > 0 and int(time[0]) < 12 and suffix[1].lower() == 'pm':
        time[0] = int(time[0]) + 12
    time = datetime.time(int(time[0]), int(time[1][0]))
    time = datetime.datetime.combine(date, time)
    time_dict = {'dateTime' : time.isoformat(), 'timeZone': 'America/Los_Angeles'}
    return time_dict

if __name__ == '__main__':
    app.run()