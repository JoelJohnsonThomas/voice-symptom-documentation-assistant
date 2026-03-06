"""
AES-256-GCM Encryption at Rest for HIPAA Compliance

Provides:
- AES-256-GCM authenticated encryption for PHI data (transcripts, audio, SOAP notes)
- Key derivation from a master secret using PBKDF2-HMAC-SHA256
- Unique nonce per encryption operation (12-byte random)
- Base64-encoded ciphertext for safe storage in text DB columns

Security properties:
- Confidentiality + integrity (GCM authentication tag)
- No nonce reuse (random 12 bytes per operation)
- Key stretching via PBKDF2 with configurable iterations
"""

import base64
import hashlib
import hmac
import os
import struct
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Format: VERSION(1) || NONCE(12) || TAG(16) || CIPHERTEXT(variable)
_VERSION = 1
_NONCE_SIZE = 12
_TAG_SIZE = 16
_KEY_SIZE = 32  # 256 bits


def _derive_key(master_secret: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
    """Derive a 256-bit encryption key from master secret using PBKDF2."""
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        master_secret.encode("utf-8"),
        salt,
        iterations=settings.encryption_kdf_iterations,
        dklen=_KEY_SIZE,
    )
    return key, salt


def _get_encryption_key() -> bytes:
    """Get or derive the encryption key from settings.

    Uses a fixed salt derived from the secret itself for deterministic key derivation,
    so the same key is produced across restarts without storing the salt separately.
    """
    secret = settings.encryption_master_key
    if not secret or secret == "CHANGE_ME_IN_PRODUCTION":
        raise RuntimeError(
            "ENCRYPTION_MASTER_KEY must be set to a strong random secret for HIPAA encryption at rest."
        )
    # Deterministic salt from HMAC of the secret — same key every time
    fixed_salt = hmac.new(secret.encode(), b"hipaa-encryption-salt", hashlib.sha256).digest()[:16]
    key, _ = _derive_key(secret, salt=fixed_salt)
    return key


def encrypt_data(plaintext: str) -> str:
    """Encrypt a plaintext string using AES-256-GCM.

    Returns a base64-encoded string containing version, nonce, tag, and ciphertext.
    Returns the original string if encryption is disabled or plaintext is empty.
    """
    if not settings.encryption_at_rest_enabled:
        return plaintext
    if not plaintext:
        return plaintext

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        logger.error("cryptography package required for encryption. Install with: pip install cryptography")
        raise RuntimeError("cryptography package is required for HIPAA encryption at rest")

    key = _get_encryption_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)

    # ciphertext from AESGCM includes the 16-byte tag appended
    # Pack: VERSION || NONCE || CIPHERTEXT_WITH_TAG
    packed = struct.pack("B", _VERSION) + nonce + ciphertext
    return base64.b64encode(packed).decode("ascii")


def decrypt_data(encoded: str) -> str:
    """Decrypt a base64-encoded AES-256-GCM ciphertext.

    Returns the original plaintext string.
    Returns the input unchanged if encryption is disabled or data is not encrypted.
    """
    if not settings.encryption_at_rest_enabled:
        return encoded
    if not encoded:
        return encoded

    # Check if data looks like base64-encoded encrypted data
    try:
        raw = base64.b64decode(encoded)
    except Exception:
        # Not base64 — return as-is (unencrypted legacy data)
        return encoded

    if len(raw) < 1 + _NONCE_SIZE + _TAG_SIZE:
        # Too short to be encrypted data — return as-is
        return encoded

    version = raw[0]
    if version != _VERSION:
        # Unknown version or unencrypted data — return as-is
        return encoded

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise RuntimeError("cryptography package is required for HIPAA decryption")

    nonce = raw[1:1 + _NONCE_SIZE]
    ciphertext_with_tag = raw[1 + _NONCE_SIZE:]

    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext_with_tag, None)
    return plaintext.decode("utf-8")


def encrypt_bytes(data: bytes) -> bytes:
    """Encrypt raw bytes (e.g., audio files) using AES-256-GCM.

    Returns encrypted bytes with version, nonce, and tag prepended.
    """
    if not settings.encryption_at_rest_enabled:
        return data
    if not data:
        return data

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise RuntimeError("cryptography package is required for HIPAA encryption at rest")

    key = _get_encryption_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return struct.pack("B", _VERSION) + nonce + ciphertext


def decrypt_bytes(data: bytes) -> bytes:
    """Decrypt raw bytes encrypted with encrypt_bytes."""
    if not settings.encryption_at_rest_enabled:
        return data
    if not data or len(data) < 1 + _NONCE_SIZE + _TAG_SIZE:
        return data

    version = data[0]
    if version != _VERSION:
        return data

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise RuntimeError("cryptography package is required for HIPAA decryption")

    nonce = data[1:1 + _NONCE_SIZE]
    ciphertext_with_tag = data[1 + _NONCE_SIZE:]

    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext_with_tag, None)


def is_encrypted(data: str) -> bool:
    """Check if a string appears to be encrypted data."""
    try:
        raw = base64.b64decode(data)
        return len(raw) > 1 + _NONCE_SIZE + _TAG_SIZE and raw[0] == _VERSION
    except Exception:
        return False
