import smtplib
from email.mime.text import MIMEText

sender_email = "vikalp.singh@gmail.com"
app_password = "your_app_password"   # Generate from Google account security settings
receiver_email = "meshanti.singh@gmail.com"

subject = "Test Email"
body = "This is test email from Python."

msg = MIMEText(body)
msg['Subject'] = subject
msg['From'] = sender_email
msg['To'] = receiver_email

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls()
    server.login(sender_email, app_password)
    server.sendmail(sender_email, receiver_email, msg.as_string())

print("Email sent successfully!")
