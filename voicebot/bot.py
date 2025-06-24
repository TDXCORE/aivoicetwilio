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
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from openai._types import NOT_GIVEN
from pipecat.frames.frames import TextFrame

# Cargar variables de entorno
load_dotenv(override=True)

# ──────────────────────────────────────────
# 1) PIPELINE PARA LLAMADAS DE VOZ (WebSocket)
# ──────────────────────────────────────────
async def _voice_call(ws: WebSocket):
    """Maneja la conexión Media Streams de Twilio - Groq Whisper + Groq LLM + ElevenLabs."""
    logger.info("🎯 Iniciando pipeline de voz Groq Whisper + Groq LLM + ElevenLabs...")
    
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

        # ───── VAD CONFIGURADO PARA MAYOR SENSIBILIDAD ─────
        vad_analyzer = SileroVADAnalyzer(
            sample_rate=8000,
            params=VADParams(
                confidence=0.5,      # Más sensible para captar más audio
                start_secs=0.1,      # Respuesta más rápida
                stop_secs=0.5,       # Tiempo moderado antes de parar
                min_volume=0.3       # Volumen mínimo más bajo para captar audio débil
            )
        )
        logger.info("✅ Silero VAD creado con parámetros optimizados")

        # ───── TRANSPORT CON CONFIGURACIÓN OPTIMIZADA PARA AUDIO ─────
        transport = FastAPIWebsocketTransport(
            websocket=ws,
            params=FastAPIWebsocketParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
                add_wav_header=False,
                vad_analyzer=vad_analyzer,
                serializer=serializer,
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                audio_in_channels=1,    # Mono channel explícito
                audio_out_channels=1,   # Mono channel explícito
                audio_out_enabled_timeout=30.0,  # Timeout más largo para audio
            ),
        )
        logger.info("✅ Transport creado")

        # ───── GROQ WHISPER STT ─────
        stt = GroqSTTService(
            api_key=os.getenv("GROQ_API_KEY"),
            model="whisper-large-v3",
            language="es",
            temperature=0,  # Máxima precisión
        )
        logger.info("✅ Groq Whisper STT creado")
        
        # ───── GROQ LLM ─────
        llm = GroqLLMService(
            api_key=os.getenv("GROQ_API_KEY"), 
            model="llama-3.3-70b-versatile"
        )
        logger.info("✅ Groq LLM creado")
        
        # ───── ELEVENLABS TTS OPTIMIZADO ─────
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY")
        if not elevenlabs_api_key:
            logger.error("❌ ELEVENLABS_API_KEY no configurada")
            raise ValueError("ELEVENLABS_API_KEY requerida")
            
        tts = ElevenLabsTTSService(
            api_key=elevenlabs_api_key,
            voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel (multiidioma, incluye español)
            model="eleven_flash_v2_5",  # Ultra-fast model optimized for real-time
            language="es",  # Español
            stability=0.4,  # Menor estabilidad para mayor velocidad
            similarity_boost=0.7,  # Reducido para mayor velocidad
            style=0.0,  # Sin estilo adicional
            use_speaker_boost=False,  # Desactivado para mayor velocidad
            output_format="pcm_16000",  # Formato optimizado para Twilio
            optimize_streaming_latency=4,  # Máxima optimización de latencia
        )
        logger.info("✅ ElevenLabs TTS creado (optimizado para baja latencia)")

        # ───── CONTEXTO LLM CORREGIDO ─────
        messages = [
            {
                "role": "system",
                "content": """Eres Freddy, SDR (Sales Development Representative) de TDX, empresa colombiana de soluciones de IA conversacional y automatización.

PERSONALIDAD Y TONO:
- Formal-amigable, colombiano profesional
- Sin muletillas coloquiales excesivas ni groserías
- Ritmo natural y pausado
- Escucha activa: refleja las ideas del prospecto
- Máximo 2 oraciones por respuesta para mantener fluidez
- Tono relajado y con mucha confianza

OBJETIVO DE LA LLAMADA:
1) Descubrir dolores críticos del líder de tecnología
2) Mapearlos a las soluciones de TDX  
3) Concretar reunión de exploración (20-30 min)

GUION A SEGUIR:

APERTURA (usar SOLO después de que el prospecto hable primero):
"Buen día, le habla Freddy, de TDX. ¿Cómo está? Lo estoy contactando porque estamos ayudando a líderes de tecnología a reducir en un treinta por ciento el tiempo que sus equipos dedican a tareas repetitivas y a acelerar la salida de prototipos. ¿Es un tema que está en su radar en este momento?"

DESCUBRIMIENTO (usar estas preguntas según el flujo):
- "Entendiendo ese desafío de las tareas repetitivas, ¿en qué procesos específicos su equipo de TI experimenta hoy más cuellos de botella por tickets o llamadas que les quitan foco?"
- "Pensando en la agilidad, cuando necesitan lanzar un prototipo o MVP, ¿cuánto tiempo les toma hoy realmente sacarlo a producción y llevarlo al usuario final?"
- "Hablando de eficiencia, ¿sus sistemas como CRM/ERP y canales como WhatsApp o voz conversan de forma fluida, o su equipo debe hacer muchos amarres manuales para que funcionen juntos?"

SOLUCIONES TDX (mapear directamente al dolor identificado):
- Para cuellos de botella en soporte: "Justamente para liberar esa carga, TDX implementa AI Chatbot Multiagente o AI Voice Assistant; estas soluciones toman el ochenta por ciento de las interacciones repetitivas."
- Para tareas repetitivas: "Para quitarse de encima esas labores que consumen tiempo valioso, utilizamos Flujos de Automatización y nuestro AgentOps Framework, optimizando procesos end-to-end."
- Para la velocidad de lanzamiento de MVPs: "Si el desafío es la agilidad, con MVP en quince días y nuestra oferta de SaaS Agentic, podemos acelerar significativamente la puesta en marcha de sus innovaciones."
- Para amarres manuales y sistemas desintegrados: "Si la fricción está en la integración, nuestra Integración con CRM/ERP y el AI Assistant para WhatsApp permiten una conectividad perfecta y eliminan esos procesos manuales."

CIERRE:
"Dado que identificamos [mencionar el dolor principal del prospecto], propongo una sesión de descubrimiento de veinticinco minutos. Allí podemos revisar a detalle sus flujos y le mostraré un caso real de TDX, similar al suyo, donde logramos resultados tangibles. ¿Le iría bien este jueves a las diez a.m. o prefiere el viernes a primera hora?"

MANEJO DE SITUACIONES:
- Si el usuario dice "No" a las preguntas iniciales, hacer preguntas exploratorias alternativas
- Si no entiendo una transcripción, preguntar cortésmente: "No logré escucharlo bien, ¿podría repetir por favor?"
- Si hay silencio prolongado, hacer una pregunta abierta para reactivar la conversación
- Nunca quedarse completamente callado, siempre mantener la conversación activa

INSTRUCCIONES CRÍTICAS:
- ESPERAR siempre a que el usuario hable primero antes de usar la apertura
- NO generar respuestas automáticas al conectarse
- Responder SOLO cuando recibas input real del usuario
- Seguir el guion paso a paso después de que el cliente hable
- Escuchar 70%, hablar 30%
- Siempre buscar agendar la reunión
- Usar vocabulario formal-colombiano: "cuello de botella", "amarres", "quitarse de encima"
- Respuestas máximo 2 oraciones para mantener fluidez
- No incluir caracteres especiales en las respuestas ya que se convertirán a audio
- Ser adaptable y conversacional, mantener el flujo natural"""
            }
        ]
        
        # ───── CONTEXTO SIN MENSAJE INICIAL ─────
        context = OpenAILLMContext(messages)
        context_aggregator = llm.create_context_aggregator(context)
        logger.info("✅ Contexto de ventas B2B creado")

        # ───── PIPELINE ─────
        pipeline = Pipeline([
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ])
        logger.info("✅ Pipeline creado")

        # ───── TASK ─────
        task = PipelineTask(
            pipeline,
            params=PipelineParams(
                audio_in_sample_rate=8000,
                audio_out_sample_rate=8000,
                allow_interruptions=True,
                enable_metrics=True,
                enable_usage_metrics=True,
            ),
        )
        
        # ───── EVENTOS DE TRANSPORTE CON DEBUGGING ─────        
        @transport.event_handler("on_client_connected")
        async def on_client_connected(transport, client):
            logger.info(f"🔗 Cliente conectado: {client}")

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info(f"👋 Cliente desconectado: {client}")
            await task.cancel()

        # ───── EVENTOS PARA DEBUGGING DE AUDIO ─────
        @transport.event_handler("on_audio_stream_started")
        async def on_audio_stream_started(transport):
            logger.info("🎵 Audio stream iniciado")

        @transport.event_handler("on_audio_stream_stopped") 
        async def on_audio_stream_stopped(transport):
            logger.info("🔇 Audio stream detenido")

        # ───── EVENTOS DE TTS PARA DEBUGGING ─────
        @tts.event_handler("on_tts_started")
        async def on_tts_started(tts, text):
            logger.info(f"🔊 TTS iniciado: '{text[:50]}...'")

        @tts.event_handler("on_tts_stopped")
        async def on_tts_stopped(tts):
            logger.info("🔇 TTS finalizado")

        # ───── EJECUTAR RUNNER ─────
        logger.info("🚀 Iniciando pipeline de ventas B2B con Groq Whisper + ElevenLabs...")
        runner = PipelineRunner(handle_sigint=False)
        await runner.run(task)
        logger.info("📞 Llamada de ventas finalizada")
        
    except Exception as e:
        logger.exception(f"💥 Error en pipeline de ventas: {e}")
        raise


# ──────────────────────────────────────────
# 2) PIPELINE SMS / WHATSAPP (webhook HTTP)
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
                "content": "Eres Freddy, SDR de TDX. Responde de forma concisa y profesional en español. Enfócate en agendar una reunión para mostrar nuestras soluciones de IA conversacional."
            },
            {
                "role": "user",
                "content": user_msg
            }
        ])
        
        # Generar respuesta
        response = await llm._process_context(context)
        reply = response.choices[0].message.content
        
        logger.info(f"🤖 Respuesta SMS: '{reply}'")

        # TwiML para responder
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
        return Response(content=twiml, media_type="text/xml")
        
    except Exception as e:
        logger.exception(f"💥 Error en SMS: {e}")
        error_twiml = '<?xml version="1.0" encoding="UTF-8"?><Response><Message>Error procesando mensaje</Message></Response>'
        return Response(content=error_twiml, media_type="text/xml")


# ──────────────────────────────────────────
# 3) HEALTH CHECK
# ──────────────────────────────────────────
async def health_check():
    """Health check endpoint."""
    logger.info("🏥 Health check Pipeline de Ventas B2B")
    return {
        "status": "healthy", 
        "service": "TDX Sales Bot - Groq Whisper + Groq LLM + ElevenLabs",
        "version": "2025-06-24-ELEVENLABS-FLASH",
        "apis": {
            "groq": bool(os.getenv("GROQ_API_KEY")),
            "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        },
        "services": {
            "stt": "Groq Whisper Large V3",
            "llm": "Groq Llama 3.3 70B", 
            "tts": "ElevenLabs Flash V2.5",
            "purpose": "Sales Development Representative (SDR)"
        }
    }


# ──────────────────────────────────────────
# 4) PUNTO ÚNICO DE ENTRADA
# ──────────────────────────────────────────
async def bot(ctx):
    """
    Función principal para Sales Bot B2B.
    Compatible con tu main.py existente.
    """
    if isinstance(ctx, WebSocket):
        logger.info("📞 Llamada de ventas → Freddy SDR de TDX")
        await _voice_call(ctx)
    elif isinstance(ctx, Request):
        logger.info("💬 Mensaje SMS/WhatsApp → Freddy SDR")
        return await _sms(ctx)
    else:
        logger.error(f"❌ Tipo no soportado: {type(ctx)}")
        raise TypeError("bot() sólo acepta WebSocket o Request de FastAPI")