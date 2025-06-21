"""
bot.py – Pipecat + Twilio + FastAPI
2025-06-21
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
import json, os
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

from pipecatcloud.agent import WebSocketSessionArguments

load_dotenv(override=True)

# ───────────────────────────── Core WebSocket flow ───────────────────────
async def main(ws: WebSocket) -> None:
    logger.debug("Starting WebSocket bot")

    # Primeros dos mensajes JSON de Twilio
    start_iter = ws.iter_text()
    await start_iter.__anext__()                       # handshake
    call_data = json.loads(await start_iter.__anext__())

    stream_sid = call_data["start"]["streamSid"]
    call_sid   = call_data["start"]["callSid"]
    logger.info(f"Connected: CallSid={call_sid}, StreamSid={stream_sid}")

    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

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

    # ───── Servicios STT / LLM / TTS ─────
    stt = DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        language="es"                     # STT en español
    )
    llm = OpenAILLMService(api_key=os.getenv("OPENAI_API_KEY"), model="gpt-4o-mini")
    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="15d0c2e2-8d29-44c3-be23-d585d5f154a1",   # voz española (Bogotá)
    )

    # ───── Contexto inicial del chat ─────
    messages = [
        {
            "role": "system",
            "content": (
                "Eres **Lorenzo**, SDR de TDX. Hablas siempre en colombiano:\n"
                "1. Saluda breve (≤1 s) SOLO después de oír al usuario.\n"
                "2. Preséntate en una sola frase (≤2 s).\n"
                "3. Sigue el guion Cool Call paso a paso.\n"
                "4. Permite que te interrumpan: si detectas barge-in, terminas tu frase y escuchas."
            ),
        }
    ]
    context = OpenAILLMContext(messages, NOT_GIVEN)
    ctx_aggr = llm.create_context_aggregator(context)

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

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=False,       # el bot termina su frase antes de escuchar
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # ───── Eventos de conexión ─────
    # ───── Eventos de conexión ─────
    @transport.event_handler("on_client_connected")
    async def _on_connect(_transport, client):
        logger.info(f"Client connected: {client}")

    @transport.event_handler("on_vad_detected")
    async def _on_vad_detected(_transport, vad_event):
        if vad_event.duration_ms >= 200:
            FIRST_REPLY = "¡Hola! Soy Lorenzo de TDX, ¿cómo estás?"
            await task.queue_text(FIRST_REPLY)  # helper que pasa por TTS

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnect(_transport, client):
        logger.info(f"Client disconnected: {client}")
        await task.cancel()

    # (Opcional) log cada frame
    # @transport.event_handler("on_frame")
    # async def _on_frame(_transport, frame):
    #     logger.debug(f"Frame {frame.type} len={len(frame.data)}")

    runner = PipelineRunner(handle_sigint=False, force_gc=True)
    try:
        await runner.run(task)
    except Exception:
        logger.exception("Pipeline crashed")

# ───────────────────────────── SMS/WhatsApp webhook ──────────────────────
async def handle_twilio_request(request: Request):
    logger.debug("Handling Twilio SMS/WhatsApp request")
    data = await request.form()
    logger.info(f"Form data: {data}")

    body = data.get("Body", "")
    from_n = data.get("From", "?")
    to_n   = data.get("To", "?")
    logger.info(f"SMS from {from_n} to {to_n}: {body}")

    reply = f"Received: {body}"
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Message>{reply}</Message></Response>'
    )

# ───────────────────────────── Entry Point wrapper ───────────────────────
async def bot(args: Union[WebSocketSessionArguments, WebSocket, Request]):
    logger.info("Bot entry – type=%s", type(args))

    try:
        if isinstance(args, WebSocketSessionArguments):
            await main(args.websocket)
        elif isinstance(args, WebSocket):
            logger.debug("WebSocket branch hit")
            await main(args)
        elif isinstance(args, Request):
            return await handle_twilio_request(args)
        else:
            logger.error("Unsupported request type: %s", type(args))
    except Exception:
        logger.exception("Error in bot entry")
        raise
