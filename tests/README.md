# Awaxen Backend Test Suite

## 🚀 Hızlı Başlangıç

### Bağımlılıkları Yükle
```bash
# Docker container içinde
docker exec -it awaxen_backend pip install pytest pytest-asyncio httpx aiosqlite

# Veya lokal geliştirme için
pip install -e ".[dev]"
```

### Testleri Çalıştır
```bash
# Tüm testler
pytest -v

# Sadece belirli test dosyası
pytest -v tests/test_auth_sync.py

# Sadece belirli test sınıfı
pytest -v tests/test_auth_sync.py::TestAuth0Sync

# Sadece belirli test
pytest -v tests/test_auth_sync.py::TestAuth0Sync::test_sync_new_user_creates_user_and_org

# Coverage ile
pytest -v --cov=src --cov-report=html
```

## 📁 Test Dosyaları

| Dosya | Açıklama |
|-------|----------|
| `conftest.py` | Test fixtures ve konfigürasyon |
| `test_health.py` | Health check endpoint testleri |
| `test_api_endpoints.py` | Temel endpoint erişilebilirlik testleri |
| `test_auth_sync.py` | Auth0 senkronizasyon akışı testleri |
| `test_organization_flow.py` | Organizasyon yönetimi testleri |
| `test_logic_bugs.py` | Mantık hatası tespit testleri |

## 🧪 Test Kategorileri

### 1. Unit Tests
Tek bir fonksiyonu izole olarak test eder.

### 2. Integration Tests
Birden fazla komponentin birlikte çalışmasını test eder.

### 3. Flow Tests
Kullanıcı senaryolarını baştan sona test eder:
- Auth0 ile giriş → Organizasyon oluşturma → Kullanıcı davet etme

### 4. Edge Case Tests
Sınır durumlarını test eder:
- Boş isim
- Çok uzun isim
- Özel karakterler
- SQL injection
- XSS

## 🔧 Fixtures

### Database Fixtures
```python
@pytest.fixture
async def db_session():
    """Her test için temiz veritabanı oturumu."""
```

### Auth Fixtures
```python
@pytest.fixture
def admin_token():
    """Admin yetkili test token'ı."""

@pytest.fixture
def tenant_token():
    """Tenant yetkili test token'ı."""

@pytest.fixture
def user_token():
    """Normal kullanıcı test token'ı."""
```

### Factory Fixtures
```python
@pytest.fixture
def make_user():
    """Test kullanıcısı factory."""

@pytest.fixture
def make_organization():
    """Test organizasyonu factory."""
```

## 🐛 Mantık Hatası Tespiti

Testler şu mantık hatalarını tespit eder:

1. **Veri Sızıntısı (Tenant Isolation)**
   - Bir kullanıcı başka organizasyonun verisini görememeli

2. **Duplicate Kayıt**
   - Aynı email/slug ile iki kayıt oluşturulamamalı

3. **Yetki Sızıntısı**
   - Normal kullanıcı admin işlemi yapamamalı

4. **Cascade Delete**
   - Organizasyon silinince ilişkili veriler de silinmeli

5. **Race Conditions**
   - Eşzamanlı istekler duplicate oluşturmamalı

## 📊 Coverage Raporu

```bash
# HTML rapor oluştur
pytest --cov=src --cov-report=html

# Raporu aç
open htmlcov/index.html
```

## 🔴 Test Fail Olursa

1. **500 Internal Server Error**: Backend'de exception var
2. **409 Conflict**: Unique constraint ihlali
3. **403 Forbidden**: Yetki kontrolü çalışıyor (beklenen)
4. **401 Unauthorized**: Auth gerekli (beklenen)

## 💡 Yeni Test Ekleme

```python
# tests/test_my_feature.py
import pytest
from httpx import AsyncClient

class TestMyFeature:
    @pytest.mark.asyncio
    async def test_my_scenario(self, client: AsyncClient):
        response = await client.get("/api/v1/my-endpoint")
        assert response.status_code == 200
```
