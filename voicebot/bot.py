# voicebot/bot.py
import os
import asyncio
import json
from typing import Union
from dotenv import load_dotenv
from fastapi import WebSocket, Request, Response
from loguru import logger

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from openai._types import NOT_GIVEN
from pipecat.frames.frames import TextFrame

# Cargar variables de entorno
load_dotenv(override=True)

SAMPLE_RATE = 8000  # Twilio Media Streams


# ──────────────────────────────────────────
# 1) PIPELINE PARA LLAMADAS DE VOZ (WebSocket)
# ──────────────────────────────────────────
async def _voice_call(ws: WebSocket):
    """Maneja la conexión Media Streams de Twilio."""
    logger.info("🎯 Iniciando pipeline de voz con Twilio handshake...")
    
    try:
        # ───── TWILIO HANDSHAKE (necesario para Media Streams) ─────
        start_iter = ws.iter_text()
        await start_iter.__anext__()  # handshake message
        start_msg = await start_iter.__anext__()  # start message
        start_data = json.loads(start_msg)
        
        stream_sid = start_data["start"]["streamSid"]
        call_sid = start_data["start"]["callSid"]
        
        logger.info(f"📞 CallSid: {call_sid}")
        logger.info(f"📞 StreamSid: {stream_sid}")

        # ───── SERIALIZER CON DATOS DE TWILIO ─────
        serializer = TwilioFrameSerializer(
            stream_sid=stream_sid,
            call_sid=call_sid,
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        )
        logger.info("✅ Twilio serializer creado")

        # ───── SERVICIOS CON TUS API KEYS ─────
        # Deepgram STT mejorado para español
        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            language="es",
            sample_rate=SAMPLE_RATE,
            audio_passthrough=True,
            model="nova-2",              # Modelo más reciente
            smart_format=True,           # Mejora la transcripción
            interim_results=True,        # Resultados parciales
            endpointing=300,             # 300ms para finalizar
        )
        logger.info("✅ Deepgram STT mejorado creado")
        
        # OpenAI LLM
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"), 
            model="gpt-4o-mini"
        )
        logger.info("✅ OpenAI LLM creado")
        
        # Cartesia TTS (tu preferido)
        tts = CartesiaTTSService(
            api_key=os.getenv("CARTESIA_API_KEY"),
            voice_id="a0e99841-438c-4a64-b679-ae501e7d6091",  # Tu voz configurada
            push_silence_after_stop=True,  # Fix para Twilio
        )
        logger.info("✅ Cartesia TTS creado")

        # ───── CONTEXTO LLM ─────
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres Lorenzo, un asistente de voz amigable de TDX. "
                    "Responde en español de forma natural y breve. "
                    "Máximo 2 oraciones por respuesta."
                )
            }
        ]
        context = OpenAILLMContext(messages, NOT_GIVEN)
        ctx_aggr = llm.create_context_aggregator(context)
        logger.info("✅ LLM context creado")

        # ───── VAD SIMPLE (sin parámetros problemáticos) ─────
        vad = SileroVADAnalyzer(sample_rate=SAMPLE_RATE)
        logger.info("✅ Silero VAD creado")

        # ───── TRANSPORT CONFIGURADO PARA TWILIO ─────
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=vad,
                serializer=serializer,
            ),
        )
        logger.info("✅ Transport creado")

        # ───── PIPELINE LIMPIO ─────
        pipeline = Pipeline([
            transport.input(),
            stt,
            ctx_aggr.user(),
            llm,
            tts,
            transport.output(),
            ctx_aggr.assistant(),
        ])
        logger.info("✅ Pipeline creado")

        # ───── TASK Y RUNNER ─────
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                audio_in_sample_rate=SAMPLE_RATE,
                audio_out_sample_rate=SAMPLE_RATE,
                enable_metrics=True,
            ),
        )
        
        # ───── SALUDO AUTOMÁTICO ─────
        async def send_greeting():
            await asyncio.sleep(3)  # Más tiempo para asegurar conexión
            logger.info("👋 Enviando saludo...")
            greeting = TextFrame("¡Hola! Soy Lorenzo de TDX. Te escucho perfectamente. Puedes hablar ahora.")
            await task.queue_frame(greeting)
            logger.info("✅ Saludo enviado")

        asyncio.create_task(send_greeting())

        # ───── EJECUTAR PIPELINE ─────
        logger.info("🚀 Iniciando pipeline de voz...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        logger.info("📞 Llamada finalizada")
        
    except Exception as e:
        logger.exception(f"💥 Error en pipeline de voz: {e}")
        raise


# ──────────────────────────────────────────
# 2) PIPELINE SMS / WHATSAPP (webhook HTTP)
# ──────────────────────────────────────────
async def _sms(request: Request) -> Response:
    """Maneja mensajes SMS/WhatsApp de Twilio."""
    try:
        form = await request.form()
        user_msg = form.get("Body", "") or "..."
        from_number = form.get("From", "")
        
        logger.info(f"💬 SMS de {from_number}: '{user_msg}'")

        # Usar OpenAI para respuesta rápida de texto
        llm = OpenAILLMService(
            api_key=os.getenv("OPENAI_API_KEY"),
            model="gpt-4o-mini"
        )
        
        # Contexto simple para SMS
        context = OpenAILLMContext([
            {
                "role": "system", 
                "content": "Eres Lorenzo, un asistente amigable de TDX. Responde de forma concisa en español."
            },
            {
                "role": "user",
                "content": user_msg
            }
        ], NOT_GIVEN)
        
        # Generar respuesta
        response = await llm._process_context(context)
        reply = response.choices[0].message.content
        
        logger.info(f"🤖 Respuesta SMS: '{reply}'")

        # TwiML para responder
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.exception(f"💥 Error en SMS: {e}")
        # Respuesta de error en TwiML
        error_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error procesando mensaje</Message></Response>'
        return Response(content=error_twiml, media_type="text/xml")


# ──────────────────────────────────────────
# 3) HEALTH CHECK
# ──────────────────────────────────────────
async def health_check():
    """Health check endpoint."""
    logger.info("🏥 Health check")
    return {
        "status": "healthy", 
        "service": "TDX Voice Bot",
        "version": "2025-06-22-PLAN-B-FIXED",
        "apis": {
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
            "openai": bool(os.getenv("OPENAI_API_KEY")),
            "deepgram": bool(os.getenv("DEEPGRAM_API_KEY")),
            "cartesia": bool(os.getenv("CARTESIA_API_KEY")),
        }
    }


# ──────────────────────────────────────────
# 4) PUNTO ÚNICO DE ENTRADA (compatible con tu main.py)
# ──────────────────────────────────────────
async def bot(ctx):
    """
    Función principal que maneja tanto WebSocket (voz) como Request (SMS).
    Compatible con tu main.py existente.
    """
    if isinstance(ctx, WebSocket):
        logger.info("🗣️ Llamada de voz Twilio entrante")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 Mensaje SMS/WhatsApp entrante")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")