#install icalender using following command: pip3 install icalendar
from icalendar import Calendar, Event
from datetime import datetime
from pytz import UTC   # timezone


#https://stackoverflow.com/questions/3408097/parsing-files-ics-icalendar-using-python

g = open('charlesrichardsonusagmail.com.ics', 'rb')
gcal = Calendar.from_ical(g.read())
for component in gcal.walk():
    if component.name == "VEVENT":
        print(component.get('summary'))
        print(component.get('dtstart'))
        print(component.get('dtend'))
        print(component.get('dtstamp'))
g.close()
