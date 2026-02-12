const express = require('express');
const pino = require('pino');
const QRCode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const { z } = require('zod');
const fs = require('fs/promises');
const path = require('path');
const {
  default: makeWASocket,
  DisconnectReason,
  useMultiFileAuthState,
  delay,
} = require('@whiskeysockets/baileys');

const PORT = Number(process.env.PORT || 8085);
const AUTH_STATE_DIR = process.env.AUTH_STATE_DIR || './auth_state';
const LOG_LEVEL = process.env.LOG_LEVEL || 'info';

const logger = pino({ level: LOG_LEVEL });
const app = express();
app.use(express.json());

let sock;
let latestQr = null;
let connectionState = 'disconnected';
let isConnecting = false;
let reconnectTimer = null;
let reconnectAttempts = 0;
let connectGeneration = 0;

const payloadSchema = z.object({
  to: z.string().trim().min(8),
  reportUrl: z.string().url(),
  name: z.string().trim().min(1).optional(),
});

function normalizePhone(to) {
  const cleaned = to.trim();
  if (cleaned.endsWith('@s.whatsapp.net')) return cleaned;
  const digits = cleaned.replace(/[^\d]/g, '');
  return `${digits}@s.whatsapp.net`;
}

function buildMessage({ name, reportUrl }) {
  const intro = name ? `Hi ${name},` : 'Hi,';
  return `${intro} your Session Analysis is ready ✅\n${reportUrl}`;
}

function getStatusCode(error) {
  return error?.output?.statusCode || error?.data?.statusCode || 0;
}

function computeBackoffMs(attempt) {
  const base = 1200;
  const max = 30000;
  const value = base * 2 ** Math.max(0, attempt - 1);
  return Math.min(value, max);
}

function isRelinkRequiredStatus(code) {
  return (
    code === 405 ||
    code === DisconnectReason.loggedOut ||
    code === DisconnectReason.connectionReplaced ||
    code === DisconnectReason.badSession ||
    code === DisconnectReason.multideviceMismatch
  );
}

async function sendWithRetry(jid, text, retries = 2) {
  let attempt = 0;
  while (attempt <= retries) {
    try {
      return await sock.sendMessage(jid, { text });
    } catch (error) {
      if (attempt === retries) throw error;
      const backoffMs = 500 * 2 ** attempt;
      logger.warn({ attempt: attempt + 1, backoffMs, err: error.message }, 'send failed, retrying');
      await delay(backoffMs);
      attempt += 1;
    }
  }
}

async function clearAuthStateContents() {
  try {
    await fs.mkdir(AUTH_STATE_DIR, { recursive: true });
    const entries = await fs.readdir(AUTH_STATE_DIR, { withFileTypes: true });
    await Promise.all(
      entries.map((entry) => fs.rm(path.join(AUTH_STATE_DIR, entry.name), { recursive: true, force: true })),
    );
    logger.warn({ authDir: AUTH_STATE_DIR, removedEntries: entries.length }, 'auth state contents cleared');
  } catch (error) {
    logger.error({ err: error.message, authDir: AUTH_STATE_DIR }, 'failed to clear auth state contents');
  }
}

function scheduleReconnect(delayMs = 1200) {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWhatsApp('reconnect').catch((error) => {
      logger.error({ err: error.message }, 'reconnect attempt failed');
      scheduleReconnect(computeBackoffMs(reconnectAttempts + 1));
    });
  }, delayMs);
}

async function closeCurrentSocket() {
  try {
    if (sock?.ev && typeof sock.ev.removeAllListeners === 'function') {
      sock.ev.removeAllListeners('connection.update');
      sock.ev.removeAllListeners('creds.update');
    }
  } catch {}

  try {
    sock?.ws?.close?.();
  } catch {}
}

async function connectWhatsApp(reason = 'init') {
  if (isConnecting) return;
  isConnecting = true;
  const generation = ++connectGeneration;

  try {
    await closeCurrentSocket();

    const { state, saveCreds } = await useMultiFileAuthState(AUTH_STATE_DIR);

    sock = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      logger: pino({ level: 'silent' }),
      browser: ['Voicera WhatsApp Link Sender', 'Chrome', '1.0.0'],
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', async (update) => {
      if (generation !== connectGeneration) return;

      const { connection, lastDisconnect, qr } = update;
      const reasonCode = getStatusCode(lastDisconnect?.error);

      if (qr) {
        latestQr = qr;
        connectionState = 'qr_ready';
        logger.info({ reason }, 'New WhatsApp QR generated. Scan from your WhatsApp mobile app.');
        qrcodeTerminal.generate(qr, { small: true });
      }

      if (connection) {
        connectionState = connection;
        logger.info({ connection }, 'whatsapp connection update');
      }

      if (connection === 'open') {
        latestQr = null;
        connectionState = 'open';
        reconnectAttempts = 0;
        logger.info('whatsapp connected');
        return;
      }

      if (connection === 'close') {
        const relinkRequired = isRelinkRequiredStatus(reasonCode);
        const restartRequired = reasonCode === DisconnectReason.restartRequired;
        const shouldReconnect = !relinkRequired && !restartRequired;

        logger.warn(
          {
            shouldReconnect,
            reasonCode,
            relinkRequired,
            restartRequired,
          },
          'whatsapp connection closed',
        );

        if (relinkRequired) {
          latestQr = null;
          connectionState = 'relink_required';
          await clearAuthStateContents();
          logger.warn(
            { reasonCode },
            'relink required; auth state cleared. Open /qr to generate a fresh pairing code.',
          );
          return;
        }

        if (restartRequired) {
          reconnectAttempts += 1;
          scheduleReconnect(500);
          return;
        }

        if (shouldReconnect) {
          reconnectAttempts += 1;
          scheduleReconnect(computeBackoffMs(reconnectAttempts));
        }
      }
    });
  } finally {
    isConnecting = false;
  }
}

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', connectionState, reconnectAttempts });
});

app.get('/qr', async (_req, res) => {
  if (!latestQr && connectionState !== 'open') {
    await connectWhatsApp('qr-request');
    await delay(1200);
  }

  if (!latestQr) {
    return res.status(404).json({
      message: 'QR is not currently available. The session may already be connected.',
      connectionState,
    });
  }

  const qrDataUrl = await QRCode.toDataURL(latestQr);
  return res.json({ connectionState, qrDataUrl });
});

app.post('/send-report-link', async (req, res) => {
  const parsed = payloadSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({
      error: 'invalid_payload',
      issues: parsed.error.flatten(),
    });
  }

  if (!sock || connectionState !== 'open') {
    return res.status(503).json({
      error: 'whatsapp_not_connected',
      message: 'WhatsApp session is not connected. Scan QR first via GET /qr.',
    });
  }

  const { to, reportUrl, name } = parsed.data;
  const jid = normalizePhone(to);
  const text = buildMessage({ name, reportUrl });

  try {
    const result = await sendWithRetry(jid, text, 2);

    logger.info(
      {
        to: jid,
        messageId: result?.key?.id,
      },
      'report link message sent',
    );

    return res.json({
      success: true,
      messageId: result?.key?.id,
    });
  } catch (error) {
    logger.error({ err: error.message, to: jid }, 'failed to send report link');
    return res.status(500).json({
      error: 'send_failed',
      message: 'Failed to send WhatsApp message after retries.',
    });
  }
});

app.use((err, _req, res, _next) => {
  logger.error({ err: err.message }, 'unhandled error');
  res.status(500).json({ error: 'internal_server_error' });
});

app.listen(PORT, async () => {
  logger.info({ port: PORT }, 'whatsapp-link-sender listening');
  await connectWhatsApp('startup');
});
