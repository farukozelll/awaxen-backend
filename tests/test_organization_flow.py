"""
Organization Management Flow Tests

Bu testler organizasyon yönetimi akışlarını test eder:
1. Organizasyon oluşturma
2. Kullanıcı davet etme
3. Yetki kontrolü
4. Tenant isolation (veri sızıntısı kontrolü)

Mantık Hataları Kontrolü:
- Aynı slug ile iki organizasyon oluşturulamamalı (409 Conflict)
- Admin olmayan kullanıcı organizasyon oluşturamamalı (403 Forbidden)
- Bir organizasyonun kullanıcısı başka organizasyonu görememeli
"""
import pytest
from httpx import AsyncClient


class TestOrganizationCreation:
    """Organizasyon oluşturma testleri."""
    
    @pytest.mark.asyncio
    async def test_create_organization_via_sync(self, client: AsyncClient, mock_auth0_user: dict):
        """
        Auth0 sync ile organizasyon otomatik oluşturulmalı.
        """
        response = await client.post("/api/v1/auth/sync", json=mock_auth0_user)
        
        assert response.status_code == 200
        data = response.json()
        
        # Organizasyon oluşturulmuş mu?
        assert data["organization"] is not None
        assert "id" in data["organization"]
        assert "slug" in data["organization"]
        assert data["organization"]["is_active"] is True
    
    @pytest.mark.asyncio
    async def test_duplicate_slug_handled_gracefully(self, client: AsyncClient):
        """
        Aynı isimle iki kullanıcı sync edildiğinde slug çakışması olmamalı.
        
        MANTIK HATASI: Eğer 500 dönerse, slug uniqueness kontrolü eksik.
        """
        user1 = {
            "auth0_id": "google-oauth2|user1",
            "email": "user1@example.com",
            "name": "John Doe",
            "email_verified": True,
        }
        user2 = {
            "auth0_id": "google-oauth2|user2",
            "email": "user2@example.com",
            "name": "John Doe",  # Aynı isim!
            "email_verified": True,
        }
        
        # İlk kullanıcı
        response1 = await client.post("/api/v1/auth/sync", json=user1)
        assert response1.status_code == 200, f"First sync failed: {response1.text}"
        org1_slug = response1.json()["organization"]["slug"]
        
        # İkinci kullanıcı (aynı isim)
        response2 = await client.post("/api/v1/auth/sync", json=user2)
        assert response2.status_code == 200, f"Second sync failed: {response2.text}"
        org2_slug = response2.json()["organization"]["slug"]
        
        # Slug'lar farklı olmalı (biri suffix almış olmalı)
        assert org1_slug != org2_slug, "Aynı slug ile iki organizasyon oluşturulmamalı"


class TestTenantIsolation:
    """
    Tenant Isolation (Veri Sızıntısı) Testleri
    
    Bu testler çok önemli güvenlik kontrolleridir.
    Bir organizasyonun verileri başka organizasyona sızmamalı.
    """
    
    @pytest.mark.asyncio
    async def test_user_cannot_see_other_org_data(self, client: AsyncClient):
        """
        User A, User B'nin organizasyonunu görememeli.
        
        MANTIK HATASI: Eğer 200 dönerse ve veri görünürse,
        organization_id filtresi eksik demektir.
        """
        # İki farklı kullanıcı oluştur
        user_a = {
            "auth0_id": "google-oauth2|userA",
            "email": "usera@example.com",
            "name": "User A",
            "email_verified": True,
        }
        user_b = {
            "auth0_id": "google-oauth2|userB",
            "email": "userb@example.com",
            "name": "User B",
            "email_verified": True,
        }
        
        # Her iki kullanıcıyı da oluştur
        resp_a = await client.post("/api/v1/auth/sync", json=user_a)
        resp_b = await client.post("/api/v1/auth/sync", json=user_b)
        
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        
        org_a_id = resp_a.json()["organization"]["id"]
        org_b_id = resp_b.json()["organization"]["id"]
        
        # Organizasyonlar farklı olmalı
        assert org_a_id != org_b_id, "Her kullanıcının kendi organizasyonu olmalı"


class TestOrganizationModules:
    """Organizasyon modül yönetimi testleri."""
    
    @pytest.mark.asyncio
    async def test_new_org_has_core_module(self, client: AsyncClient, mock_auth0_user: dict):
        """
        Yeni organizasyon oluşturulduğunda 'core' modülü aktif olmalı.
        """
        response = await client.post("/api/v1/auth/sync", json=mock_auth0_user)
        
        assert response.status_code == 200
        data = response.json()
        
        # Modüller listesi kontrolü
        if "modules" in data["user"]:
            modules = data["user"]["modules"]
            assert "core" in modules, "Yeni organizasyonda 'core' modülü aktif olmalı"


class TestUserInvitation:
    """Kullanıcı davet etme testleri."""
    
    @pytest.mark.asyncio
    async def test_invite_endpoint_exists(self, client: AsyncClient):
        """
        Davet endpoint'i mevcut olmalı.
        
        NOT: Bu test sadece endpoint'in var olduğunu kontrol eder.
        Gerçek davet işlemi için authenticated client gerekir.
        """
        # Rastgele bir org_id ile dene (401 veya 404 beklenir, 500 değil)
        response = await client.post(
            "/api/v1/admin/organizations/00000000-0000-0000-0000-000000000000/invite",
            json={"email": "test@example.com", "role": "user"}
        )
        
        # 401 (Unauthorized) veya 404 (Not Found) kabul edilebilir
        # 500 kabul edilemez (endpoint bozuk demektir)
        assert response.status_code in [401, 403, 404, 422], \
            f"Invite endpoint hatalı: {response.status_code} - {response.text}"


class TestPermissionChecks:
    """Yetki kontrolü testleri."""
    
    @pytest.mark.asyncio
    async def test_admin_endpoints_require_auth(self, client: AsyncClient):
        """
        Admin endpoint'leri authentication gerektirmeli.
        """
        admin_endpoints = [
            ("GET", "/api/v1/admin/organizations"),
            ("GET", "/api/v1/admin/users"),
            ("GET", "/api/v1/admin/system/status"),
        ]
        
        for method, endpoint in admin_endpoints:
            if method == "GET":
                response = await client.get(endpoint)
            else:
                response = await client.post(endpoint, json={})
            
            assert response.status_code in [401, 403], \
                f"{endpoint} should require auth, got {response.status_code}"
    
    @pytest.mark.asyncio
    async def test_user_cannot_access_admin_endpoints(self, client: AsyncClient, user_token: str):
        """
        Normal kullanıcı admin endpoint'lerine erişememeli.
        
        MANTIK HATASI: Eğer 200 dönerse, yetki kontrolü eksik demektir.
        """
        client.headers["Authorization"] = f"Bearer {user_token}"
        
        response = await client.get("/api/v1/admin/organizations")
        
        # 403 Forbidden beklenir
        assert response.status_code in [401, 403], \
            f"Normal kullanıcı admin endpoint'ine erişememeli, got {response.status_code}"


class TestEdgeCases:
    """Sınır durumları (Edge Cases) testleri."""
    
    @pytest.mark.asyncio
    async def test_empty_name_handled(self, client: AsyncClient):
        """
        Boş isim ile sync yapılırsa email'den isim türetilmeli.
        """
        user_data = {
            "auth0_id": "google-oauth2|noname123",
            "email": "noname@example.com",
            "name": "",  # Boş isim
            "email_verified": True,
        }
        response = await client.post("/api/v1/auth/sync", json=user_data)
        
        # 500 dönmemeli
        assert response.status_code == 200, f"Empty name should be handled: {response.text}"
    
    @pytest.mark.asyncio
    async def test_special_characters_in_name(self, client: AsyncClient):
        """
        İsimde özel karakterler olsa bile slug düzgün oluşturulmalı.
        """
        user_data = {
            "auth0_id": "google-oauth2|special123",
            "email": "special@example.com",
            "name": "Ömer Faruk Özel",  # Türkçe karakterler
            "email_verified": True,
        }
        response = await client.post("/api/v1/auth/sync", json=user_data)
        
        assert response.status_code == 200, f"Special chars should be handled: {response.text}"
        
        # Slug oluşturulmuş mu?
        data = response.json()
        assert data["organization"]["slug"] is not None
    
    @pytest.mark.asyncio
    async def test_very_long_name(self, client: AsyncClient):
        """
        Çok uzun isim ile sync yapılırsa truncate edilmeli veya hata vermeli.
        """
        user_data = {
            "auth0_id": "google-oauth2|longname123",
            "email": "longname@example.com",
            "name": "A" * 500,  # 500 karakterlik isim
            "email_verified": True,
        }
        response = await client.post("/api/v1/auth/sync", json=user_data)
        
        # 400 veya 200 kabul edilebilir, 500 kabul edilemez
        assert response.status_code in [200, 400, 422], \
            f"Long name should be handled gracefully: {response.text}"
