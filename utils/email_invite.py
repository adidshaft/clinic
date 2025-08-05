import os
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment
import base64
import datetime

def send_email_with_ics(to_email, subject, body, summary, start_time, end_time, location):
    sg_api_key = os.getenv("SENDGRID_API_KEY")
    from_email_address = os.getenv("SENDGRID_VERIFIED_EMAIL")

    if not sg_api_key:
        print("Missing SENDGRID_API_KEY.")
        return

    if not from_email_address:
        print("Missing SENDGRID_VERIFIED_EMAIL.")
        return

    sg = sendgrid.SendGridAPIClient(api_key=sg_api_key)

    # Generate ICS data
    dtstamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    dtstart = start_time.strftime("%Y%m%dT%H%M%S")
    dtend = end_time.strftime("%Y%m%dT%H%M%S")

    ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Your Clinic//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
DTSTAMP:{dtstamp}
DTSTART:{dtstart}
DTEND:{dtend}
SUMMARY:{summary}
LOCATION:{location}
DESCRIPTION:{body}
STATUS:CONFIRMED
SEQUENCE:0
BEGIN:VALARM
TRIGGER:-PT15M
ACTION:DISPLAY
DESCRIPTION:Reminder
END:VALARM
END:VEVENT
END:VCALENDAR
"""

    encoded_ics = base64.b64encode(ics_content.encode('utf-8')).decode('utf-8')

    attachment = Attachment()
    attachment.file_content = encoded_ics
    attachment.file_type = "text/calendar"
    attachment.file_name = "appointment.ics"
    attachment.disposition = "attachment"

    message = Mail(
        from_email=Email(from_email_address),
        to_emails=To(to_email),
        subject=subject,
        plain_text_content=Content("text/plain", body)
    )

    message.attachment = attachment

    try:
        response = sg.send(message)
        print(f"Email sent to {to_email}, Status Code: {response.status_code}")
    except Exception as e:
        print("SendGrid error:", e)
