// LRMC PRO Elite Terminal Logic — v2.4

const API_BASE = '/api';

// ── Formatters ────────────────────────────────────────────────
function formatCurrency(num, prefix = '$', fixed = 2) {
    if (num === null || num === undefined) return '--';
    const sign = num < 0 ? '-' : (num > 0 ? '+' : '');
    return `${sign}${prefix}${Math.abs(num).toFixed(fixed)}`;
}

function formatCrypto(num) {
    if (num === null || num === undefined) return '--';
    return Number(num).toFixed(4);
}

function formatPrice(p) {
    if (p === null || p === undefined) return '--';
    const v = parseFloat(p);
    return v < 0.01 ? v.toFixed(6) : v.toFixed(4);
}

// ── Dashboard (balance + positions + config) ──────────────────
function updateDashboard(data) {
    // Bot Status Indicator
    const statusEl = document.getElementById('scanner-status');
    if (statusEl) {
        if (data.running) {
            statusEl.innerHTML = `ESCANER ACTIVO <span class="dot" style="background-color: #22c55e; box-shadow: 0 0 8px #22c55e;"></span>`;
            statusEl.style.color = '#22c55e';
            statusEl.style.backgroundColor = 'rgba(34, 197, 94, 0.1)';
            statusEl.style.borderColor = 'rgba(34, 197, 94, 0.3)';
        } else {
            statusEl.innerHTML = `ESCANER DETENIDO <span class="dot" style="background-color: #ef4444; box-shadow: 0 0 8px #ef4444; animation: none;"></span>`;
            statusEl.style.color = '#ef4444';
            statusEl.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
            statusEl.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        }
    }

    // Balances
    if (data.balance !== null && data.balance !== undefined) {
        document.getElementById('balance-vst').innerText   = `${parseFloat(data.balance).toFixed(2)} USDT`;
        document.getElementById('balance-equity').innerText = `${parseFloat(data.balance).toFixed(2)} Equity`;
    }

    // Config params
    if (data.config) {
        document.getElementById('param-leverage').innerText  = `${data.config.leverage}X`;
        document.getElementById('param-maxtrades').innerText = data.config.max_trades;
        const risk = data.config.risk_per_trade;
        if (risk !== undefined && risk !== null) {
            document.getElementById('param-risk').innerText = `$${parseFloat(risk).toFixed(2)} USDT`;
        }
    }

    // Active Positions Table
    const tbody    = document.getElementById('positions-body');
    const positions = data.positions || [];
    document.getElementById('active-count-val').innerText = positions.length;

    if (positions.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center" style="color:#64748b; padding:2rem;">NO HAY POSICIONES ACTIVAS EN BYBIT</td></tr>';
        document.getElementById('global-pnl').innerText = '$0.00';
        document.getElementById('global-pnl').className = '';
    } else {
        let rows = '';
        let globalPnl = 0;

        positions.forEach(p => {
            const sideClass  = p.positionSide === 'LONG' ? 'text-green' : 'text-red';
            const entry      = formatPrice(p.avgPrice);
            const unrealized = parseFloat(p.unrealizedProfit || 0);
            globalPnl += unrealized;

            const pnlClass = unrealized >= 0 ? 'text-green' : 'text-red';
            const pnlStr   = formatCurrency(unrealized, '$', 4);

            // ── BADGE PROGRESSION (30/30/40) ──────────────────────────────
            // Siempre visible: ✦ ENTRADA (con SL)
            const slBadgePrice = p.sl_price ? ` · SL ${formatPrice(p.sl_price)}` : '';
            let badges = `<span class="tag" style="background:rgba(34,197,94,0.1);color:#22c55e;border:1px solid rgba(34,197,94,0.3);margin-right:4px;font-weight:700;">✦ ENTRADA${slBadgePrice}</span>`;

            // Fase 2 — TP1 tocado
            if (p.tp1_hit) {
                badges += '<span class="tag" style="background:rgba(16,185,129,0.2);color:#10b981;border:1px solid #10b981;margin-right:4px;font-weight:700;">🎯 TP1 (30%)</span>';
            }

            // Fase 3 — BREAKEVEN activado (profit_lock_active = 40% avanzado hacia TP2)
            if (p.profit_lock_active || p.breakeven_hit) {
                badges += '<span class="tag" style="background:rgba(168,85,247,0.15);color:#c084fc;border:1px solid rgba(168,85,247,0.5);margin-right:4px;font-weight:700;box-shadow:0 0 6px rgba(168,85,247,0.25);">🛡️ BREAKEVEN</span>';
            }

            // Fase 4a — TP2 tocado
            if (p.tp2_hit) {
                badges += '<span class="tag" style="background:rgba(16,185,129,0.2);color:#10b981;border:1px solid #10b981;margin-right:4px;font-weight:700;">🎯 TP2 (60%)</span>';
            }

            // Fase 4b — TRAILING activo (último badge, con brillo animado)
            if (p.trailing_active) {
                badges += '<span class="tag tag-trail-glow" style="margin-right:4px;font-weight:700;">🔁 TRAILING RUN (40%)</span>';
            }

            // Estado pendiente: qué busca ahora
            if (!p.tp1_hit) {
                badges += '<span class="tag" style="background:rgba(255,255,255,0.04);color:#6b7280;border:1px solid rgba(255,255,255,0.08);margin-right:4px;font-style:italic;">Buscando TP1...</span>';
            } else if (!p.tp2_hit) {
                badges += '<span class="tag" style="background:rgba(255,255,255,0.04);color:#6b7280;border:1px solid rgba(255,255,255,0.08);margin-right:4px;font-style:italic;">Buscando TP2...</span>';
            }

            // Niveles SL/TP en línea secundaria
            const slStr = p.sl_price  ? `SL <b>${formatPrice(p.sl_price)}</b>` : '';
            const tp1Str = p.tp1_price ? `TP1 <b>${formatPrice(p.tp1_price)}</b>` : '';
            const tp2Str = p.tp2_price ? `TP2 <b>${formatPrice(p.tp2_price)}</b>` : '';
            const levels = [slStr, tp1Str, tp2Str].filter(Boolean).join(' · ');

            const strategyName = p.strategy || 'N/A';
            const strategyBadge = strategyName === 'QUANTUM V13 PRO' || strategyName === 'AntigravityV13'
                ? '<span class="badge" style="background: linear-gradient(90deg, #3b82f6, #8b5cf6);">Quantum V13 PRO</span>'
                : strategyName === 'QUANTUM V13 PRO (Adoptado)' || strategyName === 'AntigravityV13_Adopted'
                ? '<span class="badge" style="background: linear-gradient(90deg, #ef4444, #f59e0b);">Quantum V13 (Adoptado)</span>'
                : strategyName.includes('SUPERTREND')
                ? '<span class="badge" style="background: linear-gradient(90deg, #10b981, #059669);">SuperTrend MTF</span>'
                : `<span class="badge">${strategyName}</span>`;

            rows += `
                <tr>
                    <td><span style="font-weight:800">${p.symbol}</span></td>
                    <td>${strategyBadge}</td>
                    <td><span class="${sideClass}" style="font-weight:700">${p.positionSide}</span></td>
                    <td><span style="font-family:monospace">${entry}</span></td>
                    <td>
                        <div class="state-badges">${badges}</div>
                        ${levels ? `<div style="font-size:0.6rem;color:#64748b;margin-top:0.2rem">${levels}</div>` : ''}
                    </td>
                    <td><span class="${pnlClass}" style="font-family:monospace; font-weight:800">${pnlStr}</span></td>
                    <td><button class="btn-live">MONITOR</button></td>
                </tr>
            `;
        });
        tbody.innerHTML = rows;

        // Global live PnL
        const gpEl = document.getElementById('global-pnl');
        gpEl.innerText = formatCurrency(globalPnl);
        gpEl.className = globalPnl >= 0 ? 'text-green' : 'text-red';
    }
}

// ── Stats + History ───────────────────────────────────────────
// ── Stats + Master History Table ──────────────────────────────
async function fetchMasterHistory() {
    try {
        const res = await fetch(`${API_BASE}/trade_history?limit=50`);
        if (!res.ok) return;
        const data = await res.json();
        const histList = document.getElementById('history-list');
        const trades = data.operaciones || [];

        if (trades.length === 0) {
            histList.innerHTML = '<tr><td colspan="10" style="text-align: center; color: #64748b; padding: 2rem;">No hay operaciones registradas en el disco de memoria.</td></tr>';
            return;
        }

        let hHTML = '';
        trades.forEach(t => {
            const estado = t.estado_final || t.estado || 'CERRADA';
            const isWin  = estado === 'GANADA' || (t.pnl_realizado || 0) > 0;
            const isLoss = estado === 'PERDIDA' || (t.pnl_realizado || 0) < 0;
            
            const colorMain = isWin ? '#22c55e' : (isLoss ? '#ef4444' : '#eab308');
            const bgHover   = isWin ? 'rgba(34,197,94,0.05)' : 'rgba(239,68,68,0.05)';

            // Formatear fechas
            const fApertura = t.apertura ? t.apertura.replace('T', ' ').substring(0, 19) : '--';
            const fCierre   = t.cierre   ? t.cierre.replace('T', ' ').substring(0, 19) : (t.fecha_cierre || '--');

            // Moneda y dirección
            const sideStr = t.side || (t.signal || 'LONG');
            const sideClass = sideStr === 'LONG' ? 'text-green' : 'text-red';

            // Estrategia
            const strat = t.strategy || t.estrategia || 'QUANTUM V13';

            // Precios y volúmenes
            const pEntrada = formatPrice(t.precio_entrada || t.entry_price);
            const volumenUsdt = t.margen_usdt ? `$${(t.margen_usdt * (t.apalancamiento || 10)).toFixed(2)} USDT` : '$150.00 USDT';
            const tokens = t.tamanio_posicion ? formatCrypto(t.tamanio_posicion) : (t.qty ? formatCrypto(t.qty) : '--');

            // Distancias SL / TP
            const slStr  = t.stop_loss ? `SL: <b>${formatPrice(t.stop_loss)}</b>` : 'SL: --';
            const tp1Str = t.take_profit_1 ? `TP1: <b>${formatPrice(t.take_profit_1)}</b>` : '';
            const tp2Str = t.take_profit_2 ? `TP2: <b>${formatPrice(t.take_profit_2)}</b>` : '';
            const levels = [slStr, tp1Str, tp2Str].filter(Boolean).join('<br>');

            // BE & Trailing Flags
            let beBadge = t.breakeven_activado || (t.extra && t.extra.breakeven_activado)
                ? '<span style="background:rgba(168,85,247,0.2);color:#c084fc;border:1px solid rgba(168,85,247,0.4);padding:2px 6px;border-radius:4px;font-size:0.7rem;font-weight:700;">🛡️ BREAKEVEN</span>'
                : '<span style="color:#64748b;font-size:0.7rem;">Inactivo</span>';

            let trailBadge = t.trailing_activado || (t.extra && t.extra.trailing_activado)
                ? '<span style="background:rgba(59,130,246,0.2);color:#60a5fa;border:1px solid rgba(59,130,246,0.4);padding:2px 6px;border-radius:4px;font-size:0.7rem;font-weight:700;margin-left:4px;">🔁 TRAILING</span>'
                : '';

            const pnlVal = t.pnl_realizado !== undefined ? t.pnl_realizado : (t.pnl || 0);
            const pnlStr = formatCurrency(pnlVal, '$', 4);

            hHTML += `
                <tr style="border-left: 4px solid ${colorMain}; background: rgba(255,255,255,0.01); transition: all 0.2s;" onmouseover="this.style.background='${bgHover}'" onmouseout="this.style.background='rgba(255,255,255,0.01)'">
                    <td style="padding: 0.8rem; font-family: monospace; color:#94a3b8;">${fApertura}</td>
                    <td style="padding: 0.8rem;"><span style="font-weight:800; font-size:0.9rem;">${t.symbol}</span> <span class="${sideClass}" style="font-size:0.75rem; font-weight:700; margin-left:4px;">${sideStr}</span></td>
                    <td style="padding: 0.8rem;"><span style="color:#c084fc; font-weight:700;">${strat}</span></td>
                    <td style="padding: 0.8rem; font-family: monospace;"><b>${pEntrada}</b></td>
                    <td style="padding: 0.8rem; color:#e2e8f0; font-weight:600;">${volumenUsdt}</td>
                    <td style="padding: 0.8rem; font-family: monospace; color:#cbd5e1;">${tokens}</td>
                    <td style="padding: 0.8rem; font-size:0.75rem; color:#94a3b8; line-height:1.3;">${levels}</td>
                    <td style="padding: 0.8rem;">${beBadge} ${trailBadge}</td>
                    <td style="padding: 0.8rem; font-family: monospace; color:#94a3b8;">${fCierre}</td>
                    <td style="padding: 0.8rem; text-align:right;">
                        <div style="font-weight:900; font-size:0.85rem; color:${colorMain};">${estado}</div>
                        <div style="font-family:monospace; font-weight:800; font-size:1.05rem; color:${colorMain};">${pnlStr}</div>
                    </td>
                </tr>
            `;
        });
        histList.innerHTML = hHTML;
    } catch (e) { console.error('Error fetching master history', e); }
}

async function fetchDiskStatus() {
    try {
        const res = await fetch(`${API_BASE}/disk_status`);
        if (!res.ok) return;
        const data = await res.json();
        const badgeText = document.getElementById('disk-status-text');
        if (badgeText && data.disk) {
            if (data.disk.connected) {
                badgeText.innerHTML = `🟢 FTP RED NAS (${data.disk.ftp_host})`;
                badgeText.style.color = '#22c55e';
            } else {
                badgeText.innerHTML = `🟡 LOCAL FAILSAFE (${data.disk.local_base})`;
                badgeText.style.color = '#eab308';
            }
        }
    } catch (e) {}
}

function updateStats(stats) {
    if (!stats) return;

    const updatePnl = (id, val) => {
        const el = document.getElementById(id);
        if (el) {
            el.innerText  = formatCurrency(val);
            el.className  = `pnl-amount ${val >= 0 ? 'text-green' : 'text-red'}`;
        }
    };

    updatePnl('pnl-today', stats.pnl_today);

    if (document.getElementById('win-today')) document.getElementById('win-today').innerText    = stats.win_today;
    if (document.getElementById('loss-today')) document.getElementById('loss-today').innerText   = stats.loss_today;

    if (document.getElementById('winrate-pct')) document.getElementById('winrate-pct').innerText          = `${stats.win_rate.toFixed(1)}%`;
    if (document.getElementById('winrate-bar')) document.getElementById('winrate-bar').style.width        = `${Math.min(stats.win_rate, 100)}%`;
    if (document.getElementById('profit-factor')) document.getElementById('profit-factor').innerText        = stats.profit_factor.toFixed(2);
    if (document.getElementById('mean-win')) document.getElementById('mean-win').innerText             = formatCurrency(stats.mean_win);
    if (document.getElementById('mean-loss')) document.getElementById('mean-loss').innerText            = formatCurrency(stats.mean_loss);
}


// ── Terminal de Ejecución ─────────────────────────────────────
function updateLogs(logs) {
    if (!logs || !logs.length) return;
    const consoleEl = document.getElementById('terminal-console');

    let logHTML = '';
    logs.forEach(line => {
        let cssClass = 'log-line';

        // Colour rules — ordered by priority (most specific first)
        if (line.includes('[BTC BLOCK]') || line.includes('VOLATILITY'))   cssClass += ' error';
        else if (line.includes('[BREAKEVEN]') || line.includes('breakeven')) cssClass += ' be-event';
        else if (line.includes('[TRAILING]') || line.includes('trailing'))   cssClass += ' be-event';
        else if (line.includes('[OPEN]') || line.includes('[CLOSE')
              || line.includes('[TRADE]') || line.includes('FILLED'))        cssClass += ' trade-event';
        else if (line.includes('[ERROR]') || line.includes('[WARNING]')
              || line.includes('Error') || line.includes('error'))           cssClass += ' error';
        else if (line.includes('OK') || line.includes('uccess'))             cssClass += ' success';
        else if (line.includes('[INFO]'))                                    cssClass += ' system';

        // Extract timestamp HH:MM:SS
        let ts = '';
        const match = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
        if (match) {
            ts   = `<span class="ts">[${match[1].split(' ')[1]}]</span>`;
            line = line.replace(match[1], '').replace(/^[\s,-]+/, '');
        }

        // Escape HTML
        line = line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

        logHTML += `<div class="${cssClass}">${ts}${line}</div>`;
    });

    consoleEl.innerHTML = logHTML;
    consoleEl.scrollTop = consoleEl.scrollHeight;
}

// ── API Fetchers ──────────────────────────────────────────────
async function fetchDashboard() {
    try {
        const res = await fetch(`${API_BASE}/dashboard`);
        if (res.ok) updateDashboard(await res.json());
    } catch (e) { console.error('Dashboard fetch error', e); }
}

async function fetchStats() {
    try {
        const res = await fetch(`${API_BASE}/stats`);
        if (res.ok) updateStats(await res.json());
    } catch (e) { console.error('Stats fetch error', e); }
}

async function fetchLogs() {
    try {
        const res = await fetch(`${API_BASE}/logs`);
        if (res.ok) {
            const data = await res.json();
            updateLogs(data.logs);
        }
    } catch (e) { console.error('Logs fetch error', e); }
}

// ── Startup ───────────────────────────────────────────────────
fetchDashboard();
fetchStats();
fetchLogs();
fetchMasterHistory();
fetchDiskStatus();

setInterval(fetchDashboard,      8000);   //  8s  — posiciones + riesgo
setInterval(fetchMasterHistory, 10000);   // 10s  — registro maestro de operaciones
setInterval(fetchDiskStatus,    15000);   // 15s  — estado del almacenamiento
setInterval(fetchStats,         45000);  // 45s  — estadísticas (pesado)
setInterval(fetchLogs,           4000);  //  4s  — terminal en tiempo casi real

// ── Button Listeners ──────────────────────────────────────────
document.getElementById('btn-correr').addEventListener('click', async () => {
    try {
        const res = await fetch(`${API_BASE}/bot/start`, {method: 'POST'});
        if (res.ok) alert('✅ Bot de Trading INICIADO.');
    } catch(e) { alert('Error de conexión.'); }
});

document.getElementById('btn-detener').addEventListener('click', async () => {
    try {
        const res = await fetch(`${API_BASE}/bot/stop`, {method: 'POST'});
        if (res.ok) alert('🛑 Bot de Trading DETENIDO.');
    } catch(e) { alert('Error de conexión.'); }
});

document.getElementById('btn-reset').addEventListener('click', async () => {
    if (!confirm('⚠️ ¿ESTÁS SEGURO?\n\nEsto CANCELARÁ todas las órdenes abiertas, CERRARÁ todas las posiciones y pondrá a CERO los contadores. Solo para emergencias.')) return;
    try {
        const res = await fetch(`${API_BASE}/bot/reset`, {method: 'POST'});
        if (res.ok) alert('✅ RESET COMPLETADO. Posiciones cerradas y contadores a cero.');
        fetchDashboard();
        fetchStats();
    } catch(e) { alert('Error de conexión.'); }
});
