const express = require('express');
const pino = require('pino');
const QRCode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const { z } = require('zod');
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

const payloadSchema = z.object({
  to: z.string().trim().min(8),
  reportUrl: z.string().url(),
  name: z.string().trim().min(1).optional(),
});

function normalizePhone(to) {
  const cleaned = to.trim();
  if (cleaned.endsWith('@s.whatsapp.net')) {
    return cleaned;
  }

  const digits = cleaned.replace(/[^\d]/g, '');
  return `${digits}@s.whatsapp.net`;
}

function buildMessage({ name, reportUrl }) {
  const intro = name ? `Hi ${name},` : 'Hi,';
  return `${intro} your report is ready: ${reportUrl}`;
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

async function connectWhatsApp() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_STATE_DIR);

  sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    logger: pino({ level: 'silent' }),
    browser: ['Voicera WhatsApp Link Sender', 'Chrome', '1.0.0'],
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      latestQr = qr;
      logger.info('New WhatsApp QR generated. Scan from your WhatsApp mobile app.');
      qrcodeTerminal.generate(qr, { small: true });
    }

    if (connection) {
      connectionState = connection;
      logger.info({ connection }, 'whatsapp connection update');
    }

    if (connection === 'close') {
      const shouldReconnect =
        (lastDisconnect?.error?.output?.statusCode || 0) !== DisconnectReason.loggedOut;

      logger.warn(
        {
          shouldReconnect,
          reasonCode: lastDisconnect?.error?.output?.statusCode,
        },
        'whatsapp connection closed',
      );

      if (shouldReconnect) {
        await connectWhatsApp();
      }
    }

    if (connection === 'open') {
      latestQr = null;
    }
  });
}

app.get('/health', (_req, res) => {
  res.json({ status: 'ok', connectionState });
});

app.get('/qr', async (_req, res) => {
  if (!latestQr) {
    return res.status(404).json({
      message: 'QR is not currently available. The session may already be connected.',
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
  await connectWhatsApp();
});
