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
        tbody.innerHTML = '<tr><td colspan="7" class="text-center" style="color:#64748b; padding:2rem;">NO HAY POSICIONES ACTIVAS EN BINGX</td></tr>';
        document.getElementById('global-pnl').innerText = '$0.00';
        document.getElementById('global-pnl').className = '';
    } else {
        let rows = '';
        let globalPnl = 0;

        positions.forEach(p => {
            const sideClass  = p.positionSide === 'LONG' ? 'green' : 'red';
            const entry      = formatPrice(p.avgPrice);
            const unrealized = parseFloat(p.unrealizedProfit || 0);
            globalPnl += unrealized;

            const pnlClass = unrealized >= 0 ? 'green' : 'red';
            const pnlStr   = formatCurrency(unrealized, '$', 4);

            // BE / Trailing badges
            let badges = '<span class="tag live">⚡ LIVE</span>';
            if (p.breakeven_hit)   badges += ' <span class="tag be">🛡️ BREAKEVEN</span>';
            if (p.trailing_active) badges += ' <span class="tag trail">🔁 TRAILING</span>';

            // SL / TP info
            const slStr = p.sl_price ? `SL ${formatPrice(p.sl_price)}` : '';
            const tpStr = p.tp_price ? `TP ${formatPrice(p.tp_price)}` : '';
            const levels = [slStr, tpStr].filter(Boolean).join(' · ');

            const strategyName = p.strategy || 'N/A';
            const strategyBadge = strategyName === 'QUANTUM_V10_PRO' 
                                  ? `<span class="badge" style="background:rgba(59,130,246,0.2);color:#3b82f6;border:1px solid #3b82f6">V10 PRO</span>`
                                  : strategyName === 'QUANTUM_DIVERGENCE'
                                  ? `<span class="badge" style="background:rgba(168,85,247,0.2);color:#a855f7;border:1px solid #a855f7">DIVERGENCE</span>`
                                  : strategyName === 'BUSTOS_PULLBACK'
                                  ? `<span class="badge" style="background:rgba(234,179,8,0.2);color:#eab308;border:1px solid #eab308">BUSTOS EMA 21</span>`
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
        gpEl.className = globalPnl >= 0 ? 'green' : 'red';
    }
}

// ── Stats + History ───────────────────────────────────────────
function updateStats(stats) {
    if (!stats) return;

    const updatePnl = (id, val) => {
        const el = document.getElementById(id);
        el.innerText  = formatCurrency(val);
        el.className  = `pnl-amount ${val >= 0 ? 'green' : 'red'}`;
    };

    updatePnl('pnl-today', stats.pnl_today);

    document.getElementById('win-today').innerText    = stats.win_today;
    document.getElementById('loss-today').innerText   = stats.loss_today;

    document.getElementById('winrate-pct').innerText          = `${stats.win_rate.toFixed(1)}%`;
    document.getElementById('winrate-bar').style.width        = `${Math.min(stats.win_rate, 100)}%`;
    document.getElementById('profit-factor').innerText        = stats.profit_factor.toFixed(2);
    document.getElementById('mean-win').innerText             = formatCurrency(stats.mean_win);
    document.getElementById('mean-loss').innerText            = formatCurrency(stats.mean_loss);

    // History List — enrich with BE/Trailing flags if present
    const histList = document.getElementById('history-list');
    if (stats.recent_trades && stats.recent_trades.length > 0) {
        let hHTML = '';
        stats.recent_trades.forEach(t => {
            const isWin    = t.pnl >= 0;
            const pnlClass = isWin ? 'green' : 'red';

            // Optional flags from closed trade record
            let flags = '';
            if (t.breakeven_hit)   flags += '<span class="tag be" style="font-size:0.55rem">🛡️ BE</span> ';
            if (t.trailing_active) flags += '<span class="tag trail" style="font-size:0.55rem">🔁 TRAIL</span>';

            // Time formatting
            let timeStr = '';
            if (t.time) {
                const d = new Date(t.time);
                timeStr = `<span style="font-size:0.6rem;color:#555">${d.toLocaleTimeString()}</span>`;
            }

            // Initials for avatar
            const initials = t.symbol.replace('USDT','').replace('-','').substring(0,2).toUpperCase();
            
            // Format strategy name
            let strategyNameText = t.strategy ? t.strategy.replace(/_/g, ' ') : 'UNKNOWN STRATEGY';
            if (strategyNameText === 'UNKNOWN STRATEGY' && t.symbol === 'BTCUSDT') strategyNameText = 'QUANTUM V10 PRO'; // Example fallback

            hHTML += `
                <div class="hist-item" style="border-left: 3px solid ${isWin ? '#22c55e' : '#ef4444'}; display: grid; grid-template-columns: 40px 1.5fr 2fr auto; gap: 1rem; align-items: center; padding: 0.8rem 1rem;">
                    
                    <!-- Avatar -->
                    <div style="width:32px; height:32px; border-radius:50%; background:rgba(255,255,255,0.05); display:flex; align-items:center; justify-content:center; font-size:0.7rem; font-weight:800; color:${isWin ? '#22c55e' : '#ef4444'}; border: 1px solid ${isWin ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}">
                        ${initials}
                    </div>

                    <!-- Symbol & Side -->
                    <div style="display:flex; flex-direction:column; gap:0.2rem;">
                        <div>
                            <span class="hist-symbol" style="font-size:0.85rem;">${t.symbol}</span>
                            <span class="hist-side" style="color:white; font-weight:bold; font-size:0.75rem;">${t.side}</span>
                        </div>
                        ${timeStr}
                    </div>

                    <!-- Strategy & Reason -->
                    <div style="display:flex; flex-direction:column; gap:0.2rem; align-items: flex-start;">
                        <span style="font-size:0.65rem; color:#60a5fa; font-weight:bold; letter-spacing:0.5px;">${strategyNameText}</span>
                        <div style="display:flex; gap:0.4rem; align-items:center;">
                            <span style="font-size:0.6rem; color:#aaa;">CAUSA: <span style="color:white; font-weight:bold;">${t.reason ? t.reason.toUpperCase() : 'CERRADO'}</span></span>
                            ${flags}
                        </div>
                    </div>

                    <!-- PNL -->
                    <div class="hist-pnl ${pnlClass}" style="text-align:right; font-size:1.0rem; font-weight:800; text-shadow: 0 0 5px ${isWin ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'};">${formatCurrency(t.pnl)}</div>
                </div>
            `;
        });
        histList.innerHTML = hHTML;
    } else {
        histList.innerHTML = '<div class="history-empty">Sin historial de trades en esta sesión.</div>';
    }
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

setInterval(fetchDashboard,  8000);   //  8s  — posiciones + riesgo
setInterval(fetchStats,      45000);  // 45s  — estadísticas (pesado)
setInterval(fetchLogs,        4000);  //  4s  — terminal en tiempo casi real

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
