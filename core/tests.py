from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase, Client
from django.urls import reverse
from core.security import JWTService, PasswordService
from core.repositories.notifications import NotificationDocument


class AuthViewsTests(SimpleTestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse("core:auth_register")
        self.login_url = reverse("core:auth_login")
        self.me_url = reverse("core:auth_me")

    def test_register_missing_fields(self):
        response = self.client.post(
            self.register_url,
            data={"email": "test@test.com"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    @patch("core.views.auth.UserRepository")
    def test_register_duplicate_email(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.email_exists.return_value = True
        mock_repo_cls.return_value = mock_repo

        response = self.client.post(
            self.register_url,
            data={
                "email": "existente@jalisco.mx",
                "password": "secretpassword",
                "nombre": "Juan Pérez",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("El email ya está registrado", response.json().get("error", ""))

    @patch("core.views.auth.UserRepository")
    @patch("core.security.settings")
    def test_register_success(self, mock_settings, mock_repo_cls):
        mock_settings.SECRET_KEY = "test_secret_key_for_jwt"
        mock_repo = MagicMock()
        mock_repo.email_exists.return_value = False
        mock_repo.create_user.return_value = "507f1f77bcf86cd799439011"

        mock_user = MagicMock()
        mock_user.id = "507f1f77bcf86cd799439011"
        mock_user.email = "nuevo@jalisco.mx"
        mock_user.rol = "turista"
        mock_user.nombre = "Juan Pérez"
        mock_repo.get_by_id.return_value = mock_user
        mock_repo_cls.return_value = mock_repo

        response = self.client.post(
            self.register_url,
            data={
                "email": "nuevo@jalisco.mx",
                "password": "secretpassword",
                "nombre": "Juan Pérez",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["user"]["email"], "nuevo@jalisco.mx")

    @patch("core.security.settings")
    @patch("core.views.auth.UserRepository")
    def test_me_put_update_profile(self, mock_repo_cls, mock_settings):
        mock_settings.SECRET_KEY = "test_secret_key_for_jwt"
        token = JWTService.encode({"id": "507f1f77bcf86cd799439011", "rol": "turista"})

        mock_repo = MagicMock()
        mock_user = MagicMock()
        mock_user.to_safe_dict.return_value = {
            "id": "507f1f77bcf86cd799439011",
            "email": "turista@jalisco.mx",
            "nombre": "Juan Actualizado",
            "preferences": {"telefono": "3312345678"},
        }
        mock_repo.update_profile.return_value = mock_user
        mock_repo_cls.return_value = mock_repo

        response = self.client.put(
            self.me_url,
            data={"nombre": "Juan Actualizado", "telefono": "3312345678"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["nombre"], "Juan Actualizado")


# ===========================================================================
# Fase 2 — Módulo de Favoritos
# ===========================================================================

class FavoritesViewsTests(SimpleTestCase):
    """Tests de integración para los endpoints de Favoritos."""

    def setUp(self):
        self.client = Client()
        self.favorites_url = reverse("core:favorites_list_create")

        # Parchear settings.SECRET_KEY de forma persistente durante todo el test.
        # Necesario porque tanto la generación del token como el decorador
        # @jwt_required llaman a JWTService._get_secret() → settings.SECRET_KEY.
        self.settings_patcher = patch(
            "core.security.settings",
            SECRET_KEY="supersecretkey_at_least_32chars_long_for_test",
        )
        self.settings_patcher.start()
        self.addCleanup(self.settings_patcher.stop)

        self.token = JWTService.encode(
            {"id": "aabbccddeeff001122334455", "rol": "turista"}
        )
        self.auth_header = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}


    # ── GET /core/favorites/ ─────────────────────────────────────────── #

    @patch("core.views.favorites.FavoriteRepository")
    def test_get_favorites_returns_list(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.get_by_user.return_value = []
        mock_repo_cls.return_value = mock_repo

        response = self.client.get(self.favorites_url, **self.auth_header)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"], [])
        self.assertEqual(data["count"], 0)

    def test_get_favorites_unauthenticated_returns_401(self):
        response = self.client.get(self.favorites_url)
        self.assertEqual(response.status_code, 401)

    # ── POST /core/favorites/ ────────────────────────────────────────── #

    @patch("core.views.favorites.FavoriteRepository")
    def test_post_favorite_success(self, mock_repo_cls):
        from core.repositories.favorites import FavoriteDocument

        mock_repo = MagicMock()
        mock_repo.already_saved.return_value = False

        real_fav = FavoriteDocument(
            id="aab001",
            user_id="aabbccddeeff001122334455",
            tipo="lugar",
            referencia_id="68793a2b04b8fc29f0c4a2e1",
            created_at="2026-07-17T00:00:00+00:00",
        )
        mock_repo.add_favorite.return_value = real_fav
        mock_repo_cls.return_value = mock_repo

        response = self.client.post(
            self.favorites_url,
            data={"tipo": "lugar", "referencia_id": "68793a2b04b8fc29f0c4a2e1"},
            content_type="application/json",
            **self.auth_header,
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])

    @patch("core.views.favorites.FavoriteRepository")
    def test_post_favorite_invalid_tipo_returns_400(self, mock_repo_cls):
        mock_repo_cls.return_value = MagicMock()

        response = self.client.post(
            self.favorites_url,
            data={"tipo": "invalid_type", "referencia_id": "abc123"},
            content_type="application/json",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 400)

    # ── DELETE /core/favorites/<referencia_id>/ ──────────────────────── #

    @patch("core.views.favorites.FavoriteRepository")
    def test_delete_favorite_success(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.remove_favorite.return_value = True
        mock_repo_cls.return_value = mock_repo

        url = reverse("core:favorites_delete", args=["68793a2b04b8fc29f0c4a2e1"])
        response = self.client.delete(url, **self.auth_header)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

    @patch("core.views.favorites.FavoriteRepository")
    def test_delete_favorite_not_found_returns_404(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.remove_favorite.return_value = False
        mock_repo_cls.return_value = mock_repo

        url = reverse("core:favorites_delete", args=["non_existent_id"])
        response = self.client.delete(url, **self.auth_header)
        self.assertEqual(response.status_code, 404)


# ===========================================================================
# Fase 3 — Admin CRUD
# ===========================================================================

class AdminCRUDTests(SimpleTestCase):

    def setUp(self):
        self.client = Client()
        self.settings_patcher = patch(
            "core.security.settings",
            SECRET_KEY="supersecretkey_at_least_32chars_long_for_test",
        )
        self.settings_patcher.start()
        self.addCleanup(self.settings_patcher.stop)

        self.admin_token = JWTService.encode({"id": "admin001", "rol": "admin"})
        self.user_token  = JWTService.encode({"id": "user001",  "rol": "turista"})
        self.admin_header = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        self.user_header  = {"HTTP_AUTHORIZATION": f"Bearer {self.user_token}"}

    # ── Rol insuficiente → 403 ───────────────────────────────────────── #

    def test_create_resource_non_admin_returns_403(self):
        url = reverse("core:admin_resource_create", args=["places"])
        response = self.client.post(
            url, data={"nombre": "Test"}, content_type="application/json",
            **self.user_header,
        )
        self.assertEqual(response.status_code, 403)

    # ── Recurso inexistente → 404 ────────────────────────────────────── #

    def test_create_unknown_resource_returns_404(self):
        url = reverse("core:admin_resource_create", args=["unknown"])
        response = self.client.post(
            url, data={"nombre": "Test"}, content_type="application/json",
            **self.admin_header,
        )
        self.assertEqual(response.status_code, 404)

    # ── POST /admin/places/ → 201 ────────────────────────────────────── #

    @patch("core.repositories.places.PlaceRepository")
    def test_create_place_success(self, mock_repo_cls):
        from core.repositories.places import PlaceDocument
        mock_repo = MagicMock()
        mock_repo.create_place.return_value = PlaceDocument(
            id="pid001", nombre="Bosque La Primavera", municipio="Zapopan",
        )
        mock_repo_cls.return_value = mock_repo

        url = reverse("core:admin_resource_create", args=["places"])
        response = self.client.post(
            url,
            data={"nombre": "Bosque La Primavera", "municipio": "Zapopan"},
            content_type="application/json",
            **self.admin_header,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["success"])

    # ── DELETE /admin/places/<id>/delete/ → 200 ──────────────────────── #

    @patch("core.repositories.places.PlaceRepository")
    def test_delete_place_success(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.delete_place.return_value = True
        mock_repo_cls.return_value = mock_repo

        url = reverse("core:admin_resource_delete", args=["places", "pid001"])
        response = self.client.delete(url, **self.admin_header)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    # ── DELETE → 404 cuando soft-delete no tiene efecto ──────────────── #

    @patch("core.repositories.places.PlaceRepository")
    def test_delete_place_not_found_returns_404(self, mock_repo_cls):
        mock_repo = MagicMock()
        mock_repo.delete_place.return_value = False
        mock_repo_cls.return_value = mock_repo

        url = reverse("core:admin_resource_delete", args=["places", "nonexistent"])
        response = self.client.delete(url, **self.admin_header)
        self.assertEqual(response.status_code, 404)


# ===========================================================================
# Fase 4 — Estadísticas y Backup
# ===========================================================================

class StatsAndBackupTests(SimpleTestCase):

    def setUp(self):
        self.client = Client()
        self.settings_patcher = patch(
            "core.security.settings",
            SECRET_KEY="supersecretkey_at_least_32chars_long_for_test",
        )
        self.settings_patcher.start()
        self.addCleanup(self.settings_patcher.stop)

        self.admin_token = JWTService.encode({"id": "admin001", "rol": "admin"})
        self.user_token  = JWTService.encode({"id": "user001",  "rol": "turista"})
        self.admin_header = {"HTTP_AUTHORIZATION": f"Bearer {self.admin_token}"}
        self.user_header  = {"HTTP_AUTHORIZATION": f"Bearer {self.user_token}"}

    # ── /admin/stats/ ────────────────────────────────────────────────── #

    def test_stats_non_admin_returns_403(self):
        url = reverse("core:admin_stats")
        response = self.client.get(url, **self.user_header)
        self.assertEqual(response.status_code, 403)

    @patch("core.views.stats.MongoDBClient")
    def test_stats_returns_structure(self, mock_client_cls):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.count_documents.return_value = 10
        mock_db.__getitem__.return_value.aggregate.return_value = [
            {"_id": "turista", "count": 8},
            {"_id": "admin",   "count": 2},
        ]
        mock_client_cls.get_database.return_value = mock_db

        url = reverse("core:admin_stats")
        response = self.client.get(url, **self.admin_header)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("totales", data["data"])
        self.assertIn("roles",   data["data"])
        self.assertIn("lugares", data["data"]["totales"])

    # ── /admin/backup/<resource>/ ─────────────────────────────────────── #

    def test_backup_non_admin_returns_403(self):
        url = reverse("core:admin_backup_export", args=["all"])
        response = self.client.get(url, **self.user_header)
        self.assertEqual(response.status_code, 403)

    def test_backup_invalid_resource_returns_400(self):
        url = reverse("core:admin_backup_export", args=["unknown_resource"])
        response = self.client.get(url, **self.admin_header)
        self.assertEqual(response.status_code, 400)

    @patch("core.views.backup.MongoDBClient")
    def test_backup_all_returns_json_attachment(self, mock_client_cls):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.find.return_value = []
        mock_client_cls.get_database.return_value = mock_db

        url = reverse("core:admin_backup_export", args=["all"])
        response = self.client.get(url, **self.admin_header)
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])
        self.assertIn("attachment", response["Content-Disposition"])
        body = response.json()
        self.assertIn("places", body)

    @patch("core.views.backup.MongoDBClient")
    def test_backup_single_resource_returns_json(self, mock_client_cls):
        mock_db = MagicMock()
        mock_db.__getitem__.return_value.find.return_value = [
            {"_id": "abc123", "nombre": "Bosque"},
        ]
        mock_client_cls.get_database.return_value = mock_db

        url = reverse("core:admin_backup_export", args=["places"])
        response = self.client.get(url, **self.admin_header)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("places", body)
        self.assertEqual(len(body["places"]), 1)
        self.assertEqual(body["places"][0]["id"], "abc123")


# ===========================================================================
# Fase 5 — Notificaciones
# ===========================================================================

class NotificationViewsTests(SimpleTestCase):

    def setUp(self):
        self.client = Client()
        self.settings_patcher = patch(
            "core.security.settings",
            SECRET_KEY="supersecretkey_at_least_32chars_long_for_test",
        )
        self.settings_patcher.start()
        self.addCleanup(self.settings_patcher.stop)

        self.user_token = JWTService.encode({"id": "user001", "rol": "turista"})
        self.user_header = {"HTTP_AUTHORIZATION": f"Bearer {self.user_token}"}
        self.list_url = reverse("core:notifications_list_create_delete")
        self.read_all_url = reverse("core:notification_mark_all_read")

    @patch("core.views.notifications._get_repo")
    def test_get_notifications_returns_list(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.get_by_user.return_value = [
            NotificationDocument(
                id="notif1",
                user_id="user001",
                titulo="Bienvenido",
                mensaje="Hola",
                leido=False,
                tipo="info",
                created_at="2026-07-17T20:00:00Z",
            )
        ]
        mock_get_repo.return_value = mock_repo

        response = self.client.get(self.list_url, **self.user_header)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["data"]), 1)
        self.assertEqual(data["data"][0]["titulo"], "Bienvenido")

    @patch("core.views.notifications._get_repo")
    def test_create_notification_success(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.create_notification.return_value = NotificationDocument(
            id="notif2",
            user_id="user001",
            titulo="Alerta",
            mensaje="Revisa tu perfil",
            leido=False,
            tipo="alerta",
            created_at="2026-07-17T20:05:00Z",
        )
        mock_get_repo.return_value = mock_repo

        payload = {"titulo": "Alerta", "mensaje": "Revisa tu perfil", "tipo": "alerta"}
        response = self.client.post(
            self.list_url, data=payload, content_type="application/json", **self.user_header
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["id"], "notif2")

    @patch("core.views.notifications._get_repo")
    def test_mark_as_read_success(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.mark_as_read.return_value = NotificationDocument(
            id="notif1",
            user_id="user001",
            titulo="Bienvenido",
            mensaje="Hola",
            leido=True,
            tipo="info",
            created_at="2026-07-17T20:00:00Z",
        )
        mock_get_repo.return_value = mock_repo

        url = reverse("core:notification_mark_read", args=["notif1"])
        response = self.client.patch(url, **self.user_header)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["leido"])

    @patch("core.views.notifications._get_repo")
    def test_mark_all_as_read_success(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.mark_all_as_read.return_value = 3
        mock_get_repo.return_value = mock_repo

        response = self.client.patch(self.read_all_url, **self.user_header)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["modified"], 3)

    @patch("core.views.notifications._get_repo")
    def test_delete_notification_success(self, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.delete_for_user.return_value = True
        mock_get_repo.return_value = mock_repo

        url = reverse("core:notification_detail", args=["notif1"])
        response = self.client.delete(url, **self.user_header)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["deleted"])




