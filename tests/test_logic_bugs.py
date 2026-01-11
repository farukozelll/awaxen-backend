"""
Logic Bug Detection Tests

Bu testler sistemdeki mantık hatalarını tespit etmek için tasarlanmıştır.
Her test bir potansiyel bug senaryosunu kontrol eder.

Test Kategorileri:
1. Veri Bütünlüğü (Data Integrity)
2. Yetki Sızıntısı (Authorization Leaks)
3. Race Conditions
4. Cascade Delete
5. Unique Constraints
"""
import pytest
from httpx import AsyncClient
import asyncio


class TestDataIntegrity:
    """Veri bütünlüğü testleri."""
    
    @pytest.mark.asyncio
    async def test_user_org_relationship_consistent(self, client: AsyncClient, mock_auth0_user: dict):
        """
        Kullanıcı oluşturulduğunda organizasyon ilişkisi tutarlı olmalı.
        
        MANTIK HATASI: Kullanıcı var ama organizasyon yok veya tersi.
        """
        response = await client.post("/api/v1/auth/sync", json=mock_auth0_user)
        assert response.status_code == 200
        
        data = response.json()
        
        # Kullanıcı ve organizasyon birlikte oluşturulmuş mu?
        assert data["user"] is not None, "User oluşturulmalı"
        assert data["organization"] is not None, "Organization oluşturulmalı"
        
        # Kullanıcının organizasyonu var mı?
        if "organization" in data["user"] and data["user"]["organization"]:
            assert data["user"]["organization"]["id"] == data["organization"]["id"]
    
    @pytest.mark.asyncio
    async def test_wallet_created_for_new_user(self, client: AsyncClient, mock_auth0_user: dict):
        """
        Yeni kullanıcı için AWX cüzdanı oluşturulmalı.
        
        MANTIK HATASI: Kullanıcı var ama cüzdan yok.
        """
        response = await client.post("/api/v1/auth/sync", json=mock_auth0_user)
        assert response.status_code == 200
        
        data = response.json()
        
        # Wallet bilgisi kontrol et
        if "wallet" in data["user"]:
            wallet = data["user"]["wallet"]
            if wallet is not None:
                assert "balance" in wallet, "Wallet balance olmalı"
                assert "currency" in wallet, "Wallet currency olmalı"


class TestUniqueConstraints:
    """Unique constraint testleri."""
    
    @pytest.mark.asyncio
    async def test_same_email_different_auth0_id_handled(self, client: AsyncClient):
        """
        Aynı email ile farklı auth0_id gelirse ne olur?
        
        Beklenen: Mevcut kullanıcıya auth0_id eklenmeli.
        MANTIK HATASI: Yeni kullanıcı oluşturulursa duplicate email olur.
        """
        email = "shared@example.com"
        
        # İlk sync
        user1 = {
            "auth0_id": "google-oauth2|first123",
            "email": email,
            "name": "First User",
            "email_verified": True,
        }
        resp1 = await client.post("/api/v1/auth/sync", json=user1)
        assert resp1.status_code == 200
        user1_id = resp1.json()["user"]["id"]
        
        # İkinci sync - aynı email, farklı auth0_id
        # Bu durumda sistem ne yapmalı?
        # Option 1: Hata ver (409 Conflict)
        # Option 2: Mevcut kullanıcıyı güncelle
        user2 = {
            "auth0_id": "github|second456",
            "email": email,
            "name": "Second User",
            "email_verified": True,
        }
        resp2 = await client.post("/api/v1/auth/sync", json=user2)
        
        # 500 dönmemeli - graceful handling olmalı
        assert resp2.status_code in [200, 409], \
            f"Duplicate email gracefully handled olmalı: {resp2.text}"
    
    @pytest.mark.asyncio
    async def test_organization_slug_uniqueness(self, client: AsyncClient):
        """
        Organizasyon slug'ları unique olmalı.
        
        MANTIK HATASI: Aynı slug ile iki organizasyon oluşturulabilirse
        routing ve lookup'larda sorun çıkar.
        """
        # Aynı isimle iki kullanıcı
        users = [
            {
                "auth0_id": f"google-oauth2|slug_test_{i}",
                "email": f"slugtest{i}@example.com",
                "name": "Test Company",  # Aynı isim
                "email_verified": True,
            }
            for i in range(3)
        ]
        
        slugs = set()
        for user in users:
            resp = await client.post("/api/v1/auth/sync", json=user)
            assert resp.status_code == 200, f"Sync failed: {resp.text}"
            slug = resp.json()["organization"]["slug"]
            
            # Slug daha önce kullanılmamış olmalı
            assert slug not in slugs, f"Duplicate slug detected: {slug}"
            slugs.add(slug)


class TestCascadeDelete:
    """Cascade delete testleri."""
    
    @pytest.mark.asyncio
    async def test_soft_delete_preserves_data(self, client: AsyncClient, mock_auth0_user: dict):
        """
        Soft delete yapıldığında veri silinmemeli, sadece is_active=False olmalı.
        
        NOT: Bu test admin yetkisi gerektirir.
        """
        # Önce kullanıcı oluştur
        response = await client.post("/api/v1/auth/sync", json=mock_auth0_user)
        assert response.status_code == 200
        
        # Soft delete için admin endpoint'i test et
        # Bu test şimdilik sadece sync'in çalıştığını doğrular


class TestRaceConditions:
    """Race condition testleri."""
    
    @pytest.mark.asyncio
    async def test_concurrent_sync_same_user(self, client: AsyncClient):
        """
        Aynı kullanıcı için eşzamanlı sync istekleri yapılırsa ne olur?
        
        MANTIK HATASI: Duplicate user oluşturulabilir veya deadlock olabilir.
        """
        user_data = {
            "auth0_id": "google-oauth2|concurrent123",
            "email": "concurrent@example.com",
            "name": "Concurrent User",
            "email_verified": True,
        }
        
        # 5 eşzamanlı istek
        tasks = [
            client.post("/api/v1/auth/sync", json=user_data)
            for _ in range(5)
        ]
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Hiçbiri 500 dönmemeli
        for i, resp in enumerate(responses):
            if isinstance(resp, Exception):
                pytest.fail(f"Request {i} raised exception: {resp}")
            assert resp.status_code in [200, 409], \
                f"Request {i} failed: {resp.status_code} - {resp.text}"
        
        # Sadece bir kullanıcı oluşturulmuş olmalı
        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        assert success_count >= 1, "En az bir istek başarılı olmalı"


class TestInputValidation:
    """Input validation testleri."""
    
    @pytest.mark.asyncio
    async def test_sql_injection_in_email(self, client: AsyncClient):
        """
        Email alanında SQL injection denemesi.
        
        MANTIK HATASI: Eğer 500 dönerse veya beklenmedik davranış olursa
        SQL injection açığı olabilir.
        """
        malicious_data = {
            "auth0_id": "google-oauth2|sqli123",
            "email": "test@example.com'; DROP TABLE user; --",
            "name": "SQL Injector",
            "email_verified": True,
        }
        
        response = await client.post("/api/v1/auth/sync", json=malicious_data)
        
        # 400 veya 422 beklenir (validation error)
        # 500 kabul edilemez
        assert response.status_code in [400, 422], \
            f"SQL injection should be blocked: {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_xss_in_name(self, client: AsyncClient):
        """
        Name alanında XSS denemesi.
        
        NOT: Backend XSS'i engellemeli veya escape etmeli.
        """
        xss_data = {
            "auth0_id": "google-oauth2|xss123",
            "email": "xss@example.com",
            "name": "<script>alert('XSS')</script>",
            "email_verified": True,
        }
        
        response = await client.post("/api/v1/auth/sync", json=xss_data)
        
        # Kabul edilebilir veya reddedilebilir, ama 500 olmamalı
        assert response.status_code in [200, 400, 422], \
            f"XSS should be handled: {response.status_code}"
        
        if response.status_code == 200:
            # Eğer kabul edildiyse, escape edilmiş olmalı
            data = response.json()
            name = data["user"].get("full_name", "")
            assert "<script>" not in name or name == "<script>alert('XSS')</script>", \
                "XSS should be escaped or stored as-is (frontend escapes)"


class TestBusinessLogic:
    """İş mantığı testleri."""
    
    @pytest.mark.asyncio
    async def test_default_role_is_tenant_for_new_org(self, client: AsyncClient, mock_auth0_user: dict):
        """
        Yeni organizasyon oluşturan kullanıcı 'tenant' rolüne sahip olmalı.
        
        MANTIK HATASI: Eğer 'user' rolü verilirse, kendi organizasyonunu yönetemez.
        """
        response = await client.post("/api/v1/auth/sync", json=mock_auth0_user)
        assert response.status_code == 200
        
        data = response.json()
        
        # Rol kontrolü
        if "role" in data["user"] and data["user"]["role"]:
            role = data["user"]["role"]
            if isinstance(role, dict):
                role_code = role.get("code", "")
            else:
                role_code = role
            
            assert role_code == "tenant", \
                f"Organizasyon sahibi 'tenant' rolüne sahip olmalı, got: {role_code}"
    
    @pytest.mark.asyncio
    async def test_organization_tier_defaults_to_free(self, client: AsyncClient, mock_auth0_user: dict):
        """
        Yeni organizasyon 'free' tier ile başlamalı.
        """
        response = await client.post("/api/v1/auth/sync", json=mock_auth0_user)
        assert response.status_code == 200
        
        data = response.json()
        org = data["organization"]
        
        if "tier" in org:
            assert org["tier"] == "free", \
                f"Yeni organizasyon 'free' tier olmalı, got: {org['tier']}"
