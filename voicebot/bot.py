"""
bot.py – Pipecat + Twilio + FastAPI
2025-06-22 - SIMPLIFIED VERSION - Focus on Working Audio
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
    logger.info("🚀 SIMPLIFIED VERSION 2.0 - Starting WebSocket bot")
    logger.info("🔖 VERSION TIMESTAMP: 2025-06-22-01:05 - SIMPLIFIED AUDIO DEBUG")
    
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

        # ───── TRANSPORT SIN VAD PARA SIMPLIFICAR ─────
        logger.info("🔧 Creating transport...")
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=None,  # Sin VAD por ahora
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

        # ───── ACTIVAR DEBUG DE WEBSOCKET PARA VER TODOS LOS MENSAJES ─────
        logger.info("🔍 ACTIVATING FULL WEBSOCKET DEBUG...")
        
        # Monitor raw WebSocket messages in background
        async def debug_websocket():
            try:
                message_count = 0
                async for raw_message in ws.iter_text():
                    message_count += 1
                    logger.info(f"📨 WS Message #{message_count}: {raw_message[:500]}...")
                    
                    try:
                        msg = json.loads(raw_message)
                        event_type = msg.get('event', 'unknown')
                        logger.info(f"📨 Event type: {event_type}")
                        
                        if event_type == 'media':
                            logger.info(f"🎵 AUDIO DATA RECEIVED! Details: {msg}")
                            nonlocal audio_count
                            audio_count += 1
                        elif event_type == 'start':
                            tracks = msg.get('start', {}).get('tracks', [])
                            logger.info(f"🎯 TRACKS CONFIGURED: {tracks}")
                            if 'inbound' not in tracks and 'both_tracks' not in tracks:
                                logger.error(f"❌ AUDIO TRACKS PROBLEM: {tracks}")
                        elif event_type == 'stop':
                            logger.info(f"🛑 Stream stopped: {msg}")
                            
                    except json.JSONDecodeError:
                        logger.info(f"📨 Non-JSON message: {raw_message}")
                        
            except Exception as e:
                logger.error(f"💥 WebSocket debug error: {e}")
        
        # Start WebSocket debugging - ACTIVAR PARA VER TODOS LOS MENSAJES
        asyncio.create_task(debug_websocket())
        
        # ───── MONITOREO DE ESTADO ─────
        audio_count = 0
        transcript_count = 0
        
        async def monitor_stats():
            nonlocal audio_count, transcript_count
            while True:
                await asyncio.sleep(3)  # Every 3 seconds
                logger.info(f"📊 Audio: {audio_count}, Transcripts: {transcript_count}")
                
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