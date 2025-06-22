"""
bot.py – Pipecat + Twilio + FastAPI
2025-06-22 - WORKING VERSION - CLEAN AND SIMPLE
"""

# ───────────────────────────── Logger global ──────────────────────────────
from loguru import logger
import sys, os, datetime as dt

logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="[{time:HH:mm:ss.SSS}] {level} | {message}",
)

# ───────────────────────────── Imports Libs ──────────────────────────────
import json, os, asyncio
from typing import Union

from dotenv import load_dotenv
from fastapi import Request, WebSocket

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
from pipecat.frames.frames import TextFrame

from pipecatcloud.agent import WebSocketSessionArguments

load_dotenv(override=True)

# ───────────────────────────── Core WebSocket flow ───────────────────────
async def main(ws: WebSocket) -> None:
    logger.info("🚀 WORKING VERSION - CLEAN IMPLEMENTATION")
    logger.info("🔖 VERSION: 2025-06-22-FINAL")
    
    try:
        # ───── TWILIO HANDSHAKE ─────
        start_iter = ws.iter_text()
        await start_iter.__anext__()  # handshake
        start_msg = await start_iter.__anext__()
        start_data = json.loads(start_msg)
        
        stream_sid = start_data["start"]["streamSid"]
        call_sid = start_data["start"]["callSid"]
        
        logger.info(f"📞 CallSid: {call_sid}")
        logger.info(f"📞 StreamSid: {stream_sid}")

        # ───── CREAR SERVICIOS ─────
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
            voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",
        )

        # ───── CONTEXTO LLM ─────
        messages = [
            {
                "role": "system",
                "content": "Eres Lorenzo, un asistente de voz amigable de TDX. Responde en español de forma natural y breve. Máximo 2 oraciones por respuesta."
            }
        ]
        context = OpenAILLMContext(messages, NOT_GIVEN)
        ctx_aggr = llm.create_context_aggregator(context)

        # ───── TRANSPORT ─────
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

        # ───── PIPELINE ─────
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

        # ───── SALUDO AUTOMÁTICO ─────
        async def send_greeting():
            await asyncio.sleep(2)  # Wait for pipeline
            logger.info("👋 Sending greeting...")
            greeting = TextFrame("¡Hola! Soy Lorenzo de TDX. ¿En qué puedo ayudarte hoy?")
            await task.queue_frame(greeting)
            logger.info("✅ Greeting sent")

        asyncio.create_task(send_greeting())

        # ───── MONITOREO SIMPLE ─────
        async def simple_monitor():
            while True:
                await asyncio.sleep(10)
                logger.info("📊 Bot running and listening...")

        asyncio.create_task(simple_monitor())

        # ───── EJECUTAR PIPELINE ─────
        logger.info("🚀 Starting pipeline...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)

    except Exception as e:
        logger.exception(f"💥 Error: {e}")

# ───────────────────────────── SMS webhook ──────────────────────────────
async def handle_twilio_request(request: Request):
    logger.info("📱 SMS request")
    try:
        data = await request.form()
        body = data.get("Body", "")
        from_n = data.get("From", "")
        
        logger.info(f"📱 SMS from {from_n}: {body}")
        
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>Recibido: {body}</Message></Response>'
        )
    except Exception as e:
        logger.exception(f"💥 SMS error: {e}")
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>'
            f'<Response><Message>Error</Message></Response>'
        )

# ───────────────────────────── Entry Point ───────────────────────────────
async def bot(args: Union[WebSocketSessionArguments, WebSocket, Request]):
    logger.info(f"🎯 Bot called with: {type(args)}")

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
        logger.exception(f"💥 Bot error: {e}")
        raise

# ───────────────────────────── Health Check ──────────────────────────────
async def health_check():
    logger.info("🏥 Health check")
    return {"status": "healthy", "timestamp": dt.datetime.now().isoformat()}