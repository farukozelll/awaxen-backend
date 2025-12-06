"""
Token Encryption Utilities - Güvenli token saklama.

OAuth token'ları (Shelly, Tesla, Tapo) veritabanında şifreli saklanır.
Fernet symmetric encryption kullanılır.

TRICK: .env dosyasında ENCRYPTION_KEY tanımlanmalı:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""
import os
from functools import lru_cache
from cryptography.fernet import Fernet, InvalidToken


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """
    Fernet instance'ını cached olarak döndür.
    
    ENCRYPTION_KEY yoksa hata fırlatır - güvenlik için zorunlu.
    """
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        raise ValueError(
            "ENCRYPTION_KEY environment variable is required! "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_token(plain_text: str) -> str:
    """
    Plain text token'ı şifrele.
    
    Args:
        plain_text: Şifrelenmemiş token (örn: Shelly access_token)
    
    Returns:
        Şifrelenmiş token (base64 encoded string)
    """
    if not plain_text:
        return None
    
    fernet = _get_fernet()
    encrypted = fernet.encrypt(plain_text.encode())
    return encrypted.decode()


def decrypt_token(encrypted_text: str) -> str:
    """
    Şifrelenmiş token'ı çöz.
    
    Args:
        encrypted_text: Şifrelenmiş token
    
    Returns:
        Plain text token
    
    Raises:
        InvalidToken: Şifre çözme başarısız olursa
    """
    if not encrypted_text:
        return None
    
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted_text.encode())
        return decrypted.decode()
    except InvalidToken:
        # Log this as a security event
        raise ValueError("Token decryption failed - possible tampering or key mismatch")


def rotate_encryption_key(old_key: str, new_key: str, encrypted_text: str) -> str:
    """
    Encryption key değiştiğinde mevcut token'ları yeni key ile şifrele.
    
    Migration sırasında kullanılır.
    """
    # Eski key ile çöz
    old_fernet = Fernet(old_key.encode())
    plain = old_fernet.decrypt(encrypted_text.encode()).decode()
    
    # Yeni key ile şifrele
    new_fernet = Fernet(new_key.encode())
    return new_fernet.encrypt(plain.encode()).decode()
