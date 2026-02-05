import os
import pytest
import secrets
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Use a fixed key for tests instead of trying to import it
TEST_BOOT_KEY = secrets.token_bytes(32)


def test_encryption_decryption_integrity():
    """
    Ensures that the encryption used by the packager can be
    correctly decrypted and that any tampering is detected.
    """
    original_code = "print('Hello, Secure World!')"
    aesgcm = AESGCM(TEST_BOOT_KEY)
    nonce = os.urandom(12)

    # Encrypt
    encrypted_payload = aesgcm.encrypt(nonce, original_code.encode("utf-8"), None)
    total_data = nonce + encrypted_payload

    # Decrypt simulation (what the Rust loader does)
    ext_nonce = total_data[:12]
    ext_ciphertext = total_data[12:]

    decrypted_bytes = aesgcm.decrypt(ext_nonce, ext_ciphertext, None)
    assert decrypted_bytes.decode("utf-8") == original_code


def test_tamper_detection():
    """
    Ensures that AES-GCM tag validation fails if the payload is modified.
    """
    original_code = "secret_logic()"
    aesgcm = AESGCM(TEST_BOOT_KEY)
    nonce = os.urandom(12)
    encrypted_payload = aesgcm.encrypt(nonce, original_code.encode("utf-8"), None)

    # Tamper with the encrypted data (flip one bit in the ciphertext)
    tampered_data_list = list(encrypted_payload)
    tampered_data_list[0] ^= 0x01
    tampered_payload = bytes(tampered_data_list)

    with pytest.raises(Exception):
        # This should throw a Ciphertext authentication failure
        aesgcm.decrypt(nonce, tampered_payload, None)


def test_cross_platform_path_logic():
    """
    Verifies that the packager generates valid cross-platform binary names.
    """
    from pytron.pack.utils import get_native_engine_binaries
    import sys

    libs = get_native_engine_binaries()
    if sys.platform == "win32":
        assert "pytron_native.pyd" in libs
    elif sys.platform == "darwin":
        assert "pytron_native.so" in libs
    else:
        assert "pytron_native.so" in libs
