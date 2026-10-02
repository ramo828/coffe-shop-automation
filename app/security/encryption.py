"""
Database Encryption and Compression Module
Provides AES-256-GCM envelope encryption and GZ compression for local data safety.
"""
import os
import gzip
import base64
import logging
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)

def derive_key(passphrase: str, salt: bytes) -> bytes:
    """Derive 256-bit AES key from passphrase using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return kdf.derive(passphrase.encode("utf-8"))

def encrypt_bytes(data: bytes, passphrase: str) -> bytes:
    """
    Encrypt data using AES-256-GCM.
    Returns: salt (16 bytes) + nonce (12 bytes) + ciphertext + tag
    """
    salt = os.urandom(16)
    key = derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ciphertext

def decrypt_bytes(encrypted_payload: bytes, passphrase: str) -> bytes:
    """
    Decrypt AES-256-GCM encrypted payload.
    Extracts salt (16 bytes), nonce (12 bytes), and decrypts remainder.
    """
    if len(encrypted_payload) < 28:
        raise ValueError("Payload is too short to be valid ciphertext.")
    salt = encrypted_payload[:16]
    nonce = encrypted_payload[16:28]
    ciphertext = encrypted_payload[28:]
    key = derive_key(passphrase, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)

def compress_file_gz(source_path: Path, dest_path: Path):
    """Compress a file using gzip."""
    with open(source_path, "rb") as f_in:
        with gzip.open(dest_path, "wb") as f_out:
            f_out.writelines(f_in)

def decompress_file_gz(source_path: Path, dest_path: Path):
    """Decompress a gzip file."""
    with gzip.open(source_path, "rb") as f_in:
        with open(dest_path, "wb") as f_out:
            f_out.writelines(f_in)

def create_encrypted_backup(source_db_path: Path, backup_dest_path: Path, passphrase: str, compress: bool = True):
    """Create an encrypted (and optionally compressed) backup of the database."""
    with open(source_db_path, "rb") as f:
        data = f.read()

    if compress:
        data = gzip.compress(data)

    encrypted = encrypt_bytes(data, passphrase)
    with open(backup_dest_path, "wb") as f:
        f.write(encrypted)
    logger.info(f"Encrypted backup created at {backup_dest_path}")

def restore_encrypted_backup(backup_path: Path, target_db_path: Path, passphrase: str, compressed: bool = True):
    """Restore an encrypted backup to the database destination."""
    with open(backup_path, "rb") as f:
        encrypted_data = f.read()

    decrypted = decrypt_bytes(encrypted_data, passphrase)
    if compressed:
        decrypted = gzip.decompress(decrypted)

    with open(target_db_path, "wb") as f:
        f.write(decrypted)
    logger.info(f"Database successfully restored from {backup_path}")
