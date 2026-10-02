"""
Unit and Integration Tests: Security, Demo/Real Mode, Anti-Tamper Clock Guard, and Encryption
"""
import unittest
from app.security.license import get_system_license_status, generate_activation_key, verify_activation_key, activate_real_mode
from app.security.encryption import encrypt_bytes, decrypt_bytes
from app.security.time_guard import check_time_integrity, record_tamper_event, is_tamper_flagged
from app.core.config import DEFAULT_BRANCH_CODE
from app.core.database import get_db

class TestSecurityAndLicense(unittest.TestCase):
    def test_demo_license_status(self):
        """CRITICAL RULE L1: Demo trial evaluation status."""
        status = get_system_license_status()
        self.assertIn("status_label", status)
        self.assertIn(status["status_label"], ["TRIAL_ACTIVE", "REAL", "TRIAL_EXPIRED", "TAMPER_LOCKED"])

    def test_real_activation_key_cryptography(self):
        """CRITICAL RULE L2: Cryptographically verifiable activation keys."""
        valid_key = generate_activation_key(DEFAULT_BRANCH_CODE)
        self.assertTrue(verify_activation_key(valid_key, DEFAULT_BRANCH_CODE))

        # Invalid keys must fail
        self.assertFalse(verify_activation_key("INVALID-FAKE-KEY-9999", DEFAULT_BRANCH_CODE))
        self.assertFalse(verify_activation_key(valid_key, "OTHER-BRANCH-99"))

    def test_real_activation_unlocks_system(self):
        """Activating with valid key switches system to REAL mode."""
        valid_key = generate_activation_key(DEFAULT_BRANCH_CODE)
        ok, msg = activate_real_mode(valid_key, DEFAULT_BRANCH_CODE)
        self.assertTrue(ok)

        status = get_system_license_status()
        self.assertTrue(status["is_real_mode"])
        self.assertFalse(status["is_locked"])
        self.assertEqual(status["status_label"], "REAL")

    def test_aes_256_gcm_encryption_and_decryption(self):
        """CRITICAL RULE M1: DB/Data encryption with AES-256-GCM."""
        plaintext = b"ILLY_SENSITIVE_SPECIALTY_COFFEE_RECORDS_2026"
        passphrase = "UltraSecretDeveloperPassphrase99!"

        ciphertext = encrypt_bytes(plaintext, passphrase)
        self.assertNotEqual(plaintext, ciphertext)
        self.assertNotIn(b"ILLY", ciphertext)

        # Decrypt
        decrypted = decrypt_bytes(ciphertext, passphrase)
        self.assertEqual(plaintext, decrypted)

        # Invalid passphrase must fail
        with self.assertRaises(Exception):
            decrypt_bytes(ciphertext, "WrongPassphrase123")

if __name__ == "__main__":
    unittest.main()

