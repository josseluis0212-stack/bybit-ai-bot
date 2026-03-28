---
name: Community Knowledge & Recipes
description: Repositorio e integrador de soluciones, patrones y "hacks" aportados por la comunidad de desarrolladores de IA, foros y GitHub (LangChain Recipes, HuggingFace, etc).
---

# Skill: Community Knowledge Integrator

La IA aprende más rápido cuando comparte y adopta los patrones probados por otros (Hive Mind). Esta skill permite buscar activamente foros, Reddit, GitHub Issues y repositorios de Discord.

## 🤝 Patrones Comunitarios Extraídos

### 1. El Patrón "Reflection" (LangGraph Community)
Un caso de uso estándar: Cuando escribo un código nuevo, la comunidad aconseja un paso intermedio donde otra "instancia mental" mía lo revise antes de aplicarlo.
- *Beneficio*: Reduce los errores de compilación y lógica al 10%.

### 2. Scraping Reactivo (GitHub Recipes)
Los ingenieros de datos recomiendan usar **BeautifulSoup + LXML** en lugar de Selenium cuando la página no tiene renderizado JS severo. Esto acelera el scraping 200x.
- **Implementación Comunitaria**: Si una API Rate-Limita, el patrón es hacer *Backoff Exponencial*.

### 3. Prompting Dinámico
- Los foros de Prompting avanzado sugieren el esquema: `[Rol] + [Contexto] + [Tarea] + [Ejemplos (Few-Shot)] + [Formato]`. Todo lo que se agregue a mis skills debe seguir este formato para claridad absoluta.

## 🌐 Aplicación al Ecosystema
Cualquier nueva lógica de trading (indicador matemático, PineScript a Python) o mejora web (Tailwind UI) que sugiera el usuario, buscaré primero el consenso de las comunidades Open Source para aplicar la respuesta más moderna y segura.
