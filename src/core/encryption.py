"""
Encryption Utility Module
Fernet symmetric encryption for sensitive data (API keys, tokens).
"""
from cryptography.fernet import Fernet, InvalidToken

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class EncryptionService:
    """
    Service for encrypting/decrypting sensitive data.
    Uses Fernet symmetric encryption.
    """
    
    def __init__(self, key: str | None = None):
        """
        Initialize encryption service.
        
        Args:
            key: Fernet key (base64 encoded). Uses settings if not provided.
        """
        self._key = key or settings.encryption_key
        self._fernet: Fernet | None = None
        
        if self._key:
            try:
                self._fernet = Fernet(self._key.encode())
            except Exception as e:
                logger.error("Invalid encryption key", error=str(e))
                raise ValueError("Invalid ENCRYPTION_KEY. Generate with: "
                               "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    
    @property
    def is_configured(self) -> bool:
        """Check if encryption is properly configured."""
        return self._fernet is not None
    
    def encrypt(self, data: str) -> str:
        """
        Encrypt a string.
        
        Args:
            data: Plain text to encrypt
            
        Returns:
            Encrypted string (base64 encoded)
        """
        if not self._fernet:
            raise RuntimeError("Encryption not configured. Set ENCRYPTION_KEY in .env")
        
        encrypted = self._fernet.encrypt(data.encode())
        return encrypted.decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decrypt an encrypted string.
        
        Args:
            encrypted_data: Encrypted string (base64 encoded)
            
        Returns:
            Decrypted plain text
        """
        if not self._fernet:
            raise RuntimeError("Encryption not configured. Set ENCRYPTION_KEY in .env")
        
        try:
            decrypted = self._fernet.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except InvalidToken:
            logger.error("Failed to decrypt data - invalid token or key")
            raise ValueError("Decryption failed. Data may be corrupted or key is wrong.")
    
    def encrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """
        Encrypt specific fields in a dictionary.
        
        Args:
            data: Dictionary with data
            fields: List of field names to encrypt
            
        Returns:
            Dictionary with specified fields encrypted
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        return result
    
    def decrypt_dict(self, data: dict, fields: list[str]) -> dict:
        """
        Decrypt specific fields in a dictionary.
        
        Args:
            data: Dictionary with encrypted data
            fields: List of field names to decrypt
            
        Returns:
            Dictionary with specified fields decrypted
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                try:
                    result[field] = self.decrypt(str(result[field]))
                except ValueError:
                    logger.warning(f"Failed to decrypt field: {field}")
        return result


# Singleton instance
_encryption_service: EncryptionService | None = None


def get_encryption_service() -> EncryptionService:
    """Get or create encryption service singleton."""
    global _encryption_service
    if _encryption_service is None:
        _encryption_service = EncryptionService()
    return _encryption_service


def encrypt_api_key(api_key: str) -> str:
    """Convenience function to encrypt an API key."""
    return get_encryption_service().encrypt(api_key)


def decrypt_api_key(encrypted_key: str) -> str:
    """Convenience function to decrypt an API key."""
    return get_encryption_service().decrypt(encrypted_key)
