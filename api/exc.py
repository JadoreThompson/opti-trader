class InvalidJWT(Exception):
    """Exception raised when JWT authentication has failed"""
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
