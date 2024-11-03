class DoesNotExist(Exception):
    def __init__(self, resource):
        self.message = f"{resource} does not exist"
        super().__init__(self.message)


class InvalidError(Exception):
    def __init__(self, message):
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
                        