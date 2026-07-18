"""
core/urls_recovery.py
=====================
Sub-enrutador para resolver /api/v1/auth/password/ directo al servicio de recuperación.
"""
from django.urls import path
from core.views.password_recovery import send_recovery_code, verify_recovery_code, reset_password

urlpatterns = [
    path("send-code",   send_recovery_code,   name="auth_password_send_code"),
    path("send-code/",  send_recovery_code,   name="auth_password_send_code_slash"),
    path("verify-code", verify_recovery_code, name="auth_password_verify_code"),
    path("verify-code/", verify_recovery_code, name="auth_password_verify_code_slash"),
    path("reset",       reset_password,       name="auth_password_reset"),
    path("reset/",      reset_password,       name="auth_password_reset_slash"),
]
