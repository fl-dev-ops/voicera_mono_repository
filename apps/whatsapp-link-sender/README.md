# WhatsApp Report Link Sender

Standalone service for sending **one-way outbound WhatsApp report links** using Baileys.

## Features

- `POST /send-report-link` endpoint only (report-link scope)
- QR-based WhatsApp connection (scan once; auth state persisted on disk)
- `GET /qr` endpoint to fetch current login QR as Data URL
- Input validation with `zod`
- Simple retry logic (2 retries with exponential backoff)
- Structured logs using `pino`

## Folder

```bash
apps/whatsapp-link-sender
```

## Prerequisites

- Node.js 18+ (Node 22 tested)
- A WhatsApp account on a mobile device for QR scan

## Setup

```bash
cd apps/whatsapp-link-sender
cp .env.example .env
npm install
```

## Run

```bash
npm start
```

Server starts on `PORT` (default `8085`).

## Connect WhatsApp (QR flow)

When the server starts, a QR is generated and printed in terminal logs.

You can also fetch current QR via API:

```bash
curl http://localhost:8085/qr
```

Response contains `qrDataUrl` (base64 image).

> Auth is persisted to `AUTH_STATE_DIR` (default `./auth_state`), so re-scan is not needed unless the session is logged out.

## API

### Health

```bash
curl http://localhost:8085/health
```

### Send report link

`POST /send-report-link`

Payload:

```json
{
  "to": "9198XXXXXXXX",
  "reportUrl": "https://example.com/reports/abc123",
  "name": "Ravi"
}
```

Example:

```bash
curl -X POST http://localhost:8085/send-report-link \
  -H 'Content-Type: application/json' \
  -d '{
    "to": "9198XXXXXXXX",
    "reportUrl": "https://example.com/reports/abc123",
    "name": "Ravi"
  }'
```

Success response:

```json
{
  "success": true,
  "messageId": "<whatsapp-message-id>"
}
```

## Environment Variables

- `PORT` - HTTP port (default `8085`)
- `AUTH_STATE_DIR` - Folder for persistent Baileys auth (default `./auth_state`)
- `LOG_LEVEL` - Pino log level (default `info`)

## Notes

- This service is intentionally minimal and does not support inbound message workflows.
- Keep this service behind trusted network controls/API gateway for production use.
