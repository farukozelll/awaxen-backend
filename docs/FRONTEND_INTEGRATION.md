# 🔗 Awaxen Frontend Entegrasyon Rehberi

Bu dokümantasyon, frontend uygulamalarının Awaxen Backend API'si ile nasıl entegre olacağını açıklar.

## 📋 İçindekiler

1. [Sistem Mimarisi](#sistem-mimarisi)
2. [Auth0 Entegrasyonu](#auth0-entegrasyonu)
3. [API Endpoint'leri](#api-endpointleri)
4. [Kimlik Doğrulama Akışı](#kimlik-doğrulama-akışı)
5. [Örnek Kodlar](#örnek-kodlar)

---

## 🏗️ Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js)                       │
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │   Auth0     │    │   API       │    │   State     │          │
│  │   Provider  │───▶│   Client    │───▶│   Store     │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTPS + JWT Bearer Token
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      NGINX REVERSE PROXY                         │
│                        (Port 80/443)                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND                              │
│                       (Port 8000)                                │
│                                                                   │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│  │   Auth0     │    │   Auth      │    │   Other     │          │
│  │   Verify    │───▶│   Module    │───▶│   Modules   │          │
│  └─────────────┘    └─────────────┘    └─────────────┘          │
│                              │                                    │
│                              ▼                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    PostgreSQL + TimescaleDB                  │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔐 Auth0 Entegrasyonu

### Auth0 Yapılandırması

```env
# Frontend .env
NEXT_PUBLIC_AUTH0_DOMAIN=awaxen.eu.auth0.com
NEXT_PUBLIC_AUTH0_CLIENT_ID=2Iwki6ZIelRRT7S9L78epYaPCJKdd9gJ
NEXT_PUBLIC_AUTH0_AUDIENCE=https://api.awaxen.com
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Auth0 Provider Kurulumu (Next.js)

```typescript
// app/providers.tsx
'use client';

import { Auth0Provider } from '@auth0/auth0-react';

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <Auth0Provider
      domain={process.env.NEXT_PUBLIC_AUTH0_DOMAIN!}
      clientId={process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID!}
      authorizationParams={{
        redirect_uri: typeof window !== 'undefined' ? window.location.origin : '',
        audience: process.env.NEXT_PUBLIC_AUTH0_AUDIENCE,
        scope: 'openid profile email',
      }}
      cacheLocation="localstorage"
    >
      {children}
    </Auth0Provider>
  );
}
```

---

## 🔄 Kimlik Doğrulama Akışı

### Adım 1: Auth0 ile Giriş

```typescript
// hooks/useAuth.ts
import { useAuth0 } from '@auth0/auth0-react';

export function useAuth() {
  const { 
    loginWithRedirect, 
    logout, 
    user, 
    isAuthenticated, 
    getAccessTokenSilently 
  } = useAuth0();

  const login = () => loginWithRedirect();
  
  const handleLogout = () => logout({ 
    logoutParams: { returnTo: window.location.origin } 
  });

  return {
    login,
    logout: handleLogout,
    user,
    isAuthenticated,
    getAccessTokenSilently,
  };
}
```

### Adım 2: Token ile Backend'e Sync İsteği

**İlk giriş sonrası kullanıcıyı Postgres'e senkronize etmek için:**

```typescript
// services/auth.ts
import { apiClient } from './api-client';

interface SyncRequest {
  auth0_id: string;
  email: string;
  name?: string;
  role?: string;
}

interface SyncResponse {
  status: 'created' | 'synced';
  message: string;
  user: UserProfile;
  organization: Organization | null;
}

export async function syncUser(data: SyncRequest): Promise<SyncResponse> {
  const response = await apiClient.post('/api/v1/auth/sync', data);
  return response.data;
}
```

### Adım 3: Kullanıcı Bilgilerini Al

```typescript
// services/auth.ts
interface UserProfile {
  id: string;
  auth0_id: string;
  email: string;
  full_name: string | null;
  phone: string | null;
  telegram_username: string | null;
  role: {
    code: string;
    name: string;
  } | null;
  permissions: string[];
  organization: Organization | null;
  is_active: boolean;
  created_at: string;
}

export async function getMe(): Promise<UserProfile> {
  const response = await apiClient.get('/api/v1/auth/me');
  return response.data;
}
```

### Tam Akış Örneği

```typescript
// hooks/useAuthSync.ts
import { useAuth0 } from '@auth0/auth0-react';
import { useEffect, useState } from 'react';
import { syncUser, getMe } from '@/services/auth';
import { apiClient } from '@/services/api-client';

export function useAuthSync() {
  const { user, isAuthenticated, getAccessTokenSilently } = useAuth0();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function syncAndFetch() {
      if (!isAuthenticated || !user) {
        setLoading(false);
        return;
      }

      try {
        // 1. Token al
        const token = await getAccessTokenSilently();
        
        // 2. API client'a token ekle
        apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;

        // 3. Kullanıcıyı sync et (ilk giriş veya güncelleme)
        await syncUser({
          auth0_id: user.sub!,
          email: user.email!,
          name: user.name,
        });

        // 4. Profil bilgilerini al
        const userProfile = await getMe();
        setProfile(userProfile);
      } catch (error) {
        console.error('Auth sync failed:', error);
      } finally {
        setLoading(false);
      }
    }

    syncAndFetch();
  }, [isAuthenticated, user, getAccessTokenSilently]);

  return { profile, loading };
}
```

---

## 📡 API Endpoint'leri

### Base URL

```
Development: http://localhost:8000
Production:  https://api.awaxen.com
```

### Auth Endpoints

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/api/v1/auth/me` | Kullanıcı profili | ✅ |
| `PATCH` | `/api/v1/auth/me` | Profil güncelleme | ✅ |
| `POST` | `/api/v1/auth/sync` | Auth0 senkronizasyonu | ❌ |

### Dashboard Endpoints

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/api/v1/dashboard/summary` | Dashboard özet bilgileri | ✅ |

### Notification Endpoints

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/api/v1/notifications` | Bildirim listesi (pagination) | ✅ |
| `PATCH` | `/api/v1/notifications/read` | Bildirimleri okundu işaretle | ✅ |
| `GET` | `/api/v1/notifications/unread-count` | Okunmamış bildirim sayısı | ✅ |

### IoT Endpoints

| Method | Endpoint | Açıklama | Auth |
|--------|----------|----------|------|
| `GET` | `/api/v1/iot/gateways` | Gateway listesi (pagination) | ✅ |
| `GET` | `/api/v1/iot/gateways/{id}` | Gateway detayı | ✅ |
| `POST` | `/api/v1/iot/gateways` | Yeni gateway oluştur | ✅ |
| `GET` | `/api/v1/iot/devices` | Cihaz listesi | ✅ |
| `GET` | `/api/v1/iot/devices/{id}` | Cihaz detayı | ✅ |
| `POST` | `/api/v1/iot/telemetry` | Telemetri verisi kaydet | ✅ |
| `GET` | `/api/v1/iot/telemetry/query` | Telemetri sorgula | ✅ |

> **Not:** Tüm endpoint'ler hem `/api/v1/...` hem de `/api/...` prefix'leri ile erişilebilir (backward compatibility).

### Detaylı Endpoint Açıklamaları

#### 1. POST /api/v1/auth/sync

Auth0 kullanıcısını Postgres veritabanına senkronize eder. İlk girişte kullanıcı, organizasyon ve cüzdan oluşturulur.

**Request:**
```json
{
  "auth0_id": "google-oauth2|123456789",
  "email": "user@awaxen.com",
  "name": "Ahmet Yılmaz",
  "role": "admin"
}
```

**Response (200 - Mevcut kullanıcı):**
```json
{
  "status": "synced",
  "message": "Kullanıcı senkronize edildi",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "auth0_id": "google-oauth2|123456789",
    "email": "user@awaxen.com",
    "full_name": "Ahmet Yılmaz",
    "role": {
      "code": "admin",
      "name": "Admin"
    },
    "permissions": ["can_view_devices", "can_edit_devices"],
    "organization": {
      "id": "...",
      "name": "Ahmet's Organization",
      "slug": "ahmet-organization"
    }
  },
  "organization": { ... }
}
```

**Response (201 - Yeni kullanıcı):**
```json
{
  "status": "created",
  "message": "Yeni kullanıcı oluşturuldu",
  "user": { ... },
  "organization": { ... }
}
```

#### 2. GET /api/v1/auth/me

Token'daki kullanıcının profil bilgisini döner.

**Headers:**
```
Authorization: Bearer <jwt_token>
```

**Response (200):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "auth0_id": "google-oauth2|123456789",
  "email": "user@awaxen.com",
  "full_name": "Ahmet Yılmaz",
  "phone": "+905551112233",
  "telegram_username": "ahmetyilmaz",
  "role": {
    "code": "admin",
    "name": "Admin"
  },
  "permissions": [
    "can_view_devices",
    "can_edit_devices",
    "can_delete_devices"
  ],
  "organization": {
    "id": "...",
    "name": "Ahmet's Organization",
    "slug": "ahmet-organization",
    "is_active": true
  },
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z"
}
```

#### 3. PATCH /api/v1/auth/me

Kullanıcı profilini günceller.

**Headers:**
```
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

**Request:**
```json
{
  "full_name": "Ahmet Yılmaz Updated",
  "phone_number": "+905559998877",
  "telegram_username": "ahmet_new"
}
```

**Response (200):**
```json
{
  "message": "Profil güncellendi",
  "user": {
    "id": "...",
    "full_name": "Ahmet Yılmaz Updated",
    "phone": "+905559998877",
    "telegram_username": "ahmet_new",
    ...
  }
}
```

---

## 🛠️ API Client Kurulumu

### Axios ile API Client

```typescript
// services/api-client.ts
import axios from 'axios';

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - Token ekleme
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - Hata yönetimi
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired - redirect to login
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### Auth0 Token ile Otomatik Yenileme

```typescript
// services/api-client-auth0.ts
import axios from 'axios';
import { Auth0Client } from '@auth0/auth0-spa-js';

const auth0 = new Auth0Client({
  domain: process.env.NEXT_PUBLIC_AUTH0_DOMAIN!,
  clientId: process.env.NEXT_PUBLIC_AUTH0_CLIENT_ID!,
  authorizationParams: {
    audience: process.env.NEXT_PUBLIC_AUTH0_AUDIENCE,
  },
});

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
});

apiClient.interceptors.request.use(async (config) => {
  try {
    const token = await auth0.getTokenSilently();
    config.headers.Authorization = `Bearer ${token}`;
  } catch (error) {
    console.error('Failed to get token:', error);
  }
  return config;
});
```

---

## 🔒 Yetki Kontrolü (RBAC)

### Permissions Listesi

| Permission | Açıklama |
|------------|----------|
| `can_view_devices` | Cihazları görüntüleme |
| `can_edit_devices` | Cihaz ekleme/düzenleme |
| `can_delete_devices` | Cihaz silme |
| `can_control_devices` | Cihazları aç/kapat |
| `can_view_automations` | Otomasyonları görüntüleme |
| `can_edit_automations` | Otomasyon ekleme/düzenleme |
| `can_view_wallet` | Cüzdan görüntüleme |
| `can_view_dashboard` | Dashboard görüntüleme |

### Frontend'de Yetki Kontrolü

```typescript
// hooks/usePermissions.ts
import { useAuthSync } from './useAuthSync';

export function usePermissions() {
  const { profile } = useAuthSync();
  
  const hasPermission = (permission: string): boolean => {
    return profile?.permissions?.includes(permission) ?? false;
  };
  
  const hasAnyPermission = (...permissions: string[]): boolean => {
    return permissions.some(p => hasPermission(p));
  };
  
  const hasAllPermissions = (...permissions: string[]): boolean => {
    return permissions.every(p => hasPermission(p));
  };
  
  return { hasPermission, hasAnyPermission, hasAllPermissions };
}

// Kullanım
function DevicesPage() {
  const { hasPermission } = usePermissions();
  
  if (!hasPermission('can_view_devices')) {
    return <AccessDenied />;
  }
  
  return (
    <div>
      {hasPermission('can_edit_devices') && (
        <button>Yeni Cihaz Ekle</button>
      )}
      <DeviceList />
    </div>
  );
}
```

---

## 🚀 Hızlı Başlangıç

### 1. Backend'i Başlat

```bash
# Docker ile
docker-compose up -d

# Veya lokal
uvicorn src.main:app --reload --port 8000
```

### 2. Frontend Kurulumu

```bash
# Bağımlılıkları yükle
npm install @auth0/auth0-react axios

# .env dosyasını oluştur
cp .env.example .env.local
```

### 3. Test Et

```bash
# Swagger UI
open http://localhost:8000/docs

# Health check
curl http://localhost:8000/health
```

---

## 📞 Destek

- **API Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Email:** team@awaxen.com
