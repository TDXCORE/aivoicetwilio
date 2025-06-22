"""
bot.py – Pipecat + Twilio + FastAPI
2025-06-22 - FINAL VERSION WITH WEBSOCKET DEBUG ACTIVATED
"""

# ───────────────────────────── Logger global ──────────────────────────────
from loguru import logger
import sys, os, datetime as dt

logger.remove()  # limpia los handlers por defecto

# Consola (DEBUG)
logger.add(
    sys.stderr,
    level="DEBUG",
    format="[{time:HH:mm:ss.SSS}] {level} | {message}",
)

# Archivo rotativo diario
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
logger.add(
    f"{LOG_DIR}/{dt.date.today():%Y-%m-%d}.log",
    rotation="00:00",
    retention="7 days",
    enqueue=True,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {module}:{line} - {message}",
)

# ───────────────────────────── Imports Libs ──────────────────────────────
import json, os, asyncio
from typing import Union

from dotenv import load_dotenv
from fastapi import Request, WebSocket

import openai
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from openai._types import NOT_GIVEN
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.frames.frames import (
    AudioRawFrame,
    TextFrame,
    TranscriptionFrame,
    LLMMessagesFrame,
)

from pipecatcloud.agent import WebSocketSessionArguments

load_dotenv(override=True)

# ───────────────────────────── Core WebSocket flow ───────────────────────
async def main(ws: WebSocket) -> None:
    logger.info("🚀 FINAL VERSION - VAD ENABLED FOR AUDIO PROCESSING")
    logger.info("🔖 VERSION TIMESTAMP: 2025-06-22-03:05 - VAD ACTIVATED")
    
    try:
        # ───── SIMPLE TWILIO HANDSHAKE ─────
        start_iter = ws.iter_text()
        handshake = await start_iter.__anext__()
        logger.info(f"📨 Handshake: {handshake}")
        
        start_msg = await start_iter.__anext__()
        logger.info(f"📨 Start message: {start_msg}")
        
        start_data = json.loads(start_msg)
        stream_sid = start_data["start"]["streamSid"]
        call_sid = start_data["start"]["callSid"]
        
        # ───── DEBUGGING TWILIO STREAM ─────
        logger.info(f"📊 Start data keys: {list(start_data['start'].keys())}")
        logger.info(f"📊 Media format: {start_data['start'].get('mediaFormat', 'NOT_FOUND')}")
        
        # Check tracks configuration
        tracks = start_data["start"].get("tracks", [])
        logger.info(f"🎯 TRACKS CONFIGURED BY TWILIO: {tracks}")
        
        if "inbound" in tracks:
            logger.info("✅ INBOUND TRACK DETECTED - Should receive audio from caller")
        if "outbound" in tracks:
            logger.info("✅ OUTBOUND TRACK DETECTED - Can send audio to caller")
        if not tracks:
            logger.warning("⚠️ NO TRACKS CONFIGURED - This might be the problem")
        
        # Log the complete start message for debugging
        logger.info(f"📊 Complete start data: {json.dumps(start_data, indent=2)}")

        # ───── CREAR SERVICIOS ─────
        logger.info("🔧 Creating services...")
        
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        )

        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            language="es",
            sample_rate=8000,
            audio_passthrough=True,
        )
        
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"), 
            model="gpt-4o-mini"
        )
        
        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",  # Valid Cartesia voice
        )

        # ───── CONTEXTO LLM ─────
        messages = [
            {
                "role": "system",
                "content": "Eres Lorenzo, un asistente de voz amigable. Responde en español de forma natural y breve."
            }
        ]
        context = OpenAILLMContext(messages, NOT_GIVEN)
        ctx_aggr = llm.create_context_aggregator(context)

        # ───── TRANSPORT CON VAD ACTIVADO ─────
        logger.info("🔧 Creating transport WITH VAD...")
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=SileroVADAnalyzer(),  # ✅ VAD ACTIVADO
                serializer=serializer,
            ),
        )

        # ───── PIPELINE ─────
        logger.info("🔧 Creating pipeline...")
        pipeline = Pipeline([
            transport.input(),
            stt,
            ctx_aggr.user(),
            llm,
            tts,
            transport.output(),
            ctx_aggr.assistant(),
        ])

        # ───── TASK ─────
        logger.info("🔧 Creating task...")
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )

        # ───── SALUDO SIMPLE DESPUÉS DE CREAR TASK ─────
        async def send_greeting():
            await asyncio.sleep(1)  # Wait for pipeline to be ready
            logger.info("👋 Sending greeting...")
            greeting = TextFrame("¡Hola! Soy Lorenzo, tu asistente de voz. ¿En qué puedo ayudarte?")
            await task.queue_frame(greeting)
            logger.info("✅ Greeting queued")

        # Enviar saludo en background
        asyncio.create_task(send_greeting())

        # ───── WEBSOCKET DEBUG DESACTIVADO PARA PERMITIR PIPELINE ─────
        logger.info("🔧 WebSocket debug DISABLED - Pipeline will process audio")
        
        # El debug anterior confirmó que el audio llega correctamente
        # Ahora necesitamos que Pipecat procese ese audio
        
        # ❌ NO ACTIVAR DEBUG - INTERFIERE CON EL PIPELINE
        # asyncio.create_task(debug_websocket())
        
        logger.info("🎵 Audio should now flow through Pipecat pipeline to Deepgram")
        
        # ───── MONITOREO DE ESTADO ─────
        async def monitor_stats():
            while True:
                await asyncio.sleep(5)  # Every 5 seconds
                logger.info(f"📊 PIPELINE RUNNING - Waiting for audio processing...")
                
                # Force garbage collection to see if it helps
                import gc
                gc.collect()

        # Start monitoring
        asyncio.create_task(monitor_stats())

        # ───── EJECUTAR PIPELINE ─────
        logger.info("🚀 Starting pipeline...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)

    except Exception as e:
        logger.exception(f"💥 Pipeline error: {e}")

# ───────────────────────────── SMS/WhatsApp webhook ──────────────────────
async def handle_twilio_request(request: Request):
    logger.info("📱 Handling Twilio SMS/WhatsApp request")
    try:
        data = await request.form()
        logger.info(f"📨 Form data: {dict(data)}")

        body = data.get("Body", "")
        from_n = data.get("From", "?")
        to_n = data.get("To", "?")
        
        logger.info(f"📱 SMS from {from_n} to {to_n}: '{body}'")

        reply = f"Recibido: {body}"
        response = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>{reply}</Message></Response>'
        )
        
        return response
        
    except Exception as e:
        logger.exception(f"💥 Error handling SMS/WhatsApp request: {e}")
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>Error procesando mensaje</Message></Response>'
        )

# ───────────────────────────── Entry Point wrapper ───────────────────────
async def bot(args: Union[WebSocketSessionArguments, WebSocket, Request]):
    logger.info(f"🎯 Bot entry - type: {type(args)}")

    try:
        if isinstance(args, WebSocketSessionArguments):
            await main(args.websocket)
        elif isinstance(args, WebSocket):
            await main(args)
        elif isinstance(args, Request):
            return await handle_twilio_request(args)
        else:
            logger.error(f"❌ Unsupported type: {type(args)}")
            
    except Exception as e:
        logger.exception(f"💥 Error in bot entry: {e}")
        raise

# ───────────────────────────── Health Check ──────────────────────────────
async def health_check():
    """Simple health check endpoint"""
    logger.info("🏥 Health check")
    return {"status": "healthy", "timestamp": dt.datetime.now().isoformat()}