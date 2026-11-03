from functools import wraps
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def admin_requerido(view_func):
    """Solo deja pasar a administradores (es_admin) o superusuarios.
    - Sin sesión: redirige al login de administrador.
    - Con sesión pero sin rol de admin (ej: un cliente): error 403."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url='usuarios:login_admin')
        if not (getattr(request.user, 'es_admin', False) or request.user.is_superuser):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped
