# Endpoints

## Auth

### auth/register (POST)

> Register account

**Required Data:**

- username: Min Length: 4, Max Length: 16
- password: Min Length: 8
- email

**Response:**

- errors: `USER_ALREADY_EXISTS (409)`, `INCORRECT_FORMAT (400)`, `USERNAME_EXISTS (409)`, `USER_DOES_NOT_EXIST (404)`
- codes: `201`, `409`, `404`, `500`

### auth/login (POST)

> Login to account

**Required Data:**

- password: Min Length: 8
- email

**Response:**

- errors: `INCORRECT_PASSWORD (401)`, `USER_DOES_NOT_EXIST (404)`
- codes: `200`, `500`, `401`, `404`

### auth/refresh (POST)

> Refresh tokens

**Optional Data:**

- refresh_token

**Response:**

- errors: `INVALID_SIGNATURE (400)`, `INVALID_TOKEN_FORMAT (400)`, `DECODE_ERROR (400)`, `EXPIRED_TOKEN (401)`, `INVALID_TOKEN (400)`
- codes: `200`, `500`, `400`, `401`

### auth/logout (POST)

> Delete tokens (auth required)

**Response:**

- codes: `204`, `500`, `400`
