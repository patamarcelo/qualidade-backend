from django.core.cache import cache
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model
from rest_framework.authentication import TokenAuthentication
from django.contrib.auth.models import AnonymousUser

User = get_user_model()

class AdminTokenAuthenticationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        # Only apply token authentication in the admin panel
        if request.path.startswith('/admin/'):
            # Get the token from request headers
            token_key = request.META.get("HTTP_AUTHORIZATION")
            
            if token_key:
                token_key = token_key.split(" ")[1]  # Assuming "Token <token_value>"
                
                # Check if token is in cache
                cached_user = cache.get(f"token_{token_key}")
                if cached_user:
                    request.user = cached_user
                    print('User em cache')
                    return
                
                # If token is not in cache, authenticate it
                auth = TokenAuthentication()
                result = auth.authenticate(request)
                
                if result:
                    user, _ = result
                    cache.set(f"token_{token_key}", user, timeout=3600*24)  # Cache user for 1 hour
                    request.user = user
                    return
                
                # If token is invalid, set user to anonymous
                request.user = AnonymousUser()
            else:
                token_key = request.META.get("HTTP_AUTHORIZATION")
                print('token_key: %s' % token_key)
                # No token provided, anonymous user
                request.user = AnonymousUser()