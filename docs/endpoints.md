# Endpoints

## Auth

### auth/register

**Required Data:**

- username: Min Length: 4, Max Length: 16
- password: Min Length: 8
- email

**Response:**

- errors: `USER_ALREADY_EXISTS (400)`, `INCORRECT_FORMAT (400)`, `USERNAME_EXISTS (400)`, `USER_DOES_NOT_EXISTS (500)`
- data: `access` & `refresh`
- codes: `201`, `500`, `400`

### auth/login

**Required Data:**

- password: Min Length: 8
- email

**Response:**

- errors: `INCORRECT_PASSWORD (400)`, `USER_DOES_NOT_EXIST (400)`
- data: `access` & `refresh`
- codes: `200`, `500`, `400`

### auth/refresh

**Required Data:**

- refresh_token

**Response:**

- errors: `INVALID_SIGNATURE (400)`, `INVALID_TOKEN_FORMAT (400)`, `DECODE_ERROR (400)`, `EXPIRED_TOKEN (400)`, `INVALID_TOKEN (400)`
- data: `access` & `refresh`
- codes: `200`, `500`, `400`

### auth/logout

**Response:**

- codes: `204`, `500`, `400`
