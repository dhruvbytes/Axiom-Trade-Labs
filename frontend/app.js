// Backend URL (FastAPI is running on port 8000)
const API_BASE_URL = 'http://127.0.0.1:8000/api';

// --- DOM Elements ---
// HUD
const healthStatus = document.getElementById('health-status');
const errorBanner = document.getElementById('error-banner');
const portfolioValueEl = document.getElementById('portfolio-value');
const buyingPowerEl = document.getElementById('buying-power');
const streamStatusEl = document.getElementById('stream-status');
const consoleStreamStatusEl = document.getElementById('console-stream-status');
const refreshBtn = document.getElementById('refresh-btn');

// Panels
const posCountEl = document.getElementById('pos-count');
const positionsBody = document.getElementById('positions-body');
const activityFeed = document.getElementById('activity-feed');
const decisionContent = document.getElementById('panel-decision-content');
const riskContent = document.getElementById('panel-risk-content');
const corexContent = document.getElementById('panel-corex-content');
const decisionTime = document.getElementById('decision-time');

// Chat Drawer
const toggleChatBtn = document.getElementById('toggle-chat-btn');
const closeChatBtn = document.getElementById('close-chat-btn');
const chatDrawer = document.getElementById('chat-drawer');
const drawerOverlay = document.getElementById('drawer-overlay');
const chatBox = document.getElementById('chat-box');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

// --- Formatters ---
function formatCurrency(valueStr) {
    const num = parseFloat(valueStr);
    if (isNaN(num)) return '—';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num);
}

function formatTime(utcString) {
    if (!utcString) return new Date().toLocaleTimeString();
    return new Date(utcString).toLocaleTimeString([], { hour12: false });
}

// --- Status Handling ---
function showError(message) {
    errorBanner.textContent = message;
    errorBanner.classList.remove('hidden');
}
function hideError() {
    errorBanner.classList.add('hidden');
}
function updateConnectionStatus(isOnline) {
    if (isOnline) {
        healthStatus.className = 'status-indicator online';
        healthStatus.querySelector('span').textContent = 'SYSTEM ONLINE';
    } else {
        healthStatus.className = 'status-indicator offline';
        healthStatus.querySelector('span').textContent = 'SYSTEM OFFLINE';
    }
}

// --- API Calls ---
let isSystemOnline = false;

async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        const isOk = response.ok;
        updateConnectionStatus(isOk);
        
        // SMART AUTO-RECOVERY: 
        if (isOk && !isSystemOnline) {
            console.log("System reconnected! Auto-fetching portfolio...");
            isSystemOnline = true; // State update kar di
            fetchPortfolio();      // Chup-chaap data le aao
        } 
        else if (!isOk) {
            isSystemOnline = false; // System band ho gaya
        }
        
        return isOk;
    } catch (error) {
        updateConnectionStatus(false);
        isSystemOnline = false; // System band hai
        return false;
    }
}


function clearPortfolioUI() {
    // 1. Clear Portfolio
    portfolioValueEl.textContent = '$--.--';
    buyingPowerEl.textContent = '$--.--';
    posCountEl.textContent = '0';
    positionsBody.innerHTML = '<tr><td colspan="4" class="empty-state" style="color: var(--color-down);">System offline. Data unavailable.</td></tr>';

    // 2. Clear Architecture Panels
    decisionContent.innerHTML = '<div class="empty-state">Waiting for evaluation...</div>';
    riskContent.innerHTML = '<div class="empty-state">Waiting for proposal...</div>';
    corexContent.innerHTML = '<div class="empty-state">Waiting for routing...</div>';
    decisionTime.textContent = '—';

    // 3. Clear Live Activity Console
    activityFeed.innerHTML = `
        <div class="feed-item item-ERROR">
            <span class="feed-time">${new Date().toLocaleTimeString([], { hour12: false })}</span>
            <span class="feed-tag">[OFFLINE]</span>
            <span class="feed-msg" style="color: var(--color-down);">Connection to Axiom Trade Labs Backend lost. Waiting to reconnect...</span>
        </div>
    `;
}

async function fetchPortfolio() {
    hideError();
    const isHealthy = await checkHealth();
    
    // Agar server offline hai, toh UI clear kar do aur ruk jao
    if (!isHealthy) {
        clearPortfolioUI();
        return;
    }

    refreshBtn.disabled = true;
    try {
        const response = await fetch(`${API_BASE_URL}/portfolio`);
        if (!response.ok) throw new Error("Failed to fetch portfolio data.");
        
        const data = await response.json();
        
        // Update HUD
        portfolioValueEl.textContent = formatCurrency(data.portfolio_value);
        buyingPowerEl.textContent = formatCurrency(data.buying_power);
        posCountEl.textContent = data.positions ? data.positions.length : 0;

        // Update Positions Table
        positionsBody.innerHTML = '';
        if (!data.positions || data.positions.length === 0) {
            positionsBody.innerHTML = '<tr><td colspan="4" class="empty-state">No open positions.</td></tr>';
        } else {
            data.positions.forEach(pos => {
                const tr = document.createElement('tr');
                const plNum = parseFloat(pos.unrealized_pl);
                const plClass = plNum >= 0 ? 'profit' : 'loss';
                const plPrefix = plNum >= 0 ? '+' : '';

                tr.innerHTML = `
                    <td><strong>${pos.symbol}</strong></td>
                    <td class="text-right">${pos.qty}</td>
                    <td class="text-right">${formatCurrency(pos.market_value)}</td>
                    <td class="text-right ${plClass}">${plPrefix}${formatCurrency(pos.unrealized_pl)}</td>
                `;
                positionsBody.appendChild(tr);
            });
        }
    } catch (error) {
        console.error(error);
        showError(error.message);
        // Agar fetch karte time error aaye tab bhi UI clear kar do
        clearPortfolioUI();
    } finally {
        refreshBtn.disabled = false;
    }
}

// Smart Debounce Timer for Portfolio Updates
let portfolioUpdateTimer = null;

function triggerSmartPortfolioUpdate() {
    // Agar pehle se koi timer chal raha hai (multiple trades aa rahe hain), toh usko tod do
    if (portfolioUpdateTimer) {
        clearTimeout(portfolioUpdateTimer);
    }
    
    // Aakhiri trade aane ke exactly 2.5 seconds baad portfolio fetch karo
    portfolioUpdateTimer = setTimeout(() => {
        console.log("Executions settled. Smart updating portfolio...");
        fetchPortfolio();
    }, 2500);
}


// --- SSE Activity Stream & Workspace Architecture Updates ---
function setupActivityStream() {
    const evtSource = new EventSource(`${API_BASE_URL}/activity-stream`);

    evtSource.onopen = () => {
        // Top HUD Status
        streamStatusEl.textContent = 'CONNECTED';
        streamStatusEl.style.color = 'var(--color-up)';
        
        // Console Status
        consoleStreamStatusEl.textContent = 'STREAM ACTIVE';
        consoleStreamStatusEl.className = 'console-status status-passed';
        
        // Sidebar Status
        updateConnectionStatus(true); 

        activityFeed.innerHTML = `
            <div class="feed-item item-SYSTEM">
                <span class="feed-time">${new Date().toLocaleTimeString([], { hour12: false })}</span>
                <span class="feed-tag">[SYSTEM]</span>
                <span class="feed-msg" style="color: var(--color-up);">Connection established with Axiom Trade Labs Backend. Listening for events...</span>
            </div>
        `;
    };

    evtSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            const safeCategory = (data.category && /^[A-Z_]+$/.test(data.category)) ? data.category : 'SYSTEM';
            const timeStr = formatTime(data.timestamp_utc);
            
            appendConsoleEvent(safeCategory, timeStr, data.message, data.safe_metadata);
            
            if (safeCategory === 'DECISION') {
                updateDecisionPanel(data.safe_metadata, timeStr);
            } else if (safeCategory === 'RISK') {
                updateRiskPanel(data.safe_metadata);
            } else if (safeCategory === 'EXECUTION') {
                updateCorexPanel(data.safe_metadata);
            }
        } catch (e) {
            console.error("SSE Parse Error:", e);
        }
    };

    evtSource.onerror = function() {
        streamStatusEl.textContent = 'DISCONNECTED';
        streamStatusEl.style.color = 'var(--color-down)';
        consoleStreamStatusEl.textContent = 'STREAM OFFLINE';
        consoleStreamStatusEl.className = 'console-status status-blocked';
        
        // 🚀 NEW: Sidebar ko instantly RED (Offline) kar dega
        updateConnectionStatus(false);
    };
}

function appendConsoleEvent(category, timeStr, message, metadata) {
    const item = document.createElement('div');
    item.className = `feed-item item-${category}`;
    
    let metaHtml = '';
    if (metadata && typeof metadata === 'object') {
        const cleanMeta = Object.keys(metadata)
            .filter(k => metadata[k] !== null && metadata[k] !== undefined)
            .map(k => {
                let val = metadata[k];
                let valClass = 'meta-value';
                
                // Smart Formatting
                if (k === 'price') {
                    val = `$${parseFloat(val).toFixed(2)}`;
                    valClass += ' meta-green'; 
                } 
                else if (k === 'confidence') {
                    val = `${(parseFloat(val) * 100).toFixed(1)}%`;
                }
                else if (k === 'outcome' || k === 'result' || category === 'LEARNING') {
                    // 🚀 FIX: Learning outcomes explicitly colored
                    if(val === 'WIN' || val.toString().toLowerCase().includes('success')) {
                        valClass += ' meta-green';
                    } else if (val === 'LOSS' || val === 'EXPIRED') {
                        valClass += ' meta-red';
                    }
                }
                
                // Key-Value Pill Generation
                return `<span class="meta-item"><span class="meta-key">${k}:</span><span class="${valClass}">${val}</span></span>`;
            });
            
        if (cleanMeta.length > 0) {
            metaHtml = `<span class="feed-meta"><span class="meta-divider">|</span> ${cleanMeta.join(' ')}</span>`;
        }
    }

    item.innerHTML = `
        <span class="feed-time">${timeStr}</span>
        <span class="feed-tag">[${category}]</span>
        <span class="feed-msg">${message || 'Unknown event'}</span>
        ${metaHtml}
    `;
    
    activityFeed.appendChild(item);
    
    // Memory bound: max 100 console items
    if (activityFeed.children.length > 100) {
        activityFeed.removeChild(activityFeed.firstChild);
    }
    
    // Auto-scroll logic
    const threshold = 50; 
    const isNearBottom = activityFeed.scrollHeight - activityFeed.clientHeight - activityFeed.scrollTop < threshold;
    if (isNearBottom) {
        activityFeed.scrollTop = activityFeed.scrollHeight;
    }
}

// --- Dynamic Panel Updaters ---
function updateDecisionPanel(meta, timeStr) {
    if (!meta) return;
    
    // Agar yeh sirf routing/queued ka log hai jisme naya decision nahi hai, toh panel overwrite mat karo
    if (meta.reason && meta.reason.includes('queued')) return; 

    decisionTime.textContent = timeStr;
    const symbol = meta.symbol || '—';
    const confidence = meta.confidence ? `${(parseFloat(meta.confidence) * 100).toFixed(1)}%` : '—';
    const hypothesis = meta.hypothesis || meta.reason || '—';
    
    // 🚀 FIX: Smart detection for BUY/SELL even if exact word is missing
    let badgeClass = 'bg-neutral';
    let decisionText = 'NO TRADE';
    const checkStr = hypothesis.toLowerCase();
    
    if (checkStr.includes('buy') || checkStr.includes('trend') || checkStr.includes('accepted')) { 
        badgeClass = 'bg-buy'; decisionText = 'BUY'; 
    }
    else if (checkStr.includes('sell') || checkStr.includes('reduction')) { 
        badgeClass = 'bg-sell'; decisionText = 'SELL'; 
    }

    decisionContent.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div style="font-size: 20px; font-weight: 700;">${symbol}</div>
            <div class="decision-badge ${badgeClass}">${decisionText}</div>
        </div>
        <div style="margin-top: 16px; display: flex; flex-direction: column; gap: 8px;">
            <div class="arch-data-row">
                <span class="arch-label">Confidence</span>
                <span class="arch-value">${confidence}</span>
            </div>
            <div class="arch-data-row">
                <span class="arch-label">Hypothesis</span>
                <!-- Text ko wrap karke proper jagah di hai -->
                <span class="arch-value" style="font-size:11px; text-align: right; max-width: 150px; white-space: normal; line-height: 1.3;">${hypothesis}</span>
            </div>
        </div>
    `;
}

function updateRiskPanel(meta) {
    if (!meta) return;
    const reason = meta.reason || meta.message || 'Evaluated';
    const passed = reason.toLowerCase().includes('allow') || reason.toLowerCase().includes('pass');
    
    riskContent.innerHTML = `
        <div class="arch-data-row" style="margin-bottom: 12px;">
            <span class="arch-label">Status</span>
            <span class="arch-value ${passed ? 'status-passed' : 'status-blocked'}">
                ${passed ? 'APPROVED' : 'BLOCKED'}
            </span>
        </div>
        <div style="font-size: 11px; color: var(--text-muted); line-height: 1.4;">${reason}</div>
    `;
}

function updateCorexPanel(meta) {
    if (!meta) return;
    const status = meta.status || meta.reason || 'Routed';
    const symbol = meta.symbol || '—';
    const isSuccess = status.toLowerCase().includes('success') || status.toLowerCase().includes('fill');

    corexContent.innerHTML = `
        <div class="arch-data-row" style="margin-bottom: 12px;">
            <span class="arch-label">Target</span>
            <span class="arch-value">${symbol}</span>
        </div>
        <div class="arch-data-row">
            <span class="arch-label">State</span>
            <span class="arch-value ${isSuccess ? 'status-passed' : 'status-pending'}">${status.substring(0,20)}</span>
        </div>
    `;
    
    // Auto-refresh portfolio if execution succeeded
    if (isSuccess) {
        triggerSmartPortfolioUpdate();
    }
}

// --- Chat Drawer Logic ---
function toggleDrawer() {
    chatDrawer.classList.toggle('open');
    drawerOverlay.classList.toggle('hidden');
}

toggleChatBtn.addEventListener('click', toggleDrawer);
closeChatBtn.addEventListener('click', toggleDrawer);
drawerOverlay.addEventListener('click', toggleDrawer);

// Chat implementation (Preserved logic, updated DOM building)
function addMessage(payload, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message');
    
    if (sender === 'user') {
        msgDiv.classList.add('user-msg');
        msgDiv.textContent = payload;
    } else if (sender === 'ai') {
        msgDiv.classList.add('ai-msg');
        
        if (typeof payload === 'object' && payload !== null) {
            if (payload.error) {
                msgDiv.classList.add('ai-error');
                msgDiv.innerHTML = `<strong>Error:</strong> ${payload.error}<br><small>${payload.details || ''}</small>`;
            } 
            else if (payload.text_response) {
                let htmlContent = `<div>${payload.text_response.replace(/\n/g, '<br>')}</div>`;
                if (payload.debug_envelope) {
                    htmlContent += `
                        <details style="margin-top: 10px; font-size: 11px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; border: 1px solid var(--border-color);">
                            <summary style="cursor: pointer; color: var(--color-accent);">[View Deterministic Trace]</summary>
                            <pre style="margin-top: 8px; white-space: pre-wrap; word-wrap: break-word; font-family: var(--font-mono); color: var(--text-secondary);">${JSON.stringify(payload.debug_envelope, null, 2)}</pre>
                        </details>
                    `;
                }
                msgDiv.innerHTML = htmlContent;
            } 
            else if (payload.response) {
                msgDiv.innerHTML = `<pre style="font-family: var(--font-mono);">${JSON.stringify(payload.response, null, 2)}</pre>`;
            }
        } else {
            msgDiv.textContent = payload; 
        }
    }
    
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function handleChatSubmit() {
    const message = chatInput.value.trim();
    if (!message) return;

    addMessage(message, 'user');
    chatInput.value = '';
    
    sendBtn.disabled = true;
    sendBtn.textContent = '...';
    
    const loadingId = 'loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.className = 'message system-msg';
    loadingDiv.textContent = 'Analyzing context...';
    chatBox.appendChild(loadingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
        const data = await response.json();
        
        document.getElementById(loadingId).remove();
        addMessage(data, 'ai');
    } catch (error) {
        document.getElementById(loadingId).remove();
        addMessage({ error: "Agent offline", details: error.message }, 'ai');
    } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = 'SEND';
        chatInput.focus();
    }
}

// Chat Input (Enter Key)
chatInput.addEventListener('keypress', e => { if (e.key === 'Enter') handleChatSubmit(); });

if (sendBtn) {
    sendBtn.addEventListener('click', handleChatSubmit);
}

// Refresh Button
refreshBtn.addEventListener('click', fetchPortfolio);

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    fetchPortfolio();
    setupActivityStream();
    
    // 🚀 NEW: Heartbeat - Har 5 second mein backend check karega
    // Agar server wapas ON hoga, toh UI khud-ba-khud GREEN ho jayega!
    setInterval(checkHealth, 5000); 
});

// =========================================
// AXIOM AUTONOMOUS ENGINE (UI LOGIC)
// =========================================

// Elements
const navDashboardBtn = document.getElementById('nav-dashboard-btn');
const navAutonomousBtn = document.getElementById('nav-autonomous-btn');
const dashboardWorkspace = document.getElementById('dashboard-workspace');
const autonomousWorkspace = document.getElementById('autonomous-workspace');

// Autonomous Banners & Content
const autoFreezeBanner = document.getElementById('auto-freeze-banner');
const autoActiveBanner = document.getElementById('auto-active-banner');
const autoTimer = document.getElementById('auto-timer');
const autoRegime = document.getElementById('auto-regime');
const autoOptions = document.getElementById('auto-options');
const autoDecisionsBody = document.getElementById('auto-decisions-body');
const autoStrategyBody = document.getElementById('auto-strategy-body');
const autoLearningBody = document.getElementById('auto-learning-body');

let freezeTimerInterval = null;

// Tab Switching
navDashboardBtn.addEventListener('click', () => {
    navDashboardBtn.classList.add('active');
    navAutonomousBtn.classList.remove('active');
    dashboardWorkspace.classList.remove('hidden');
    autonomousWorkspace.classList.add('hidden');
});

navAutonomousBtn.addEventListener('click', () => {
    navAutonomousBtn.classList.add('active');
    navDashboardBtn.classList.remove('active');
    autonomousWorkspace.classList.remove('hidden');
    dashboardWorkspace.classList.add('hidden');
    fetchAutonomousState(); // Load data on click
});

// Fetch Authoritative Data
async function fetchAutonomousState() {
    try {
        const res = await fetch(`${API_BASE_URL}/autonomous/dashboard-state`);
        if (!res.ok) return;
        const data = await res.json();
        
        renderEngineStatus(data.engine_state);
        renderDecisions(data.recent_decisions);
        renderStrategies(data.strategy_preferences, data.engine_state.regime);
        renderLearning(data.recent_learning);
    } catch (e) {
        console.error("Failed to load autonomous state:", e);
    }
}

// 1. Render Status & Countdown Timer
function renderEngineStatus(state) {
    autoRegime.textContent = state.regime || "UNKNOWN";
    autoOptions.textContent = (state.policy && state.policy.allow_auto_options) ? "ENABLED" : "DISABLED";

    const unc = state.uncertainty;
    if (unc && unc.is_frozen) {
        autoActiveBanner.classList.add('hidden');
        autoFreezeBanner.classList.remove('hidden');
        startFreezeTimer(unc.expires_at_utc);
    } else {
        autoFreezeBanner.classList.add('hidden');
        autoActiveBanner.classList.remove('hidden');
        if (freezeTimerInterval) clearInterval(freezeTimerInterval);
    }
}

function startFreezeTimer(expiresAtUtc) {
    if (freezeTimerInterval) clearInterval(freezeTimerInterval);
    if (!expiresAtUtc) {
        autoTimer.innerHTML = "Waiting for recovery signal...";
        return;
    }

    const expireMs = new Date(expiresAtUtc).getTime();
    
    freezeTimerInterval = setInterval(() => {
        const left = Math.floor((expireMs - Date.now()) / 1000);
        if (left <= 0) {
            autoTimer.innerHTML = "Waiting for backend recovery signal...";
            clearInterval(freezeTimerInterval);
            fetchAutonomousState(); // Auto-refresh when timer hits 0
        } else {
            const m = Math.floor(left / 60).toString().padStart(2, '0');
            const s = (left % 60).toString().padStart(2, '0');
            autoTimer.innerHTML = `RESUMING IN <span>${m}:${s}</span>`;
        }
    }, 1000);
}

// 2. Render Decision Timeline
function renderDecisions(decisions) {
    if (!decisions || decisions.length === 0) {
        autoDecisionsBody.innerHTML = '<tr><td colspan="6" class="empty-state">No Meaningful Deviations Detected</td></tr>';
        return;
    }

    autoDecisionsBody.innerHTML = '';
    decisions.forEach(d => {
        const time = formatTime(d.created_at_utc);
        const asset = d.contract_symbol || d.symbol;
        const action = d.action.replace('_', ' ');
        const conf = d.action === 'NO_TRADE' ? '—' : `${(d.confidence * 100).toFixed(1)}%`;
        
        let statusBadge = `<span class="decision-badge bg-neutral">PROPOSED</span>`;
        if (d.terminal_status === 'EXECUTED') statusBadge = `<span class="decision-badge bg-buy">EXECUTED</span>`;
        else if (d.terminal_status === 'REJECTED' || d.status === 'BLOCKED') statusBadge = `<span class="decision-badge bg-sell">BLOCKED</span>`;
        else if (d.status === 'NO_TRADE') statusBadge = `<span style="color: var(--text-muted); font-size:11px; font-weight:bold;">ABSTAINED</span>`;

        autoDecisionsBody.innerHTML += `
            <tr class="hover-row">
                <td style="color: var(--text-muted);">${time}</td>
                <td style="color: #fff; font-weight:600;">${asset}</td>
                <td>${action}</td>
                <td style="color: var(--text-secondary);">${d.selected_hypothesis_id}</td>
                <td class="text-right">${conf}</td>
                <td>${statusBadge}</td>
            </tr>
        `;
    });
}

// 3. Render Bayesian Strategies
function renderStrategies(prefs, currentRegime) {
    const activePrefs = prefs.filter(p => p.regime === currentRegime)
                             .map(p => ({ ...p, posterior: p.alpha / (p.alpha + p.beta) }))
                             .sort((a, b) => b.posterior - a.posterior);

    if (activePrefs.length === 0) {
        autoStrategyBody.innerHTML = '<div class="empty-state">No active models for this regime.</div>';
        return;
    }

    autoStrategyBody.innerHTML = '';
    
    // Highlight currently favored
    if (activePrefs[0].observations > 0) {
        autoStrategyBody.innerHTML += `
            <div style="border: 1px solid rgba(59, 130, 246, 0.3); background: rgba(59, 130, 246, 0.05); padding: 12px; border-radius: 4px; margin-bottom: 16px;">
                <div style="font-size: 10px; color: var(--color-accent); font-family: var(--font-mono); margin-bottom: 4px;">CURRENTLY FAVORED</div>
                <div style="font-size: 14px; font-weight: 600; color: #fff;">${activePrefs[0].hypothesis_id}</div>
                <div style="font-size: 12px; color: var(--text-secondary); font-family: var(--font-mono); margin-top: 2px;">${(activePrefs[0].posterior * 100).toFixed(1)}% Win Prob</div>
            </div>
        `;
    }

    activePrefs.forEach(p => {
        const pct = (p.posterior * 100).toFixed(1) + '%';
        const displayPct = p.observations === 0 ? 'Insufficient Evidence' : pct;
        const barWidth = p.observations === 0 ? '0%' : pct;

        autoStrategyBody.innerHTML += `
            <div class="strat-row">
                <div class="strat-header">
                    <span>${p.hypothesis_id}</span>
                    <span>${displayPct}</span>
                </div>
                <div class="strat-bar-bg"><div class="strat-bar-fill" style="width: ${barWidth};"></div></div>
                <div class="strat-footer">n=${p.observations}</div>
            </div>
        `;
    });
}

// 4. Render Learning Ledger
function renderLearning(outcomes) {
    if (!outcomes || outcomes.length === 0) {
        autoLearningBody.innerHTML = '<div class="empty-state">No recent mature outcomes.</div>';
        return;
    }

    autoLearningBody.innerHTML = '';
    outcomes.forEach(o => {
        const time = formatTime(o.completed_at_utc);
        const winLoss = o.success ? '<span class="profit">WIN</span>' : '<span class="loss">LOSS</span>';
        const ret = (o.gross_return_pct * 100).toFixed(2);
        
        autoLearningBody.innerHTML += `
            <div class="learning-row">
                <div class="learning-header"><span>${time}</span> <span>${winLoss}</span></div>
                <div class="learning-body">Matured <span style="color:var(--color-accent)">${o.hypothesis_id}</span> on ${o.symbol}</div>
                <div class="learning-return">Return: ${ret}%</div>
            </div>
        `;
    });
}