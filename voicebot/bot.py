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
from pipecat.services.groq.llm import GroqLLMService
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
    """Maneja la conexión Media Streams de Twilio - Deepgram + Groq + Cartesia."""
    logger.info("🎯 Iniciando pipeline de voz Deepgram + Groq + Cartesia...")
    
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

        # ───── SERVICIOS DEEPGRAM + GROQ + CARTESIA ─────
        # Deepgram STT
        stt = DeepgramSTTService(
            api_key=os.getenv("DEEPGRAM_API_KEY"),
            model="nova-2-phonecall",
            language="es-419",
            filler_words=True,
            profanity_filter=True,
            smart_format=True,
            punctuate=True,
            numerals=True,
            sample_rate=SAMPLE_RATE
        )
        logger.info("✅ Deepgram STT creado")
        
        # Groq Llama 70B LLM
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"), 
            model="llama-3.3-70b-versatile"
        )
        logger.info("✅ Groq Llama 70B LLM creado")
        
        # Cartesia TTS (optimizado para Pipecat)
        cartesia_api_key = os.getenv("CARTESIA_API_KEY")
        if not cartesia_api_key:
            logger.error("❌ CARTESIA_API_KEY no configurada")
            raise ValueError("CARTESIA_API_KEY requerida")
            
        logger.info("🎵 Configurando Cartesia TTS...")
        
        # Usar una voz en español o compatible
        tts = CartesiaTTSService(
            api_key=cartesia_api_key,
            voice_id="308c82e1-ecef-48fc-b9f2-2b5298629789",
            output_format="ulaw_8000",   # ← formato 8 kHz μ-law
            sample_rate=8000,            # ← asegura la frecuencia correcta
            stream_mode="chunked",
            chunk_ms=20, 
            # Sin parámetros adicionales - usar defaults de Pipecat
        )
        logger.info("✅ Cartesia TTS creado (optimizado para Pipecat)")

        # ───── CONTEXTO LLM ─────
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres Lorenzo, un asistente de voz amigable de TDX. "
                    "Responde en español de forma natural y breve. "
                    "Máximo 2 oraciones por respuesta. "
                    "Tu salida será convertida a audio, así que no incluyas caracteres especiales. "
                    "Siempre confirma que escuchaste al usuario."
                )
            }
        ]
        context = OpenAILLMContext(messages, NOT_GIVEN)
        ctx_aggr = llm.create_context_aggregator(context)
        logger.info("✅ Groq context creado")

        # ───── VAD SIMPLE ─────
        vad = SileroVADAnalyzer(sample_rate=SAMPLE_RATE)
        logger.info("✅ Silero VAD creado")

        # ───── TRANSPORT SIMPLE (como en el ejemplo de Pipecat) ─────
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=vad,
                serializer=serializer,
                audio_out_sample_rate=8000,
                # Sin especificar sample rates - usar defaults
            ),
        )
        logger.info("✅ Transport creado")

        # ───── PIPELINE DEEPGRAM + GROQ + CARTESIA (simple y efectivo) ─────
        pipeline = Pipeline([
            transport.input(),      # WebSocket Twilio
            stt,                   # Deepgram STT
            ctx_aggr.user(),       # Contexto usuario
            llm,                   # Groq Llama 70B
            tts,                   # Cartesia TTS
            transport.output(),    # De vuelta a Twilio
            ctx_aggr.assistant(),  # Contexto asistente
        ])
        logger.info("✅ Pipeline Deepgram + Groq + Cartesia creado")

        # ───── TASK CON PARÁMETROS SIMPLES ─────
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                allow_interruptions=True,
                audio_in_sample_rate=8000,    # Twilio standard
                audio_out_sample_rate=8000,   # Twilio standard
                enable_metrics=True,
            ),
        )
        
        # ───── EVENTOS DE TRANSPORTE ─────
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info(f"🔗 Cliente conectado: {client}")
            # Iniciar conversación con saludo
            await task.queue_frames([ctx_aggr.user().get_context_frame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info(f"👋 Cliente desconectado: {client}")
            await task.cancel()
        
        # ───── SALUDO AUTOMÁTICO ─────
        async def send_greeting():
            await asyncio.sleep(2)  # Esperar conexión estable
            logger.info("👋 Enviando saludo...")
            greeting = TextFrame("¡Hola! Soy Lorenzo de TDX. Ahora uso Deepgram y Cartesia para una experiencia de audio mejorada. ¿En qué puedo ayudarte?")
            await task.queue_frame(greeting)
            logger.info("✅ Saludo enviado")

        asyncio.create_task(send_greeting())

        # ───── EJECUTAR PIPELINE ─────
        logger.info("🚀 Iniciando pipeline Deepgram + Groq + Cartesia...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        logger.info("📞 Llamada Deepgram + Groq + Cartesia finalizada")
        
    except Exception as e:
        logger.exception(f"💥 Error en pipeline Deepgram + Groq + Cartesia: {e}")
        raise


# ──────────────────────────────────────────
# 2) PIPELINE SMS / WHATSAPP (webhook HTTP) - SIN CAMBIOS
# ──────────────────────────────────────────
async def _sms(request: Request) -> Response:
    """Maneja mensajes SMS/WhatsApp de Twilio - Groq LLM."""
    try:
        form = await request.form()
        user_msg = form.get("Body", "") or "..."
        from_number = form.get("From", "")
        
        logger.info(f"💬 SMS de {from_number}: '{user_msg}'")

        # Usar Groq Llama para respuesta de texto
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="llama-3.3-70b-versatile"
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
        
        logger.info(f"🤖 Respuesta SMS Groq: '{reply}'")

        # TwiML para responder
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.exception(f"💥 Error en SMS Groq: {e}")
        # Respuesta de error en TwiML
        error_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error procesando mensaje</Message></Response>'
        return Response(content=error_twiml, media_type="text/xml")


# ──────────────────────────────────────────
# 3) HEALTH CHECK
# ──────────────────────────────────────────
async def health_check():
    """Health check endpoint."""
    logger.info("🏥 Health check Deepgram + Groq + Cartesia")
    return {
        "status": "healthy", 
        "service": "TDX Voice Bot - Deepgram + Groq + Cartesia",
        "version": "2025-06-24-DEEPGRAM-GROQ-CARTESIA",
        "apis": {
            "deepgram": bool(os.getenv("DEEPGRAM_API_KEY")),
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "cartesia": bool(os.getenv("CARTESIA_API_KEY")),
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        },
        "services": {
            "stt": "Deepgram Nova-2",
            "llm": "Groq Llama 3.3 70B", 
            "tts": "Cartesia (Spanish voice)"
        }
    }


# ──────────────────────────────────────────
# 4) PUNTO ÚNICO DE ENTRADA
# ──────────────────────────────────────────
async def bot(ctx):
    """
    Función principal Deepgram + Groq + Cartesia.
    Compatible con tu main.py existente.
    """
    if isinstance(ctx, WebSocket):
        logger.info("🗣️ Llamada de voz Twilio → Deepgram + Groq + Cartesia Stack")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 Mensaje SMS/WhatsApp → Groq")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")