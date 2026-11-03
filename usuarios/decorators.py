from functools import wraps
from django.shortcuts import redirect


def admin_requerido(view_func):
    """
    Solo permite el acceso a administradores y superusuarios.
    Si el usuario no tiene permisos, lo redirige al login.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('usuarios:login_admin')

        if not (
            getattr(request.user, 'es_admin', False)
            or request.user.is_superuser
        ):
            return redirect('usuarios:login_admin')

        return view_func(request, *args, **kwargs)

    return _wrapped
