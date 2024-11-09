from datetime import datetime, timedelta
from urllib.request import Request

from starlette.middleware.base import RequestResponseEndpoint, BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from config import API_KEY_ALIAS

_EXCLUDED_PATHS = [
    '/accounts', '/'
]

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track and limit the rate of requests based on API key.

    Attributes:
        _TIME_LIMIT (timedelta): Time window for rate limiting.
        _REQUEST_LIMIT (int): Maximum allowed requests within the time window.
        request_counter (dict): Dictionary to track request counts and timestamps by API key.
    """

    _TIME_LIMIT = timedelta(minutes=1)
    _REQUEST_LIMIT = 10 ** 5

    def __init__(self, app):
        super().__init__(app)
        self.request_counter = {}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """
        Processes incoming requests, enforces rate limiting based on API key, and returns response.

        Args:
            request (Request): Incoming HTTP request.
            call_next (RequestResponseEndpoint): Callable to pass the request to the next middleware
        Returns:
            Response: JSON response if rate limit is exceeded, otherwise the standard response.
        Raises:
            JSONResponse: Returns a 401 status code if the rate limit is reached for a given API key.
        """

        if not any(request.url.path.startswith(path) for path in _EXCLUDED_PATHS):
            response = await call_next(request)
            return response

        ip_address = request.client.host
        self.request_counter.setdefault(ip_address, [0, datetime.now()])
        api_usage = self.request_counter.get(ip_address)

        # Rate limit checks
        if (datetime.now() - api_usage[1]) < self._TIME_LIMIT and api_usage[0] >= self._REQUEST_LIMIT:
            return JSONResponse(status_code=401, content={'Error': 'Rate Limit reached'})

        if (datetime.now() - api_usage[1]) >= self._TIME_LIMIT and api_usage[0] >= self._REQUEST_LIMIT:
            self.request_counter[ip_address] = [0, datetime.now()]

        if (datetime.now() - api_usage[1]) < self._TIME_LIMIT and api_usage[0] != 5:
            self.request_counter[ip_address][0] += 1

        response = await call_next(request)
        return response
