from typing import overload


class BaseMailer:
    def __init__(self) -> None:
        pass
    
    @overload
    def send_email(self, to: list[str], subject: str, body: str) -> None: ...
    
    @overload
    def send_email_with_attachment(self, to: list[str], subject: str, body: str, attchment_paths: list[str]) -> None: ...