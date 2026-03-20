"""Phase 4: Authentication, RBAC, MFA, and consent tests."""

import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pyotp


# =====================================================
# Auth module unit tests
# =====================================================

class TestPasswordHashing(unittest.TestCase):
    """Password hashing and verification."""

    def test_hash_and_verify(self):
        from app.auth import hash_password, verify_password
        hashed = hash_password("testpassword123")
        self.assertTrue(verify_password("testpassword123", hashed))
        self.assertFalse(verify_password("wrongpassword", hashed))

    def test_hash_is_different_each_time(self):
        from app.auth import hash_password
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        self.assertNotEqual(h1, h2)  # bcrypt uses random salt


class TestJWTTokens(unittest.TestCase):
    """JWT token creation and decoding."""

    @patch("app.auth.settings")
    def test_create_access_token(self, mock_settings):
        mock_settings.jwt_secret_key = "test-secret-key-1234567890"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30

        from app.auth import create_access_token, decode_token
        token = create_access_token("user-123", "admin")
        payload = decode_token(token)

        self.assertEqual(payload["sub"], "user-123")
        self.assertEqual(payload["role"], "admin")
        self.assertEqual(payload["type"], "access")
        self.assertIn("exp", payload)
        self.assertIn("jti", payload)

    @patch("app.auth.settings")
    def test_create_refresh_token(self, mock_settings):
        mock_settings.jwt_secret_key = "test-secret-key-1234567890"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_refresh_token_expire_days = 7

        from app.auth import create_refresh_token, decode_token
        token = create_refresh_token("user-456")
        payload = decode_token(token)

        self.assertEqual(payload["sub"], "user-456")
        self.assertEqual(payload["type"], "refresh")

    @patch("app.auth.settings")
    def test_create_mfa_token(self, mock_settings):
        mock_settings.jwt_secret_key = "test-secret-key-1234567890"
        mock_settings.jwt_algorithm = "HS256"

        from app.auth import create_mfa_token, decode_token
        token = create_mfa_token("user-789")
        payload = decode_token(token)

        self.assertEqual(payload["sub"], "user-789")
        self.assertEqual(payload["type"], "mfa_pending")

    @patch("app.auth.settings")
    def test_expired_token_raises(self, mock_settings):
        import jwt as pyjwt
        mock_settings.jwt_secret_key = "test-secret-key-1234567890"
        mock_settings.jwt_algorithm = "HS256"

        from app.auth import decode_token
        from fastapi import HTTPException

        # Create an already-expired token
        expired_payload = {
            "sub": "user-1",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = pyjwt.encode(expired_payload, "test-secret-key-1234567890", algorithm="HS256")

        with self.assertRaises(HTTPException) as ctx:
            decode_token(expired_token)
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.auth.settings")
    def test_invalid_token_raises(self, mock_settings):
        mock_settings.jwt_secret_key = "test-secret-key-1234567890"
        mock_settings.jwt_algorithm = "HS256"

        from app.auth import decode_token
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            decode_token("not.a.valid.token")
        self.assertEqual(ctx.exception.status_code, 401)

    def test_hash_token(self):
        from app.auth import hash_token
        h = hash_token("some-refresh-token")
        expected = hashlib.sha256(b"some-refresh-token").hexdigest()
        self.assertEqual(h, expected)


class TestAuthDisabled(unittest.TestCase):
    """When auth_enabled=False, system should behave as before."""

    @patch("app.auth.settings")
    def test_require_roles_returns_system_user(self, mock_settings):
        mock_settings.auth_enabled = False

        from app.auth import SYSTEM_USER, UserRole, require_roles
        import asyncio

        dep = require_roles(UserRole.ADMIN)
        # Call the dependency without real request/db
        mock_request = MagicMock()
        mock_db = AsyncMock()

        result = asyncio.get_event_loop().run_until_complete(
            dep(request=mock_request, db=mock_db)
        )
        self.assertIs(result, SYSTEM_USER)

    @patch("app.auth.settings")
    def test_get_current_user_returns_system_user(self, mock_settings):
        mock_settings.auth_enabled = False

        from app.auth import SYSTEM_USER, get_current_user
        import asyncio

        mock_request = MagicMock()
        mock_db = AsyncMock()

        result = asyncio.get_event_loop().run_until_complete(
            get_current_user(request=mock_request, db=mock_db)
        )
        self.assertIs(result, SYSTEM_USER)


class TestAuthEnabled(unittest.TestCase):
    """When auth_enabled=True, JWT is enforced."""

    @patch("app.auth.settings")
    def test_missing_auth_header_raises_401(self, mock_settings):
        mock_settings.auth_enabled = True

        from app.auth import get_current_user
        from fastapi import HTTPException
        import asyncio

        mock_request = MagicMock()
        mock_request.headers.get.return_value = None
        mock_db = AsyncMock()

        with self.assertRaises(HTTPException) as ctx:
            asyncio.get_event_loop().run_until_complete(
                get_current_user(request=mock_request, db=mock_db)
            )
        self.assertEqual(ctx.exception.status_code, 401)

    @patch("app.auth.settings")
    def test_wrong_role_raises_403(self, mock_settings):
        mock_settings.auth_enabled = True
        mock_settings.jwt_secret_key = "test-secret-key-1234567890"
        mock_settings.jwt_algorithm = "HS256"
        mock_settings.jwt_access_token_expire_minutes = 30

        from app.auth import UserRole, create_access_token, require_roles
        from fastapi import HTTPException
        import asyncio

        token = create_access_token("user-1", "viewer")

        mock_request = MagicMock()
        mock_request.headers.get.return_value = f"Bearer {token}"

        # Mock the DB lookup to return a user with viewer role
        mock_user = MagicMock()
        mock_user.id = "user-1"
        mock_user.role = "viewer"
        mock_user.is_active = True

        mock_db = AsyncMock()

        dep = require_roles(UserRole.ADMIN)

        with patch("app.auth.get_current_user", new_callable=AsyncMock, return_value=mock_user):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.get_event_loop().run_until_complete(
                    dep(request=mock_request, db=mock_db)
                )
            self.assertEqual(ctx.exception.status_code, 403)


class TestMFA(unittest.TestCase):
    """TOTP MFA tests."""

    def test_totp_generation_and_verification(self):
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        self.assertTrue(totp.verify(code, valid_window=1))
        self.assertFalse(totp.verify("000000", valid_window=0))

    def test_totp_provisioning_uri(self):
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name="testuser", issuer_name="VoxDoc")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn("VoxDoc", uri)
        self.assertIn("testuser", uri)


class TestUserRoles(unittest.TestCase):
    """Role enum and role sets."""

    def test_role_values(self):
        from app.auth import UserRole
        self.assertEqual(UserRole.ADMIN.value, "admin")
        self.assertEqual(UserRole.PROVIDER.value, "provider")
        self.assertEqual(UserRole.INTAKE.value, "intake")
        self.assertEqual(UserRole.VIEWER.value, "viewer")

    def test_role_sets(self):
        from app.auth import ALL_ROLES, INTAKE_AND_UP_ROLES, UserRole
        self.assertEqual(len(ALL_ROLES), 4)
        self.assertIn(UserRole.ADMIN, INTAKE_AND_UP_ROLES)
        self.assertIn(UserRole.PROVIDER, INTAKE_AND_UP_ROLES)
        self.assertIn(UserRole.INTAKE, INTAKE_AND_UP_ROLES)
        self.assertNotIn(UserRole.VIEWER, INTAKE_AND_UP_ROLES)


class TestSystemPrincipal(unittest.TestCase):
    """System user stub compatibility."""

    def test_system_user_attributes(self):
        from app.auth import SYSTEM_USER, UserRole
        self.assertEqual(SYSTEM_USER.id, "system")
        self.assertEqual(SYSTEM_USER.username, "system")
        self.assertEqual(SYSTEM_USER.role, UserRole.ADMIN)
        self.assertTrue(SYSTEM_USER.is_active)
        self.assertIsNotNone(SYSTEM_USER.created_at)


# =====================================================
# DB model tests
# =====================================================

class TestDBModels(unittest.TestCase):
    """Verify new DB models have expected columns."""

    def test_refresh_token_model(self):
        from app.db.models import RefreshToken
        self.assertEqual(RefreshToken.__tablename__, "refresh_tokens")
        columns = {c.name for c in RefreshToken.__table__.columns}
        expected = {"id", "user_id", "token_hash", "expires_at", "revoked", "created_at", "ip_address", "user_agent"}
        self.assertTrue(expected.issubset(columns))

    def test_consent_record_model(self):
        from app.db.models import ConsentRecord
        self.assertEqual(ConsentRecord.__tablename__, "consent_records")
        columns = {c.name for c in ConsentRecord.__table__.columns}
        expected = {"id", "session_id", "consent_type", "consented_at", "revoked", "revoked_at"}
        self.assertTrue(expected.issubset(columns))

    def test_user_has_mfa_columns(self):
        from app.db.models import User
        columns = {c.name for c in User.__table__.columns}
        self.assertIn("totp_secret", columns)
        self.assertIn("mfa_enrolled_at", columns)


# =====================================================
# Config tests
# =====================================================

class TestConfigDefaults(unittest.TestCase):
    """Phase 4 config defaults preserve dev mode behavior."""

    def test_auth_disabled_by_default(self):
        from app.config import Settings
        s = Settings()
        self.assertFalse(s.auth_enabled)

    def test_mfa_disabled_by_default(self):
        from app.config import Settings
        s = Settings()
        self.assertFalse(s.mfa_enabled)

    def test_consent_tracking_enabled_by_default(self):
        from app.config import Settings
        s = Settings()
        self.assertTrue(s.consent_tracking_enabled)

    def test_cors_wildcard_default(self):
        from app.config import Settings
        s = Settings()
        self.assertEqual(s.cors_allowed_origins, "*")

    def test_jwt_defaults(self):
        from app.config import Settings
        s = Settings()
        self.assertEqual(s.jwt_algorithm, "HS256")
        self.assertEqual(s.jwt_access_token_expire_minutes, 30)
        self.assertEqual(s.jwt_refresh_token_expire_days, 7)
        self.assertEqual(s.session_inactivity_timeout_minutes, 15)


# =====================================================
# Auth routes schema tests
# =====================================================

class TestRouteSchemas(unittest.TestCase):
    """Pydantic request models validate correctly."""

    def test_register_request_validation(self):
        from app.routes.auth_routes import RegisterRequest
        req = RegisterRequest(username="testuser", password="password123")
        self.assertEqual(req.username, "testuser")
        self.assertEqual(req.role, "intake")  # default

    def test_register_request_rejects_short_username(self):
        from app.routes.auth_routes import RegisterRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegisterRequest(username="ab", password="password123")

    def test_register_request_rejects_short_password(self):
        from app.routes.auth_routes import RegisterRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RegisterRequest(username="testuser", password="short")

    def test_login_request(self):
        from app.routes.auth_routes import LoginRequest
        req = LoginRequest(username="user", password="pass")
        self.assertIsNone(req.totp_code)
        self.assertIsNone(req.mfa_token)

    def test_consent_request(self):
        from app.routes.auth_routes import ConsentRequest
        req = ConsentRequest(session_id="sess-123")
        self.assertEqual(req.consent_type, "verbal")
        self.assertIsNone(req.patient_identifier)

    def test_mfa_verify_request(self):
        from app.routes.auth_routes import MFAVerifyRequest
        req = MFAVerifyRequest(totp_code="123456")
        self.assertEqual(req.totp_code, "123456")

    def test_mfa_verify_rejects_short_code(self):
        from app.routes.auth_routes import MFAVerifyRequest
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            MFAVerifyRequest(totp_code="123")


if __name__ == "__main__":
    unittest.main()
