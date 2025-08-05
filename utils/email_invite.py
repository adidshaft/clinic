import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, Content
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import datetime

def send_email_with_ics(to_email, subject, body, summary, start_time, end_time, location):
    sender = "your_email@example.com"  # replace with your verified sender
    sg = SendGridAPIClient(api_key=os.environ["SENDGRID_API_KEY"])

    # Build ICS file
    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//yourcompany//Appointment Scheduler//EN
BEGIN:VEVENT
UID:{datetime.datetime.now().timestamp()}@yourapp.com
DTSTAMP:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{start_time.strftime('%Y%m%dT%H%M%SZ')}
DTEND:{end_time.strftime('%Y%m%dT%H%M%SZ')}
SUMMARY:{summary}
LOCATION:{location}
DESCRIPTION:{body}
END:VEVENT
END:VCALENDAR
"""

    # Build email
    message = Mail(
        from_email=sender,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body
    )

    # Add calendar invite as attachment
    attachment = Attachment()
    attachment.file_content = ics_content.encode("utf-8").decode("latin1")
    attachment.file_type = "text/calendar"
    attachment.file_name = "invite.ics"
    attachment.disposition = "attachment"
    message.attachment = attachment

    try:
        response = sg.send(message)
        print("Email sent:", response.status_code)
    except Exception as e:
        print("SendGrid error:", str(e))
