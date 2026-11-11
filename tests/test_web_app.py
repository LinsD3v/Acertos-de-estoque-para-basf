from __future__ import annotations

import base64
import csv
import io
import unittest
from pathlib import Path

from backend.app import _password_hash, app
from backend.stock_processor import GIX_REPORT, OUTPUT_CSV, OUTPUT_XLS

ROOT = Path(__file__).resolve().parents[1]
TEST_PASSWORD = "test-password-for-session"


class StockWebAppTests(unittest.TestCase):
    def setUp(self) -> None:
        app.config.update(TESTING=True)
        app.config["SECRET_KEY"] = "test-secret-key-long-enough-for-cookie-signing"
        app.config["PASSWORD_HASH"] = _password_hash(TEST_PASSWORD)
        self.client = app.test_client()
        self.login()

    def login(self) -> None:
        response = self.client.post("/login", data={"password": TEST_PASSWORD})
        self.assertEqual(response.status_code, 302)

    def test_login_is_public_but_page_api_and_assets_require_cookie(self) -> None:
        client = app.test_client()

        self.assertEqual(client.get("/login").status_code, 200)
        self.assertEqual(client.get("/").status_code, 302)
        self.assertEqual(client.get("/static/app.js").status_code, 302)
        self.assertEqual(client.get("/api/health").status_code, 401)
        login_styles = client.get("/static/login.css")
        self.assertEqual(login_styles.status_code, 200)
        login_styles.close()

    def test_password_authentication_uses_signed_cookie_without_password(self) -> None:
        client = app.test_client()
        bad_response = client.post("/login", data={"password": "wrong"})
        self.assertEqual(bad_response.status_code, 401)

        response = client.post("/login", data={"password": TEST_PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(client.get("/").status_code, 200)
        app_script = client.get("/static/app.js")
        self.assertEqual(app_script.status_code, 200)
        app_script.close()
        self.assertEqual(client.get("/api/health").status_code, 200)

        cookie = client.get_cookie("basf_auth")
        self.assertIsNotNone(cookie)
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, "Lax")
        self.assertNotIn(TEST_PASSWORD, cookie.value)

        logout_response = client.post("/logout")
        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(client.get("/").status_code, 302)

    def test_authentication_fails_closed_when_environment_is_not_configured(self) -> None:
        app.config["PASSWORD_HASH"] = None
        client = app.test_client()

        self.assertEqual(client.post("/login", data={"password": TEST_PASSWORD}).status_code, 503)
        self.assertEqual(client.get("/api/health").status_code, 503)

    def test_health_endpoint(self) -> None:
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_process_preserves_current_cli_exports(self) -> None:
        with GIX_REPORT.open("rb") as gix_file:
            response = self.client.post(
                "/api/process",
                data={"gix_file": (gix_file, GIX_REPORT.name)},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["record_count"], 302)

        csv_output = base64.b64decode(payload["files"]["csv"]["base64"])
        xls_output = base64.b64decode(payload["files"]["xls"]["base64"])
        self.assertEqual(csv_output, OUTPUT_CSV.read_bytes())
        self.assertEqual(xls_output, OUTPUT_XLS.read_bytes())

    def test_process_accepts_uploaded_mapping_and_returns_preview(self) -> None:
        gix_content = b"CODIGO;ESTOQUEATUAL\n9305;7,75\n9306;\n"
        mapping_content = b"GIX;SKU_VTEX\n9305;SKU-89\n9306;NULL\n9999;SKU-90\n"
        response = self.client.post(
            "/api/process",
            data={
                "gix_file": (io.BytesIO(gix_content), "gix.csv"),
                "mapping_file": (io.BytesIO(mapping_content), "mapping.csv"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200, response.get_json())
        payload = response.get_json()
        self.assertEqual(payload["record_count"], 1)
        self.assertEqual(payload["preview"][0]["SkuId"], "SKU-89")
        self.assertEqual(payload["preview"][0]["TotalQuantity"], 7)

        csv_text = base64.b64decode(payload["files"]["csv"]["base64"]).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual(rows[0]["SkuId"], "SKU-89")
        self.assertEqual(rows[0]["TotalQuantity"], "7")
        self.assertEqual(rows[0]["AvailableQuantity"], "7")
        self.assertTrue(
            base64.b64decode(payload["files"]["xls"]["base64"]).startswith(
                bytes.fromhex("D0CF11E0A1B11AE1")
            )
        )

    def test_process_requires_gix_csv(self) -> None:
        response = self.client.post("/api/process", data={})

        self.assertEqual(response.status_code, 400)
        self.assertIn("gix_file", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
