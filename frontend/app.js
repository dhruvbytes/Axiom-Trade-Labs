// Backend URL (FastAPI is running on port 8000)
const API_BASE_URL = 'http://127.0.0.1:8000/api';

// DOM Elements
const healthStatus = document.getElementById('health-status');
const errorBanner = document.getElementById('error-banner');
const portfolioValueEl = document.getElementById('portfolio-value');
const buyingPowerEl = document.getElementById('buying-power');
const positionsBody = document.getElementById('positions-body');
const refreshBtn = document.getElementById('refresh-btn');

// Chat DOM Elements
const chatBox = document.getElementById('chat-box');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');

// --- Functions ---

// 1. Helper: Format numbers to currency (e.g., 1000.5 -> $1,000.50)
function formatCurrency(valueStr) {
    const num = parseFloat(valueStr);
    if (isNaN(num)) return '$0.00';
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(num);
}

// 2. Helper: Show error on screen
function showError(message) {
    errorBanner.textContent = message;
    errorBanner.classList.remove('hidden');
}

// 3. Helper: Hide error on screen
function hideError() {
    errorBanner.classList.add('hidden');
}

// 4. Check Backend Health
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            healthStatus.textContent = 'Backend: 🟢 Online';
            healthStatus.className = 'status-badge online';
            return true;
        }
    } catch (error) {
        healthStatus.textContent = 'Backend: 🔴 Offline';
        healthStatus.className = 'status-badge offline';
        return false;
    }
}

// 5. Fetch Portfolio Data from FastAPI
async function fetchPortfolio() {
    hideError();
    
    // Check health first
    const isHealthy = await checkHealth();
    if (!isHealthy) {
        showError("Cannot connect to backend server. Make sure FastAPI is running.");
        return;
    }

    // Set UI to loading state
    refreshBtn.textContent = 'Refreshing...';
    refreshBtn.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/portfolio`);
        
        if (!response.ok) {
            // Handle HTTP errors returned by backend (e.g. 500)
            const errorData = await response.json();
            throw new Error(errorData.detail || "Failed to fetch portfolio.");
        }

        const data = await response.json();

        // Update Summary Cards
        portfolioValueEl.textContent = formatCurrency(data.portfolio_value);
        buyingPowerEl.textContent = formatCurrency(data.buying_power);

        // Update Positions Table
        positionsBody.innerHTML = ''; // Clear old rows
        
        if (data.positions.length === 0) {
            positionsBody.innerHTML = '<tr><td colspan="4" class="empty-state">No open positions found.</td></tr>';
        } else {
            data.positions.forEach(pos => {
                const tr = document.createElement('tr');
                
                // Color P&L green if positive, red if negative
                const plNum = parseFloat(pos.unrealized_pl);
                const plClass = plNum >= 0 ? 'profit' : 'loss';

                tr.innerHTML = `
                    <td><strong>${pos.symbol}</strong></td>
                    <td>${pos.qty}</td>
                    <td>${formatCurrency(pos.market_value)}</td>
                    <td class="${plClass}">${formatCurrency(pos.unrealized_pl)}</td>
                `;
                positionsBody.appendChild(tr);
            });
        }

    } catch (error) {
        console.error("Fetch Error:", error);
        showError(error.message);
    } finally {
        // Reset button state
        refreshBtn.textContent = 'Refresh Data';
        refreshBtn.disabled = false;
    }
}

// --- Chat Functions ---

function addMessage(payload, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.classList.add('message');
    
    if (sender === 'user') {
        msgDiv.classList.add('user-msg');
        msgDiv.textContent = payload;
    } else if (sender === 'ai') {
        msgDiv.classList.add('ai-msg');
        
        if (typeof payload === 'object' && payload !== null) {
            // Top-level error check
            if (payload.error) {
                msgDiv.classList.add('ai-error');
                msgDiv.innerHTML = `<strong>Error:</strong> ${payload.error}<br><small>${payload.details || ''}</small>`;
            } 
            // Naya Step 5 Format (text_response aur debug_envelope)
            else if (payload.text_response) {
                // 1. LLM Reporter ka human-readable text dikhao
                let htmlContent = `<div>${payload.text_response.replace(/\n/g, '<br>')}</div>`;
                
                // 2. Hackathon Judges ke liye ek cool 'Dropdown' add karo jo asli JSON Trace dikhaye
                if (payload.debug_envelope) {
                    htmlContent += `
                        <details style="margin-top: 15px; font-size: 0.85em; background: #f8f9fa; padding: 10px; border-radius: 6px; border: 1px solid #ddd;">
                            <summary style="cursor: pointer; font-weight: bold; color: #007bff;">
                                🔍 View Deterministic System Trace (ID: ${payload.debug_envelope.trace_id})
                            </summary>
                            <pre style="margin-top: 10px; white-space: pre-wrap; word-wrap: break-word; color: #333;">${JSON.stringify(payload.debug_envelope, null, 2)}</pre>
                        </details>
                    `;
                }
                msgDiv.innerHTML = htmlContent;
            } 
            else if (payload.response) {
                // Fallback format
                msgDiv.innerHTML = `<strong>Raw Output:</strong><br><pre>${JSON.stringify(payload.response, null, 2)}</pre>`;
            }
        } else {
            msgDiv.textContent = payload; // Pure text fallback
        }
    }
    
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function handleChatSubmit() {
    const message = chatInput.value.trim();
    if (!message) return;

    // 1. Show user message
    addMessage(message, 'user');
    chatInput.value = '';
    
    // 2. Show loading state
    sendBtn.disabled = true;
    sendBtn.textContent = 'Thinking...';
    
    // Add temporary loading message
    const loadingId = 'loading-' + Date.now();
    const loadingDiv = document.createElement('div');
    loadingDiv.id = loadingId;
    loadingDiv.className = 'message system-msg';
    loadingDiv.textContent = 'Agent is analyzing (this might take 10-15 seconds)...';
    chatBox.appendChild(loadingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        // 3. Send to FastAPI backend
        const response = await fetch(`${API_BASE_URL}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: message })
        });

        if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
        }

        const data = await response.json();
        
        // Remove loading message
        document.getElementById(loadingId).remove();
        
        // 4. Show combined AI + Risk Engine response
        addMessage(data, 'ai');

    } catch (error) {
        document.getElementById(loadingId).remove();
        addMessage({ error: "Failed to connect to Agent", details: error.message }, 'ai');
    } finally {
        // Reset button
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send';
        chatInput.focus();
    }
}

// Allow pressing Enter to send
chatInput.addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        handleChatSubmit();
    }
});

// --- Event Listeners ---
refreshBtn.addEventListener('click', fetchPortfolio);
sendBtn.addEventListener('click', handleChatSubmit);

// Initialize on page load
document.addEventListener('DOMContentLoaded', fetchPortfolio);