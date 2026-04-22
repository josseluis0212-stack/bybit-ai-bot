# Historial de Cambios - Bybit AI Bot

## 2026-04-22

### Ajustes de Configuración
- **Monedas analizadas:** 100 (ordenadas por volumen)
- **Volumen mínimo:** 330,000 USDT
- **Máximo operaciones:** 10 simultáneas
- **Margen por trade:** $20
- **Apalancamiento:** 10x

### Archivos Modificados
- `config/settings.py` - MAX_CONCURRENT_TRADES = 10
- `strategy/market_scanner.py` - Filtro volumen mínimo 330k + top 100
- `execution_engine/executor.py` - Código de ejecución

### Documentación
- `AGENTS.md` - Creado con configuración y estructura del proyecto

---

## Notas
- Usar `git add . && git commit -m "mensaje" && git push origin main` para guardar cambios
- Para sobrescribir remoto: `git push origin main --force`
