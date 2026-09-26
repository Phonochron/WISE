import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from werkzeug.security import check_password_hash

from deploy import prepare_deployment
from app import app, _client_rate_key
from wise_ai.data_store import get_user_by_name


class DeployTests(unittest.TestCase):
    def test_bootstrap_uses_volume_and_does_not_reset_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = {
                "PORT": "8080", "RAILWAY_VOLUME_MOUNT_PATH": directory,
                "WISE_AUTH_REQUIRED": "true", "WISE_SECURE_COOKIES": "true",
                "WISE_SECRET_KEY": "s" * 48, "WISE_BOOTSTRAP_ADMIN_USERNAME": "admin",
                "WISE_BOOTSTRAP_ADMIN_PASSWORD": "first-deploy-password-2026",
            }
            self.assertEqual(prepare_deployment(settings), 8080)
            database = Path(directory) / "wise.db"
            self.assertEqual(settings["WISE_DATABASE_PATH"], str(database))
            self.assertNotIn("WISE_BOOTSTRAP_ADMIN_PASSWORD", settings)
            account = get_user_by_name(database, "admin")
            self.assertTrue(check_password_hash(account["password_hash"], "first-deploy-password-2026"))
            self.assertEqual(prepare_deployment(settings), 8080)
            self.assertEqual(get_user_by_name(database, "admin")["password_hash"], account["password_hash"])

    def test_rejects_missing_volume_and_unsafe_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = {
                "PORT": "8080", "RAILWAY_VOLUME_MOUNT_PATH": directory,
                "WISE_AUTH_REQUIRED": "true", "WISE_SECURE_COOKIES": "true",
                "WISE_SECRET_KEY": "s" * 48,
                "WISE_BOOTSTRAP_ADMIN_PASSWORD": "first-deploy-password-2026",
            }
            for change, message in [
                ({"PORT": "nope"}, "PORT"),
                ({"RAILWAY_VOLUME_MOUNT_PATH": ""}, "volume"),
                ({"WISE_AUTH_REQUIRED": "false"}, "WISE_AUTH_REQUIRED"),
                ({"WISE_SECURE_COOKIES": "false"}, "WISE_SECURE_COOKIES"),
                ({"WISE_SECRET_KEY": "short"}, "WISE_SECRET_KEY"),
                ({"WISE_DEBUG": "true"}, "WISE_DEBUG"),
                ({"WISE_BOOTSTRAP_ADMIN_PASSWORD": "short"}, "WISE_BOOTSTRAP_ADMIN_PASSWORD"),
            ]:
                with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, message):
                    prepare_deployment({**valid, **change})

    def test_rate_limit_key_uses_railway_client_ip_only_in_deployment(self):
        with app.test_request_context("/login", headers={"X-Real-IP": "203.0.113.8"}, environ_base={"REMOTE_ADDR": "127.0.0.1"}):
            with patch.dict("os.environ", {}, clear=True):
                self.assertEqual(_client_rate_key(), "127.0.0.1")
            with patch.dict("os.environ", {"RAILWAY_ENVIRONMENT_ID": "production"}):
                self.assertEqual(_client_rate_key(), "203.0.113.8")
