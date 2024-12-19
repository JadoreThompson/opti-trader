import os
import asyncio
import base64
import logging

# Google
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Official Email
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Local
from mailers.base import BaseMailer


logger = logging.getLogger(__name__)


class GMailer(BaseMailer):
    def __init__(self) -> None:
        self.service = None
        super().__init__()
    
    async def create_service_async(self, scopes: list[str], client_secret_path: str, prefix: str='',):
        await asyncio.to_thread(self.create_service, **locals())
    
    def create_service(self, scopes: list[str], client_secret_path: str, prefix: str='') -> None:
        """
        Handles service creation for api_name

        Args:
            api_name (str): E.g. Gmail API
            api_version: E.g. v1 or v2
            scopes (list[str])
            prefix (str, optional): Applied to the name of the token file that'll be created.
                                    Defaults to ''.

        Raises:
            ValueError: At least 1 scope value isn't a string or scopes isn't of type list
        """        
        if not isinstance(scopes, list):
            raise ValueError("Scopes must be of type list")
        
        if not all(isinstance(scope, str) for scope in scopes):
            raise ValueError('All scopes must be of type str')
        
        
        creds = None
        working_dir = os.getcwd()
        api_name = 'gmail'
        api_version = 'v1'
        
        token_dir = 'tokens'
        token_file = f'token_{api_name}_{api_version}_{prefix}.json' # Oauth2 credentials
        
        if not os.path.exists(os.path.join(working_dir, token_dir)):
            os.mkdir(os.path.join(working_dir, token_dir))
            
        if os.path.exists(os.path.join(working_dir, token_dir, token_file)):
            creds = Credentials.from_authorized_user_file(
                os.path.join(working_dir, token_dir, token_file), 
                scopes
            )
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, scopes)
                creds = flow.run_local_server(port=0)
                
            with open(os.path.join(working_dir, token_dir, token_file), 'w') as f:
                f.write(creds.to_json())

        try:
            self.service = build(
                api_name, 
                api_version,
                credentials=creds,
                static_discovery=False,
            )
            
            print(api_name, api_version, 'service created successfully -_-')
        except Exception as e:
            logger.error(f'{type(e)} - {str(e)}')
            os.remove(os.path.join(working_dir, token_dir, token_file))

    async def send_email_async(self, to: list[str], subject: str, body: str, body_type: str='plain'):
        params = locals()
        del params['self']
        await asyncio.to_thread(self.send_email, **params)

    def send_email(self, to: list[str], subject: str, body: str, body_type: str='plain') -> None:
        try:
            if self.service is None:
                raise ValueError('Must initialise service first')
            
            body_type = body_type.lower()
            if body_type not in ['plain', 'html']:
                raise ValueError('Body type must be either plain or html')
            
            for recipient in to:
                msg = MIMEMultipart()
                msg['to'] = recipient
                msg['subject'] = subject
                
                msg.attach(MIMEText(body, body_type))
                
                raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
                self.service.users().messages().send(userId='me', body={'raw': raw_msg}).execute()
        except Exception as e:
            logger.error('{} - {}'.format(type(e), str(e)))
        
    async def send_email_with_attachment_async(self, to: list[str], subject: str, body: str, attchment_paths: list[str]) -> None:
        params = locals()
        del params['self']
        await asyncio.to_thread(self.send_email_with_attachment_async, **params)
        
    def send_email_with_attachment_async(self, to: list[str], subject: str, body: str, attchment_paths: list[str]) -> None:
        if self.service is None:
            raise ValueError('Must initialise service first')
        
        body_type = body_type.lower()
        if body_type not in ['plain', 'html']:
            raise ValueError('Body type must be either plain or html')
        
        for recipient in to:
            msg = MIMEMultipart()
            msg['to'] = recipient
            msg['subject'] = subject
            
            msg.attach(MIMEText(body, body_type))
            
            for path in attchment_paths:
                if os.path.exists(path):
                    with open(path, 'rb') as f:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(f.read())
                    
                    encoders.encode_base64(part)
                    
                    part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(path)}')
                    msg.attach(part)
                else:
                    raise FileNotFoundError(f'{path} not found')
                            
            raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
            self.service.users().messages().send(userId='me', body={'raw': raw_msg}).execute()
            
###### End of Class ######
