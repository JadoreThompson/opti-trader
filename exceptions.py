class DoesNotExist(Exception):
    def __init__(self, resource=None, message=None):
        if resource:
            self.message = f"{resource} does not exist"
        if message:
            self.message = message
        super().__init__(self.message)


class DuplicateError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class InvalidAction(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
                        

class UnauthorisedError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)
