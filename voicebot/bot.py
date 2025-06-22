"""
bot.py – Pipecat + Twilio + FastAPI
2025-06-21 - FIXED VERSION - Método Correcto para Enviar Texto
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

# ───────────────────────────── Global State ──────────────────────────────
call_state = {
    "greeted": False,
    "call_sid": None,
    "stream_sid": None,
    "participant_count": 0,
    "audio_frames_received": 0,
    "transcripts_received": 0,
    "llm_responses_sent": 0,
    "tts_responses_sent": 0,
}

# ───────────────────────────── Core WebSocket flow ───────────────────────
async def main(ws: WebSocket) -> None:
    logger.info("🚀 Starting WebSocket bot")
    
    try:
        # Primeros dos mensajes JSON de Twilio
        logger.debug("📥 Waiting for Twilio handshake messages...")
        start_iter = ws.iter_text()
        handshake_msg = await start_iter.__anext__()
        logger.debug(f"📨 Handshake message: {handshake_msg}")
        
        call_data_raw = await start_iter.__anext__()
        logger.debug(f"📨 Call data raw: {call_data_raw}")
        call_data = json.loads(call_data_raw)
        logger.debug(f"📊 Parsed call data: {json.dumps(call_data, indent=2)}")

        stream_sid = call_data["start"]["streamSid"]
        call_sid = call_data["start"]["callSid"]
        
        # Update global state
        call_state["call_sid"] = call_sid
        call_state["stream_sid"] = stream_sid
        
        logger.info(f"📞 Connected: CallSid={call_sid}, StreamSid={stream_sid}")

        # Verificar variables de entorno
        logger.debug("🔑 Checking environment variables...")
        env_vars = {
            "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID"),
            "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN"),
            "DEEPGRAM_API_KEY": os.getenv("DEEPGRAM_API_KEY"),
            "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
            "CARTESIA_API_KEY": os.getenv("CARTESIA_API_KEY"),
        }
        
        for key, value in env_vars.items():
            if value:
                logger.debug(f"✅ {key}: {'*' * (len(value) - 4)}{value[-4:]}")
            else:
                logger.error(f"❌ {key}: NOT SET")

        # Crear serializer
        logger.debug("🔧 Creating Twilio serializer...")
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        )

        # ───── Servicios STT / LLM / TTS (CREAR ANTES DEL TRANSPORT) ─────
        logger.debug("🔧 Creating STT service...")
        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            language="es",
            sample_rate=8000,
            audio_passthrough=True,
        )
        
        logger.debug("🔧 Creating LLM service...")
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"), 
            model="gpt-4o-mini"
        )
        
        logger.debug("🔧 Creating TTS service...")
        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="15d0c2e2-8d29-44c3-be23-d585d5f154a1",
        )

        # ───── Contexto inicial del chat ─────
        logger.debug("🔧 Setting up LLM context...")
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres **Lorenzo**, SDR de TDX. Hablas siempre en español colombiano:\n"
                    "1. Responde de forma natural y conversacional.\n"
                    "2. Mantén respuestas cortas (máximo 2-3 oraciones).\n"
                    "3. Sé amigable y profesional.\n"
                    "4. Permite interrupciones naturales."
                ),
            }
        ]
        context = OpenAILLMContext(messages, NOT_GIVEN)
        ctx_aggr = llm.create_context_aggregator(context)

        # ───── CREAR TRANSPORT ─────
        logger.debug("🔧 Creating FastAPI WebSocket transport...")
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=SileroVADAnalyzer(),
                serializer=serializer,
            ),
        )

        # ───── CREAR PIPELINE ─────
        logger.debug("🔧 Creating pipeline...")
        pipeline = Pipeline(
            [
                transport.input(),
                stt,
                ctx_aggr.user(),
                llm,
                tts,
                transport.output(),
                ctx_aggr.assistant(),
            ]
        )

        # ───── CREAR TASK ─────
        logger.debug("🔧 Creating pipeline task...")
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

        # ───── FUNCIONES DE EVENT HANDLERS CON ACCESO A TASK ─────
        async def on_client_connected(transport, client):
            logger.info(f"👤 Client connected: {client}")
            call_state["participant_count"] += 1
            logger.info(f"👥 Total participants: {call_state['participant_count']}")
            
            # SALUDO USANDO EL MÉTODO CORRECTO
            if not call_state["greeted"]:
                logger.info("👋 Sending immediate greeting...")
                await asyncio.sleep(0.5)
                
                # Crear TextFrame y enviarlo al pipeline
                greeting_frame = TextFrame("¡Hola! Soy Lorenzo de TDX, ¿cómo estás?")
                await task.queue_frame(greeting_frame)
                
                call_state["greeted"] = True
                logger.info("✅ Greeting sent")

        async def on_client_disconnected(transport, client):
            logger.info(f"👤 Client disconnected: {client}")
            call_state["participant_count"] -= 1
            logger.info(f"👥 Total participants: {call_state['participant_count']}")
            logger.info("🛑 Cancelling task due to client disconnect")
            await task.cancel()

        async def on_user_started_speaking(transport, event):
            logger.info("🎤 User started speaking")

        async def on_user_stopped_speaking(transport, event):
            logger.info("🔇 User stopped speaking")

        async def on_frame(transport, frame):
            if isinstance(frame, AudioRawFrame):
                call_state["audio_frames_received"] += 1
                if call_state["audio_frames_received"] % 100 == 0:
                    logger.debug(f"🎵 Audio frames received: {call_state['audio_frames_received']}")
            elif isinstance(frame, TextFrame):
                logger.info(f"📝 Text frame: {frame.text}")
            elif isinstance(frame, TranscriptionFrame):
                call_state["transcripts_received"] += 1
                logger.info(f"📝 Transcription #{call_state['transcripts_received']}: '{frame.text}'")
            else:
                logger.debug(f"📦 Frame received: {type(frame).__name__}")

        # ───── REGISTRAR EVENT HANDLERS ─────
        logger.debug("🔧 Registering transport event handlers...")
        
        # Estos son los eventos básicos que SÍ existen
        transport.add_event_handler("on_client_connected", on_client_connected)
        transport.add_event_handler("on_client_disconnected", on_client_disconnected)
        
        # Para eventos que pueden no existir, usar try/catch
        try:
            transport.add_event_handler("on_user_started_speaking", on_user_started_speaking)
            transport.add_event_handler("on_user_stopped_speaking", on_user_stopped_speaking)
            transport.add_event_handler("on_frame", on_frame)
        except Exception as e:
            logger.warning(f"⚠️ Could not register some event handlers: {e}")

        # ───── EJECUTAR PIPELINE ─────
        logger.info("🚀 Starting pipeline runner...")
        runner = PipelineRunner(handle_sigint=False, force_gc=True)
        
        # Stats logging task
        async def log_stats():
            while True:
                await asyncio.sleep(10)  # Log stats every 10 seconds
                logger.info(
                    f"📊 Stats - Audio: {call_state['audio_frames_received']}, "
                    f"Transcripts: {call_state['transcripts_received']}, "
                    f"LLM: {call_state['llm_responses_sent']}, "
                    f"TTS: {call_state['tts_responses_sent']}"
                )
        
        # Start stats logging in background
        stats_task = asyncio.create_task(log_stats())
        
        try:
            await runner.run(task)
        finally:
            stats_task.cancel()
            logger.info("🛑 Pipeline stopped")

    except Exception as e:
        logger.exception(f"💥 Pipeline crashed: {e}")
        raise

# ───────────────────────────── SMS/WhatsApp webhook ──────────────────────
async def handle_twilio_request(request: Request):
    logger.info("📱 Handling Twilio SMS/WhatsApp request")
    try:
        data = await request.form()
        logger.info(f"📨 Form data: {dict(data)}")

        body = data.get("Body", "")
        from_n = data.get("From", "?")
        to_n = data.get("To", "?")
        message_sid = data.get("MessageSid", "?")
        
        logger.info(f"📱 SMS {message_sid} from {from_n} to {to_n}: '{body}'")

        reply = f"Recibido: {body}"
        response = (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>{reply}</Message></Response>'
        )
        
        logger.info(f"📤 SMS Response: {response}")
        return response
        
    except Exception as e:
        logger.exception(f"💥 Error handling SMS/WhatsApp request: {e}")
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>Error procesando mensaje</Message></Response>'
        )

# ───────────────────────────── Entry Point wrapper ───────────────────────
async def bot(args: Union[WebSocketSessionArguments, WebSocket, Request]):
    logger.info(f"🎯 Bot entry point - type: {type(args)}")
    
    # Reset call state for new session
    call_state.update({
        "greeted": False,
        "call_sid": None,
        "stream_sid": None,
        "participant_count": 0,
        "audio_frames_received": 0,
        "transcripts_received": 0,
        "llm_responses_sent": 0,
        "tts_responses_sent": 0,
    })

    try:
        if isinstance(args, WebSocketSessionArguments):
            logger.info("🔌 WebSocketSessionArguments branch")
            await main(args.websocket)
        elif isinstance(args, WebSocket):
            logger.info("🔌 WebSocket branch")
            await main(args)
        elif isinstance(args, Request):
            logger.info("📱 HTTP Request branch")
            return await handle_twilio_request(args)
        else:
            logger.error(f"❌ Unsupported request type: {type(args)}")
            raise ValueError(f"Unsupported request type: {type(args)}")
            
    except Exception as e:
        logger.exception(f"💥 Error in bot entry point: {e}")
        raise

# ───────────────────────────── Health Check ──────────────────────────────
async def health_check():
    """Simple health check endpoint"""
    logger.info("🏥 Health check requested")
    return {
        "status": "healthy",
        "timestamp": dt.datetime.now().isoformat(),
        "call_state": call_state.copy()
    }