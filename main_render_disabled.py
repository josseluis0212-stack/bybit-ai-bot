#!/usr/bin/env python3
"""
BOT SUSPENDIDO - Migrado a Hugging Face Spaces
Este proceso está desactivado intencionalmente.
"""
import time
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.warning("="*60)
logger.warning("BOT DESACTIVADO EN RENDER")
logger.warning("Sistema migrado a: Hugging Face Spaces")
logger.warning("URL activa: https://luisalbertor-bybit-bot-v5.hf.space")
logger.warning("="*60)

# Mantener el proceso vivo para que Render no intente reiniciarlo
while True:
    logger.info("STANDBY - Bot desactivado en este servidor. Ver HF Spaces.")
    time.sleep(3600)
