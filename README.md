# Auth Flow API

Base URL: `http://localhost:8000`

## Endpoints

---

**GET** `/auth/login`

```
headers: { Authorization: "Bearer <google_oauth_token>" }
response: { "message": "Login successful", "user": { "id": 1, "name": "John Doe", "email": "john@gmail.com", "roles": ["employee"] } }
cookie:   auth_token (httponly)
errors:   401 — invalid token
```

---

**GET** `/auth/me`

```
headers: cookie auth_token (auto-sent by browser)
response: { "message": "User validated", "user": { "id": 1, "name": "John Doe", "email": "john@gmail.com", "roles": ["employee", "admin"] } }
errors:   401 — not authenticated / user not found
```

---

**GET** `/auth/protected`

```
headers: cookie auth_token (auto-sent by browser)
response: { "message": "Protected API" }
errors:   401 — not authenticated, 403 — insufficient permissions
```

---

**GET** `/healthcheck`

```
response: { "status": "ok" }
```

---

## Notes

- All auth endpoints require `withCredentials: true` from frontend.
- CORS configured for `http://localhost:5173`.
