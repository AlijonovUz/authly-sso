import unittest
from unittest.mock import patch, MagicMock
from authly import (
    AuthlyClient,
    AuthlySDKError,
    AuthlyTokenExchangeError,
    calculate_signature,
    verify_webhook_signature,
)
from authly.services import extract_user_payload, populate_user_fields


class DummyUser:
    def __init__(self):
        self.authly_id = None
        self.first_name = ""
        self.last_name = ""
        self.email = ""
        self.phone_number = ""
        self.birth_date = None


class TestAuthlySDK(unittest.TestCase):
    def setUp(self):
        self.client = AuthlyClient(
            backend_url="https://api.authly.uz",
            frontend_url="https://authly.uz",
            client_id="test_client_id",
            client_secret="test_secret",
            redirect_uri="https://app.uz/callback",
            webhook_secret="secret_xyz",
        )

    def test_authorization_url(self):
        url = self.client.get_authorization_url(scope="read", state="csrf_val")
        self.assertIn("https://authly.uz/login?", url)
        self.assertIn("client_id=test_client_id", url)
        self.assertIn("redirect_uri=https%3A%2F%2Fapp.uz%2Fcallback", url)
        self.assertIn("scope=read", url)
        self.assertIn("state=csrf_val", url)

    def test_authorization_url_missing_redirect_uri(self):
        client = AuthlyClient(frontend_url="https://authly.uz", client_id="cid")
        with self.assertRaises(AuthlySDKError):
            client.get_authorization_url()

    def test_webhook_signature(self):
        secret = "super_secret"
        payload = b'{"event":"user.updated","user":{"authly_id":"123"}}'
        signature = calculate_signature(secret, payload)
        self.assertTrue(signature.startswith("sha256="))
        self.assertTrue(verify_webhook_signature(secret, payload, signature))
        self.assertFalse(verify_webhook_signature(secret, b'{"other":1}', signature))
        self.assertTrue(
            self.client.verify_webhook_signature(
                b'{"test":1}', calculate_signature("secret_xyz", b'{"test":1}')
            )
        )

    @patch("requests.post")
    def test_exchange_code_for_token_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token_abc",
            "refresh_token": "refresh_xyz",
            "token_type": "Bearer",
        }
        mock_post.return_value = mock_response

        res = self.client.exchange_code_for_token("code123")
        self.assertEqual(res["access_token"], "token_abc")
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_exchange_code_for_token_failure(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "invalid_grant"
        mock_post.return_value = mock_response

        with self.assertRaises(AuthlyTokenExchangeError):
            self.client.exchange_code_for_token("bad_code")

    @patch("requests.get")
    def test_get_user_profile(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "authly_id": "uuid-123",
                "first_name": "Alisher",
                "last_name": "Navoiy",
                "phone": "+998901234567",
            },
        }
        mock_get.return_value = mock_response

        profile = self.client.get_user_profile("access_tok")
        self.assertEqual(profile["authly_id"], "uuid-123")
        self.assertEqual(profile["first_name"], "Alisher")

    def test_extract_user_payload(self):
        d1 = extract_user_payload({"data": {"id": 1}})
        self.assertEqual(d1, {"id": 1})

        d2 = extract_user_payload({"user": {"id": 2}})
        self.assertEqual(d2, {"id": 2})

        d3 = extract_user_payload({"id": 3})
        self.assertEqual(d3, {"id": 3})

    def test_populate_user_fields(self):
        user = DummyUser()
        user_data = {
            "authly_id": "u-456",
            "first_name": "Bobur",
            "last_name": "Mirzo",
            "email": "bobur@example.com",
            "phone": "+998931112233",
            "birth_date": "1483-02-14",
        }
        updated = populate_user_fields(user, user_data)
        self.assertIn("authly_id", updated)
        self.assertEqual(user.authly_id, "u-456")
        self.assertEqual(user.first_name, "Bobur")
        self.assertEqual(user.phone_number, "+998931112233")
        self.assertEqual(user.birth_date, "1483-02-14")


if __name__ == "__main__":
    unittest.main()
