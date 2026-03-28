---
name: Stealth Web Navigation & Scraping
description: Conjunto de técnicas para sortear barreras anti-bots (Cloudflare, DataDome) y navegar por la red como un humano real a gran velocidad, permitiendo lectura profunda de foros y comunidades.
---

# Skill: Stealth Navigation & Bypass

Esta skill capacita al bot (o a sus sub-agentes) para ingresar a sitios web protegidos, extraer documentación, o recopilar ideas en comunidades sin ser bloqueado.

## 🕵️‍♂️ Protocolos de Evasión (Anti-Detection)

### 1. Browser Fingerprint Masking
Un scraper estándar es detectado por su User-Agent, WebGL hash, resoluciones o fuentes CSS.
- **Acción**: Inyectar headers rotativos que simulen browsers reales (Chrome macOS, Edge Win11).
- **Herramientas (Python)**: `playwright-stealth` o `undetected-chromedriver`.

### 2. Rotación de Proxies (Residential IPs)
Si un IP hace 100 requests por minuto a Reddit o a un Exchange, será bloqueado (Rate Limit 429).
- **Solución Dinámica**: Rotar IPs residenciales por cada nuevo thread de búsqueda. No usar IPs de Data Centers (DigitalOcean/AWS son flaggeados rápido).

### 3. TLS / TCP Handshake Spoofing
Las medidas avanzadas leen a nivel de red (TLS Hello).
- **Python libraries**: `tls-client` o `curl-cffi` simulan firmas de seguridad idénticas a un browser Chromium real.

### 4. Simulación Humana Modular
- El bot debe implementar *jitter* (retrasos aleatorios de 50-300ms) al interactuar con el DOM.
- Manejar captchas y "Cloudflare Turnstile" delegando a APIs de solvers o navegando sin Headless.

## 🌐 Aplicación Práctica
Usar esta skill para leer comunidades de trading oscuro, repositorios de código sin API (Scraping directo) y canales cripto no indexados.
