# main.py
from fastapi import FastAPI, WebSocket, Request
from dotenv import load_dotenv
from fastapi.responses import Response
from voicebot.bot import bot
from loguru import logger

app = FastAPI()
load_dotenv()

# ───────── WebSocket para audio ─────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await bot(ws)                 # ← no cambia

# ───────── TwiML de VOZ ─────────
VOICE_TWIML = """
<Response>
  <Connect>
    <!--  ➜  track="both_tracks" habilita ­ audio bidireccional  -->
    <Stream url="wss://aivoicetwilio-vf.onrender.com/ws"
            track="both_tracks"/>
  </Connect>
</Response>
""".strip()

@app.post("/voice-twiml")
async def voice_twiml():
    return Response(content=VOICE_TWIML, media_type="text/xml")

# ───────── Webhook de SMS / WhatsApp ─────────
@app.post("/twilio-sms")
async def sms_endpoint(request: Request):
    logger.debug("SMS/WhatsApp webhook hit")
    return await bot(request)     # tu lógica SMS sigue igual
