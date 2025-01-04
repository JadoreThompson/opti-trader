from typing import override

class BaseMailer:
    def __init__(self) -> None:
        pass
    
    @override
    def send_email(self, to: list[str], subject: str, body: str) -> None: ...
    
    @override
    def send_email_with_attachment(self, to: list[str], subject: str, body: str, attchment_paths: list[str]) -> None: ...