import os
import base64
import datetime
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment

class EmailNotificationService:
    def __init__(self):
        self.sg_api_key = os.getenv('SENDGRID_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@clinic-vnpy.onrender.com')
        self.clinic_name = os.getenv('CLINIC_NAME', 'AI Clinic')
        self.clinic_phone = os.getenv('CLINIC_PHONE', '(555) 123-4567')
        self.clinic_address = os.getenv('CLINIC_ADDRESS', '123 Healthcare Ave, Medical City, MC 12345')
        
        if not self.sg_api_key:
            print("⚠️ WARNING: SENDGRID_API_KEY not configured. Emails will not be sent.")
    
    def send_appointment_confirmation(self, patient_info, appointment_details):
        """Send comprehensive appointment confirmation email to patient"""
        if not self.sg_api_key:
            print("❌ Cannot send email: SendGrid API key not configured")
            return False
        
        try:
            subject = f"✅ Appointment Confirmed - {appointment_details['time']}"
            
            # Create calendar attachment (.ics file)
            ics_content = self._create_calendar_attachment(
                patient_info, appointment_details
            )
            
            # Create beautiful HTML email
            html_content = self._create_confirmation_email_html(
                patient_info, appointment_details
            )
            
            # Create plain text version
            text_content = self._create_confirmation_email_text(
                patient_info, appointment_details
            )
            
            # Build the email
            message = Mail(
                from_email=Email(self.from_email, self.clinic_name),
                to_emails=To(patient_info['email']),
                subject=subject,
                html_content=Content("text/html", html_content),
                plain_text_content=Content("text/plain", text_content)
            )
            
            # Add calendar attachment if created
            if ics_content:
                encoded_ics = base64.b64encode(ics_content.encode('utf-8')).decode('utf-8')
                attachment = Attachment()
                attachment.file_content = encoded_ics
                attachment.file_type = "text/calendar"
                attachment.file_name = "appointment.ics"
                attachment.disposition = "attachment"
                message.attachment = attachment
            
            # Send the email
            sg = SendGridAPIClient(api_key=self.sg_api_key)
            response = sg.send(message)
            
            print(f"✅ Confirmation email sent to {patient_info['email']} | Status: {response.status_code}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending confirmation email: {e}")
            return False
    
    def send_appointment_reminder(self, patient_info, appointment_details, hours_before=24):
        """Send appointment reminder email"""
        if not self.sg_api_key:
            return False
        
        try:
            subject = f"🔔 Appointment Reminder - Tomorrow at {appointment_details['time']}"
            
            html_content = self._create_reminder_email_html(
                patient_info, appointment_details, hours_before
            )
            
            text_content = self._create_reminder_email_text(
                patient_info, appointment_details, hours_before
            )
            
            message = Mail(
                from_email=Email(self.from_email, self.clinic_name),
                to_emails=To(patient_info['email']),
                subject=subject,
                html_content=Content("text/html", html_content),
                plain_text_content=Content("text/plain", text_content)
            )
            
            sg = SendGridAPIClient(api_key=self.sg_api_key)
            response = sg.send(message)
            
            print(f"✅ Reminder email sent to {patient_info['email']} | Status: {response.status_code}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending reminder email: {e}")
            return False
    
    def send_doctor_notification(self, doctor_email, patient_info, appointment_details):
        """Send new appointment notification to doctor"""
        if not self.sg_api_key or not doctor_email:
            return False
        
        try:
            subject = f"📋 New Appointment: {patient_info['firstName']} {patient_info['lastName']} - {appointment_details['time']}"
            
            html_content = self._create_doctor_notification_html(
                patient_info, appointment_details
            )
            
            text_content = self._create_doctor_notification_text(
                patient_info, appointment_details
            )
            
            message = Mail(
                from_email=Email(self.from_email, f"{self.clinic_name} - Patient Portal"),
                to_emails=To(doctor_email),
                subject=subject,
                html_content=Content("text/html", html_content),
                plain_text_content=Content("text/plain", text_content)
            )
            
            sg = SendGridAPIClient(api_key=self.sg_api_key)
            response = sg.send(message)
            
            print(f"✅ Doctor notification sent to {doctor_email} | Status: {response.status_code}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending doctor notification: {e}")
            return False
    
    def _create_calendar_attachment(self, patient_info, appointment_details):
        """Create ICS calendar file for appointment"""
        try:
            # Parse appointment time (this is simplified - you might need more robust parsing)
            appointment_datetime = self._parse_appointment_time(appointment_details['time'])
            end_datetime = appointment_datetime + datetime.timedelta(hours=1)
            
            # Generate unique UID
            uid = f"{appointment_details['confirmationId']}@{self.clinic_name.lower().replace(' ', '')}.com"
            
            ics_content = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//{self.clinic_name}//Appointment//EN
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{appointment_datetime.strftime('%Y%m%dT%H%M%S')}
DTEND:{end_datetime.strftime('%Y%m%dT%H%M%S')}
SUMMARY:{self.clinic_name} Appointment - Dr. Lee
DESCRIPTION:Appointment with Dr. Lee\\nReason: {appointment_details['reason']}\\nConfirmation ID: {appointment_details['confirmationId']}
LOCATION:{self.clinic_address}
STATUS:CONFIRMED
SEQUENCE:0
BEGIN:VALARM
TRIGGER:-PT24H
ACTION:DISPLAY
DESCRIPTION:Appointment reminder - 24 hours
END:VALARM
BEGIN:VALARM
TRIGGER:-PT1H
ACTION:DISPLAY
DESCRIPTION:Appointment reminder - 1 hour
END:VALARM
END:VEVENT
END:VCALENDAR"""
            
            return ics_content
            
        except Exception as e:
            print(f"⚠️ Could not create calendar attachment: {e}")
            return None
    
    def _parse_appointment_time(self, time_str):
        """Parse appointment time string to datetime (simplified)"""
        # This is a simplified parser - you might want to use a library like dateparser
        base_date = datetime.datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Add logic to parse "Friday 10:00 AM", "Tomorrow 2:00 PM", etc.
        if "friday" in time_str.lower():
            days_ahead = 4 - base_date.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            base_date = base_date + datetime.timedelta(days=days_ahead)
        elif "saturday" in time_str.lower():
            days_ahead = 5 - base_date.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            base_date = base_date + datetime.timedelta(days=days_ahead)
        elif "tomorrow" in time_str.lower():
            base_date = base_date + datetime.timedelta(days=1)
        
        # Parse time
        if "2:00 pm" in time_str.lower() or "2pm" in time_str.lower():
            base_date = base_date.replace(hour=14)
        elif "11:00 am" in time_str.lower() or "11am" in time_str.lower():
            base_date = base_date.replace(hour=11)
        elif "10:00 am" in time_str.lower() or "10am" in time_str.lower():
            base_date = base_date.replace(hour=10)
        
        return base_date
    
    def _create_confirmation_email_html(self, patient_info, appointment_details):
        """Create beautiful HTML email for appointment confirmation"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Appointment Confirmation</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
            background-color: #f8f9fa;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #007bff, #0056b3);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
            font-weight: 600;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
            font-size: 18px;
        }}
        .content {{
            padding: 40px 30px;
        }}
        .confirmation-box {{
            background: #28a745;
            color: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            margin: 0 0 30px 0;
        }}
        .confirmation-id {{
            font-size: 20px;
            font-weight: bold;
            letter-spacing: 1px;
        }}
        .appointment-details {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 30px;
            margin: 30px 0;
        }}
        .detail-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #e9ecef;
        }}
        .detail-row:last-child {{
            border-bottom: none;
        }}
        .detail-label {{
            font-weight: 600;
            color: #495057;
        }}
        .detail-value {{
            color: #007bff;
            font-weight: 500;
        }}
        .important-info {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 8px;
            padding: 20px;
            margin: 30px 0;
        }}
        .important-info h3 {{
            margin: 0 0 15px 0;
            color: #856404;
            font-size: 18px;
        }}
        .important-info ul {{
            margin: 0;
            padding-left: 20px;
        }}
        .important-info li {{
            margin: 8px 0;
            color: #856404;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 30px;
            text-align: center;
            border-top: 1px solid #e9ecef;
        }}
        .footer p {{
            margin: 5px 0;
            color: #6c757d;
            font-size: 14px;
        }}
        .contact-info {{
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 20px;
            margin: 20px 0;
        }}
        @media (max-width: 600px) {{
            .content {{ padding: 20px; }}
            .appointment-details {{ padding: 20px; }}
            .detail-row {{ flex-direction: column; align-items: flex-start; }}
            .detail-value {{ margin-top: 5px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>🏥 {self.clinic_name}</h1>
            <p>Appointment Confirmation</p>
        </div>
        
        <!-- Content -->
        <div class="content">
            <div class="confirmation-box">
                <div style="font-size: 24px; margin-bottom: 10px;">✅ Appointment Confirmed!</div>
                <div class="confirmation-id">ID: {appointment_details['confirmationId']}</div>
            </div>
            
            <p style="font-size: 18px; margin-bottom: 30px;">
                Dear <strong>{patient_info['firstName']} {patient_info['lastName']}</strong>,
            </p>
            
            <p>Your appointment has been successfully scheduled. We look forward to seeing you!</p>
            
            <!-- Appointment Details -->
            <div class="appointment-details">
                <h3 style="margin: 0 0 20px 0; color: #007bff;">📋 Appointment Details</h3>
                
                <div class="detail-row">
                    <span class="detail-label">👨‍⚕️ Doctor</span>
                    <span class="detail-value">Dr. Lee</span>
                </div>
                
                <div class="detail-row">
                    <span class="detail-label">📅 Date & Time</span>
                    <span class="detail-value">{appointment_details['time']}</span>
                </div>
                
                <div class="detail-row">
                    <span class="detail-label">🩺 Reason for Visit</span>
                    <span class="detail-value">{appointment_details['reason']}</span>
                </div>
                
                <div class="detail-row">
                    <span class="detail-label">👤 Patient</span>
                    <span class="detail-value">{patient_info['firstName']} {patient_info['lastName']} ({patient_info['age']} years old)</span>
                </div>
                
                <div class="detail-row">
                    <span class="detail-label">📞 Contact</span>
                    <span class="detail-value">{patient_info['phone']}</span>
                </div>
                
                {f'''<div class="detail-row">
                    <span class="detail-label">🆔 Medical ID</span>
                    <span class="detail-value">{patient_info['medicalId']}</span>
                </div>''' if patient_info.get('medicalId') else ''}
                
                {f'''<div class="detail-row">
                    <span class="detail-label">⚠️ Allergies</span>
                    <span class="detail-value" style="color: #dc3545; font-weight: bold;">{patient_info['allergies']}</span>
                </div>''' if patient_info.get('allergies') else ''}
            </div>
            
            <!-- Important Information -->
            <div class="important-info">
                <h3>📋 Important Reminders</h3>
                <ul>
                    <li><strong>Arrive 15 minutes early</strong> for check-in and paperwork</li>
                    <li>Bring a <strong>valid government-issued ID</strong></li>
                    <li>Bring your <strong>insurance card</strong> (if applicable)</li>
                    <li>Prepare a <strong>list of current medications</strong></li>
                    <li>Wear a <strong>mask if you have cold symptoms</strong></li>
                    <li>Bring any <strong>relevant medical records</strong> or test results</li>
                </ul>
            </div>
            
            <!-- Contact Information -->
            <div class="contact-info">
                <h3 style="margin: 0 0 15px 0; color: #007bff;">📍 Clinic Information</h3>
                <p><strong>Address:</strong> {self.clinic_address}</p>
                <p><strong>Phone:</strong> {self.clinic_phone}</p>
                <p><strong>Website:</strong> <a href="https://clinic-vnpy.onrender.com">clinic-vnpy.onrender.com</a></p>
            </div>
            
            <p style="margin-top: 30px;">
                <strong>Need to reschedule or cancel?</strong><br>
                Please contact us at least 24 hours in advance to avoid any cancellation fees.
            </p>
            
            <p>
                We're committed to providing you with excellent healthcare. If you have any questions before your appointment, please don't hesitate to contact us.
            </p>
            
            <p style="margin-top: 30px;">
                Best regards,<br>
                <strong>The {self.clinic_name} Team</strong>
            </p>
        </div>
        
        <!-- Footer -->
        <div class="footer">
            <p><strong>This is an automated message.</strong> Please do not reply to this email.</p>
            <p>For questions or concerns, please contact us at {self.clinic_phone}</p>
            <p>© 2024 {self.clinic_name}. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """
    
    def _create_confirmation_email_text(self, patient_info, appointment_details):
        """Create plain text version of confirmation email"""
        return f"""
{self.clinic_name} - APPOINTMENT CONFIRMATION

Dear {patient_info['firstName']} {patient_info['lastName']},

✅ Your appointment has been successfully confirmed!

CONFIRMATION ID: {appointment_details['confirmationId']}

APPOINTMENT DETAILS:
- Doctor: Dr. Lee
- Date & Time: {appointment_details['time']}
- Reason: {appointment_details['reason']}
- Patient: {patient_info['firstName']} {patient_info['lastName']} ({patient_info['age']} years old)
- Contact: {patient_info['phone']}
{f"- Medical ID: {patient_info['medicalId']}" if patient_info.get('medicalId') else ""}
{f"- Allergies: {patient_info['allergies']}" if patient_info.get('allergies') else ""}

IMPORTANT REMINDERS:
- Arrive 15 minutes early for check-in
- Bring valid government-issued ID
- Bring insurance card (if applicable)  
- Prepare list of current medications
- Wear mask if you have cold symptoms

CLINIC INFORMATION:
Address: {self.clinic_address}
Phone: {self.clinic_phone}
Website: https://clinic-vnpy.onrender.com

Need to reschedule or cancel? Please contact us at least 24 hours in advance.

Best regards,
The {self.clinic_name} Team

---
This is an automated message. Please do not reply to this email.
For questions, please contact us at {self.clinic_phone}
        """
    
    def _create_reminder_email_html(self, patient_info, appointment_details, hours_before):
        """Create HTML reminder email"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Appointment Reminder</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
            background-color: #f8f9fa;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #f59e0b, #d97706);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        .content {{ padding: 40px 30px; }}
        .reminder-box {{
            background: #fff3cd;
            border: 2px solid #f59e0b;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            margin: 0 0 30px 0;
        }}
        .appointment-details {{
            background: #f8f9fa;
            border-radius: 12px;
            padding: 30px;
            margin: 30px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔔 Appointment Reminder</h1>
            <p>{self.clinic_name}</p>
        </div>
        
        <div class="content">
            <div class="reminder-box">
                <h2 style="margin: 0; color: #d97706;">⏰ Don't Forget!</h2>
                <p style="margin: 10px 0 0 0; font-size: 18px;">Your appointment is in {hours_before} hours</p>
            </div>
            
            <p>Dear <strong>{patient_info['firstName']}</strong>,</p>
            
            <p>This is a friendly reminder about your upcoming appointment:</p>
            
            <div class="appointment-details">
                <h3 style="color: #007bff;">📋 Appointment Details</h3>
                <p><strong>Doctor:</strong> Dr. Lee</p>
                <p><strong>Date & Time:</strong> {appointment_details['time']}</p>
                <p><strong>Reason:</strong> {appointment_details['reason']}</p>
                <p><strong>Confirmation ID:</strong> {appointment_details['confirmationId']}</p>
            </div>
            
            <p><strong>Remember to:</strong></p>
            <ul>
                <li>Arrive 15 minutes early</li>
                <li>Bring your ID and insurance card</li>
                <li>Bring list of current medications</li>
                <li>Wear a mask if you have symptoms</li>
            </ul>
            
            <p>See you soon!</p>
            <p><strong>The {self.clinic_name} Team</strong></p>
        </div>
    </div>
</body>
</html>
        """
    
    def _create_reminder_email_text(self, patient_info, appointment_details, hours_before):
        """Create plain text reminder email"""
        return f"""
{self.clinic_name} - APPOINTMENT REMINDER

Dear {patient_info['firstName']},

🔔 This is a friendly reminder about your upcoming appointment in {hours_before} hours.

APPOINTMENT DETAILS:
- Doctor: Dr. Lee  
- Date & Time: {appointment_details['time']}
- Reason: {appointment_details['reason']}
- Confirmation ID: {appointment_details['confirmationId']}

REMINDERS:
- Arrive 15 minutes early
- Bring ID and insurance card
- Bring medication list
- Wear mask if you have symptoms

See you soon!
The {self.clinic_name} Team
        """
    
    def _create_doctor_notification_html(self, patient_info, appointment_details):
        """Create HTML email for doctor notification"""
        return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; background: white; }}
        .header {{ background: #28a745; color: white; padding: 20px; text-align: center; }}
        .content {{ padding: 30px; }}
        .patient-details {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📋 New Appointment Notification</h1>
            <p>{self.clinic_name} - Doctor Portal</p>
        </div>
        
        <div class="content">
            <p>Dear Dr. Lee,</p>
            
            <p>A new appointment has been booked through the patient portal:</p>
            
            <div class="patient-details">
                <h3>Patient Information</h3>
                <p><strong>Patient:</strong> {patient_info['firstName']} {patient_info['lastName']}</p>
                <p><strong>Age:</strong> {patient_info['age']} years old ({patient_info['gender']})</p>
                <p><strong>Contact:</strong> {patient_info['phone']} | {patient_info['email']}</p>
                <p><strong>Appointment:</strong> {appointment_details['time']}</p>
                <p><strong>Chief Complaint:</strong> {appointment_details['reason']}</p>
                <p><strong>Confirmation ID:</strong> {appointment_details['confirmationId']}</p>
                {f"<p><strong>Medical ID:</strong> {patient_info['medicalId']}</p>" if patient_info.get('medicalId') else ""}
                {f'<p><strong>⚠️ Allergies:</strong> <span style="color: #dc3545; font-weight: bold;">{patient_info["allergies"]}</span></p>' if patient_info.get('allergies') else ""}
                {f"<p><strong>Emergency Contact:</strong> {patient_info['emergencyContact']} ({patient_info['emergencyPhone']})</p>" if patient_info.get('emergencyContact') else ""}
            </div>
            
            <p>The appointment has been automatically added to your Google Calendar (if connected).</p>
            
            <p>Best regards,<br><strong>{self.clinic_name} System</strong></p>
        </div>
    </div>
</body>
</html>
        """
    
    def _create_doctor_notification_text(self, patient_info, appointment_details):
        """Create plain text doctor notification"""
        return f"""
{self.clinic_name} - NEW APPOINTMENT NOTIFICATION

Dear Dr. Lee,

A new appointment has been booked through the patient portal:

PATIENT INFORMATION:
- Name: {patient_info['firstName']} {patient_info['lastName']}
- Age: {patient_info['age']} years old ({patient_info['gender']})
- Contact: {patient_info['phone']} | {patient_info['email']}
- Appointment: {appointment_details['time']}
- Chief Complaint: {appointment_details['reason']}
- Confirmation ID: {appointment_details['confirmationId']}
{f"- Medical ID: {patient_info['medicalId']}" if patient_info.get('medicalId') else ""}
{f"- Allergies: {patient_info['allergies']}" if patient_info.get('allergies') else ""}
{f"- Emergency Contact: {patient_info['emergencyContact']} ({patient_info['emergencyPhone']})" if patient_info.get('emergencyContact') else ""}

The appointment has been automatically added to your Google Calendar (if connected).

Best regards,
{self.clinic_name} System
        """