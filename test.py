import base64
from email.message import EmailMessage
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def send_email(subject, body, recipient, file=None):
    creds, _ = google.auth.default()

    try:
        service = build("gmail", "v1", credentials=creds)

        message = EmailMessage()
        message.set_content(body)
        message["To"] = recipient
        message["From"] = 'optitrader0001@gmail.com'
        message["Subject"] = subject

        # if file is not None:
        #     if os.path.exists(file):
        #         with open(file, 'rb') as f:
        #             pdf_data = f.read()
        #             message.add_attachment(pdf_data, maintype='application', subtype='pdf', filename=file)
        #         os.remove(file)


        # encoded message
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        create_message = {"raw": encoded_message}
        send_message = (
            service.users()
            .messages()
            .send(userId="me", body=create_message)
            .execute()
        )

    except HttpError as error:
        print(f"An error occurred: {error}")
