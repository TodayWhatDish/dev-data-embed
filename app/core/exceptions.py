# Last Updated: 2026-09-24

"""services가 '왜 거절했는지'를 종류로 올린다. 
HTTP 상태는 api/errors.py가 정한다.
"""

class AppError(Exception):
    """모든 업무 예외의 부모가 되며, message는 사용자에게 그대로 보여도 되는 문장만 담는다."""

    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg


class InvalidInput(AppError): ...
class Unauthorized(AppError): ...
class Forbidden(AppError): ...
class NotFound(AppError): ...
class Conflict(AppError): ...