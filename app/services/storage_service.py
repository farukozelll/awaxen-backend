"""MinIO/S3 Storage Service - Object Storage yönetimi."""

from __future__ import annotations

import io
import logging
import os
from datetime import timedelta
from typing import BinaryIO, Optional
from uuid import uuid4

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class StorageService:
    """
    S3-uyumlu object storage servisi.
    MinIO veya AWS S3 ile çalışır.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket: Optional[str] = None,
        secure: bool = False,
        public_endpoint: Optional[str] = None,
    ):
        self.endpoint = endpoint or os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.access_key = access_key or os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = secret_key or os.getenv("MINIO_SECRET_KEY", "minioadmin123")
        self.bucket = bucket or os.getenv("MINIO_BUCKET", "awaxen-images")
        self.secure = secure or os.getenv("MINIO_SECURE", "false").lower() == "true"
        # Public endpoint for browser access (frontend)
        self.public_endpoint = public_endpoint or os.getenv("MINIO_PUBLIC_ENDPOINT", "localhost:9000")

        protocol = "https" if self.secure else "http"
        self.endpoint_url = f"{protocol}://{self.endpoint}"
        self.public_endpoint_url = f"{protocol}://{self.public_endpoint}"

        self._client: Optional[boto3.client] = None

    @property
    def client(self):
        """Lazy-loaded S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4"),
                region_name="us-east-1",  # MinIO için gerekli
            )
            self._ensure_bucket()
        return self._client

    def _ensure_bucket(self):
        """Bucket yoksa oluştur."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
            logger.debug(f"[Storage] Bucket mevcut: {self.bucket}")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                logger.info(f"[Storage] Bucket oluşturuluyor: {self.bucket}")
                self.client.create_bucket(Bucket=self.bucket)
            else:
                logger.error(f"[Storage] Bucket kontrolü hatası: {e}")
                raise

    def upload_file(
        self,
        file_data: BinaryIO,
        filename: str,
        content_type: str = "application/octet-stream",
        folder: str = "uploads",
    ) -> str:
        """
        Dosya yükle ve object key döndür.

        Args:
            file_data: Dosya içeriği (binary)
            filename: Orijinal dosya adı
            content_type: MIME type
            folder: Hedef klasör

        Returns:
            Object key (path)
        """
        # Unique filename oluştur
        ext = os.path.splitext(filename)[1] if "." in filename else ""
        unique_name = f"{uuid4().hex}{ext}"
        object_key = f"{folder}/{unique_name}"

        try:
            self.client.upload_fileobj(
                file_data,
                self.bucket,
                object_key,
                ExtraArgs={"ContentType": content_type},
            )
            logger.info(f"[Storage] Dosya yüklendi: {object_key}")
            return object_key
        except Exception as e:
            logger.error(f"[Storage] Yükleme hatası: {e}")
            raise

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        folder: str = "uploads",
    ) -> str:
        """Bytes olarak dosya yükle."""
        return self.upload_file(
            io.BytesIO(data),
            filename,
            content_type,
            folder,
        )

    def download_file(self, object_key: str) -> bytes:
        """Dosya indir ve bytes olarak döndür."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
            data = response["Body"].read()
            logger.debug(f"[Storage] Dosya indirildi: {object_key}")
            return data
        except Exception as e:
            logger.error(f"[Storage] İndirme hatası: {e}")
            raise

    def get_presigned_url(
        self,
        object_key: str,
        expires_in: int = 3600,
        method: str = "get_object",
        use_public_endpoint: bool = True,
    ) -> str:
        """
        Presigned URL oluştur (geçici erişim linki).

        Args:
            object_key: Dosya path'i
            expires_in: Geçerlilik süresi (saniye)
            method: get_object veya put_object
            use_public_endpoint: True ise public endpoint kullan (frontend için)

        Returns:
            Presigned URL
        """
        try:
            url = self.client.generate_presigned_url(
                ClientMethod=method,
                Params={"Bucket": self.bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )
            # Replace internal endpoint with public endpoint for browser access
            if use_public_endpoint and self.endpoint != self.public_endpoint:
                url = url.replace(self.endpoint_url, self.public_endpoint_url)
            return url
        except Exception as e:
            logger.error(f"[Storage] Presigned URL hatası: {e}")
            raise

    def delete_file(self, object_key: str) -> bool:
        """Dosya sil."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
            logger.info(f"[Storage] Dosya silindi: {object_key}")
            return True
        except Exception as e:
            logger.error(f"[Storage] Silme hatası: {e}")
            return False

    def file_exists(self, object_key: str) -> bool:
        """Dosya var mı kontrol et."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=object_key)
            return True
        except ClientError:
            return False

    def list_files(self, prefix: str = "", max_keys: int = 1000) -> list[dict]:
        """Dosyaları listele."""
        try:
            response = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                MaxKeys=max_keys,
            )
            files = []
            for obj in response.get("Contents", []):
                files.append(
                    {
                        "key": obj["Key"],
                        "size": obj["Size"],
                        "last_modified": obj["LastModified"].isoformat(),
                    }
                )
            return files
        except Exception as e:
            logger.error(f"[Storage] Listeleme hatası: {e}")
            return []


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Storage service singleton'ı döndür."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
