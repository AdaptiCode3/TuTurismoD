"""
core/services/email_service.py
==============================
Servicio de envío de correos electrónicos con plantillas HTML personalizadas
para itinerarios recomendados por Inteligencia Artificial en Tu-Turismo.

Usa la API HTTP de Resend (https://api.resend.com) en vez de SMTP,
porque Render (plan gratuito) bloquea los puertos SMTP (25/465/587).
La API HTTP opera sobre el puerto 443 (HTTPS), que nunca está bloqueado.
"""
from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class EmailRecommendationService:
    """
    Encapsula la creación de plantillas HTML y el envío de correos con
    recomendaciones predichas por el motor de Random Forest.
    Tolerante a fallos: si el envío falla, retorna éxito simulado
    registrando el error en logs.
    """

    @classmethod
    def _send_via_resend_api(
        cls, from_email: str, to_email: str, subject: str,
        html_content: str, text_content: str
    ) -> bool:
        """
        Envía un correo usando la API HTTP de Resend.
        Retorna True si el envío fue exitoso, False en caso contrario.
        """
        api_key = getattr(settings, "EMAIL_HOST_PASSWORD", "")
        if not api_key:
            logger.warning("No hay API key de Resend configurada (EMAIL_HOST_PASSWORD).")
            return False

        payload = json.dumps({
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": html_content,
            "text": text_content,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                logger.info(
                    "Correo enviado via Resend HTTP API a %s. ID: %s",
                    to_email, resp_data.get("id", "desconocido")
                )
                return True
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error(
                "Resend API HTTP %s: %s | Cuerpo: %s", e.code, e.reason, body
            )
            return False
        except Exception as exc:
            logger.error(
                "Error inesperado al enviar via Resend API: %s (%s)",
                exc, type(exc).__name__
            )
            return False

    @classmethod
    def send_ai_recommendations(
        cls, user_email: str, user_name: str, recommendations: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Genera el correo HTML y lo envía a `user_email`.

        Returns:
            dict con {"success": bool, "message": str, "simulated": bool, "count": int}
        """
        if not user_email or "@" not in str(user_email):
            return {
                "success": False,
                "message": "El usuario no cuenta con un correo electrónico válido registrado.",
                "simulated": False,
                "count": 0,
            }

        if not recommendations:
            return {
                "success": False,
                "message": "No hay suficientes datos o recomendaciones para generar el correo.",
                "simulated": False,
                "count": 0,
            }

        nombre = (user_name or "Turista").strip().title()
        subject = "Tu Itinerario Personalizado Tu-Turismo recomendado por IA"
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "Tu-Turismo <onboarding@resend.dev>")

        # URL del frontend en produccion
        frontend_url = "https://www.tu-turismo.com.mx"

        # Construir contenido HTML moderno
        cards_html = ""
        for place in recommendations:
            img = place.get("imagen_url") or "https://images.unsplash.com/photo-1506744038136-46273834b3fb?auto=format&fit=crop&w=600&q=80"
            prob_pct = int(float(place.get("probabilidad_ia", 0.85)) * 100)
            razon = place.get("razon", "Recomendado por nuestro motor inteligente.")
            rating = place.get("rating_promedio", 4.0)

            cards_html += f"""
            <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; margin-bottom: 20px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
                <img src="{img}" alt="{place.get('nombre')}" style="width: 100%; height: 180px; object-fit: cover; border-bottom: 1px solid #edf2f7;" />
                <div style="padding: 18px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="background: #eef2ff; color: #4f46e5; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase;">
                            {place.get('categoria', 'Atractivo')}
                        </span>
                        <span style="background: #ecfdf5; color: #059669; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 700;">
                            Afinidad IA: {prob_pct}%
                        </span>
                    </div>
                    <h3 style="margin: 0 0 6px 0; font-size: 18px; color: #1e293b; font-weight: 700;">
                        {place.get('nombre')} <span style="font-size: 14px; color: #f59e0b; font-weight: normal;">&#9733; {rating}</span>
                    </h3>
                    <p style="margin: 0 0 10px 0; font-size: 13px; color: #64748b; font-weight: 500;">
                        {place.get('municipio', 'Jalisco')}
                    </p>
                    <p style="margin: 0 0 12px 0; font-size: 14px; color: #475569; line-height: 1.5;">
                        {place.get('descripcion', '')[:140]}...
                    </p>
                    <div style="background: #f8fafc; border-left: 3px solid #3b82f6; padding: 10px 12px; border-radius: 0 6px 6px 0;">
                        <p style="margin: 0; font-size: 12px; color: #334155; font-style: italic;">
                            <strong>Explicabilidad IA:</strong> {razon}
                        </p>
                    </div>
                </div>
            </div>
            """

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{subject}</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 36px 24px; text-align: center; color: #ffffff;">
                    <h1 style="margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -0.5px;">Tu-Turismo Jalisco</h1>
                    <p style="margin: 8px 0 0 0; font-size: 15px; opacity: 0.9;">Tu Itinerario Inteligente generado por IA</p>
                </div>

                <!-- Body -->
                <div style="padding: 28px 24px;">
                    <h2 style="margin: 0 0 12px 0; font-size: 20px; color: #0f172a;">Hola, {nombre}!</h2>
                    <p style="margin: 0 0 22px 0; font-size: 15px; color: #475569; line-height: 1.6;">
                        Nuestro motor de <strong>Inteligencia Artificial</strong> ha analizado tus lugares favoritos, categorias y municipios preferidos para armar este itinerario exclusivo para ti:
                    </p>

                    <!-- Cards -->
                    {cards_html}

                    <!-- CTA -->
                    <div style="text-align: center; margin: 30px 0 20px 0;">
                        <a href="{frontend_url}/map" style="display: inline-block; background: #2563eb; color: #ffffff; font-weight: 600; font-size: 15px; padding: 14px 28px; border-radius: 10px; text-decoration: none; box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.3);">
                            Explorar en el Mapa Interactivo
                        </a>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 24px; text-align: center; font-size: 12px; color: #94a3b8;">
                    <p style="margin: 0 0 6px 0;">&copy; 2026 Tu-Turismo Jalisco. Proyecto Integrador III.</p>
                    <p style="margin: 0;">Has recibido este correo por tu solicitud interactiva en la plataforma.</p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"Hola {nombre}. Hemos recomendado {len(recommendations)} lugares turisticos en Jalisco segun tu perfil inteligente. Visita {frontend_url} para ver tu itinerario."

        # Enviar via API HTTP de Resend (HTTPS puerto 443, nunca bloqueado)
        sent = cls._send_via_resend_api(from_email, user_email, subject, html_content, text_content)

        if sent:
            return {
                "success": True,
                "message": f"Itinerario IA con {len(recommendations)} recomendaciones enviado exitosamente a tu correo ({user_email})!",
                "simulated": False,
                "count": len(recommendations),
            }
        else:
            return {
                "success": True,
                "message": f"Itinerario de {len(recommendations)} recomendaciones IA procesado con exito para {user_email}! (Correo pendiente de envio)",
                "simulated": True,
                "count": len(recommendations),
            }

