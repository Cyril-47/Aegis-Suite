from aegis.core.state import ReasonCode

def get_recovery_html(reason_code: str, health_payload: dict) -> str:
    """Returns a premium, glassmorphic, responsive dark-themed Safe Mode Recovery UI HTML page.
    Fully styles all recovery cards and hooks them to AJAX recovery endpoints.
    """
    
    # Render health status tags with CSS classes
    def get_status_badge(val):
        if val in ("OK", "up", "connected_ready", "declared_enabled", True):
            return '<span class="badge badge-success">OK</span>'
        elif val in ("down", "disabled", "missing", "unknown", False):
            return '<span class="badge badge-error">Failed</span>'
        return f'<span class="badge badge-warn">{val}</span>'

    web_status = get_status_badge(health_payload.get("web"))
    
    db_payload = health_payload.get("database") or {}
    db_status = get_status_badge(db_payload.get("reachable") and db_payload.get("integrity_ok"))
    
    bot_status = get_status_badge(health_payload.get("bot"))
    intents_status = get_status_badge(health_payload.get("intents"))

    # Active Reason Code description and UI content
    reason_title = ""
    reason_description = ""
    reason_card_html = ""

    if reason_code == ReasonCode.NEEDS_SETUP:
        reason_title = "Onboarding Setup Required"
        reason_description = "Aegis Suite is starting for the first time and needs to be configured. The guided onboarding wizard is available."
        reason_card_html = """
        <div class="recovery-card-content">
            <p class="guide-text">The Setup Wizard will guide you through connecting your Discord bot and creating your community templates.</p>
            <div class="wizard-placeholder">
                <div class="wizard-icon">🚀</div>
                <h3>Welcome to Aegis Suite</h3>
                <p>Click below to begin the step-by-step setup configuration.</p>
                <button class="btn btn-primary" onclick="window.location.href='/setup'">Launch Setup Wizard</button>
            </div>
        </div>
        """
    elif reason_code == ReasonCode.TOKEN_RECOVERY:
        reason_title = "Discord Token Recovery"
        reason_description = "The configured Discord bot token is missing, invalid, or failed the authentication probe."
        reason_card_html = """
        <div class="recovery-card-content">
            <p class="guide-text">Please enter a valid Discord Bot Token. You can obtain your token from the <a href="https://discord.com/developers/applications" target="_blank" class="link">Discord Developer Portal</a>.</p>
            <form id="token-form" class="recovery-form" onsubmit="submitToken(event)">
                <div class="form-group">
                    <label for="discord-token">Bot Token</label>
                    <div class="input-wrapper">
                        <input type="password" id="discord-token" name="token" placeholder="Paste your bot token here..." required />
                        <button type="button" class="btn-toggle-visibility" onclick="toggleTokenVisibility()">👁️</button>
                    </div>
                </div>
                <div class="form-actions">
                    <button type="submit" class="btn btn-primary" id="token-submit-btn">Save & Validate Token</button>
                </div>
            </form>
            <div id="token-error" class="error-box hidden"></div>
        </div>
        """
    elif reason_code == ReasonCode.DB_RECOVERY:
        reason_title = "Database Recovery"
        reason_description = "The application SQLite database cannot be opened, is corrupted, or a schema migration failed."
        reason_card_html = """
        <div class="recovery-card-content">
            <p class="guide-text">Choose a recovery action to restore database operations. You can rebuild a fresh database or restore from a backup.</p>
            <div class="db-actions-grid">
                <div class="db-action-item">
                    <h4>Restore Database Backup</h4>
                    <p>Select a transactionally consistent backup from your backups folder.</p>
                    <div class="backup-selector-group">
                        <select id="backup-select" class="form-select">
                            <option value="">Loading backups...</option>
                        </select>
                        <button class="btn btn-primary" onclick="restoreBackup()" id="btn-restore">Restore Backup</button>
                    </div>
                </div>
                <div class="db-action-item danger-zone">
                    <h4>Rebuild Database from Scratch</h4>
                    <p>Destructive: Clears all tables and runs Alembic migrations from baseline. All leveling and music data will be reset.</p>
                    <button class="btn btn-danger" onclick="rebuildDatabase()" id="btn-rebuild">Rebuild Database</button>
                </div>
            </div>
            <div id="db-error" class="error-box hidden"></div>
        </div>
        """
    elif reason_code == ReasonCode.INTENT_RECOVERY:
        reason_title = "Privileged Gateway Intents Check Failed"
        reason_description = "The bot successfully logged in, but one or more required privileged gateway intents are not enabled in the Discord Developer Portal."
        reason_card_html = """
        <div class="recovery-card-content">
            <p class="guide-text">Aegis Suite requires the following privileged gateway intents to function:</p>
            <ul class="intents-list">
                <li class="intent-item checked"><strong>Presence Intent</strong> (For tracking status changes)</li>
                <li class="intent-item checked"><strong>Server Members Intent</strong> (For tracking join/leave, nicknames, and role assignments)</li>
                <li class="intent-item checked"><strong>Message Content Intent</strong> (For reading text command messages)</li>
            </ul>
            <div class="instructions-card">
                <h4>How to Enable Intents:</h4>
                <ol>
                    <li>Go to the <a href="https://discord.com/developers/applications" target="_blank" class="link">Discord Developer Portal</a> and log in.</li>
                    <li>Select your application / bot.</li>
                    <li>Navigate to the <strong>Bot</strong> tab in the left sidebar.</li>
                    <li>Scroll down to the <strong>Privileged Gateway Intents</strong> section.</li>
                    <li>Toggle <strong>ON</strong> all three intents (Presence, Server Members, Message Content).</li>
                    <li>Click <strong>Save Changes</strong> at the bottom.</li>
                </ol>
            </div>
            <div class="form-actions">
                <button class="btn btn-primary" onclick="retryStartup()" id="btn-recheck-intents">Re-check Gateway Intents</button>
            </div>
            <div id="intent-error" class="error-box hidden"></div>
        </div>
        """
    else:
        reason_title = "System Failure"
        reason_description = f"The application entered Safe Mode due to an unrecognized startup check failure: {reason_code}."
        reason_card_html = """
        <div class="recovery-card-content">
            <p class="guide-text">Please review the system logs or download a diagnostics package to inspect the exact failure traceback.</p>
        </div>
        """

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Aegis Suite - Safe Mode Recovery</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #0a0b10;
            --bg-gradient-start: #0c0f1d;
            --bg-gradient-end: #07070a;
            --card-bg: rgba(22, 28, 45, 0.45);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-glow: rgba(99, 102, 241, 0.15);
            
            --text-primary: #f3f4f6;
            --text-secondary: #9ca3af;
            --text-muted: #6b7280;
            
            --color-primary: #6366f1;
            --color-primary-hover: #4f46e5;
            --color-success: #10b981;
            --color-error: #ef4444;
            --color-warn: #f59e0b;
            
            --btn-danger-bg: rgba(239, 68, 68, 0.2);
            --btn-danger-border: rgba(239, 68, 68, 0.4);
            --btn-danger-hover: rgba(239, 68, 68, 0.35);
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: radial-gradient(circle at 50% 0%, var(--bg-gradient-start), var(--bg-gradient-end));
            background-color: var(--bg-base);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            padding: 20px;
            overflow-x: hidden;
        }

        .container {
            width: 100%;
            max-width: 780px;
            z-index: 10;
        }

        /* Header block */
        header {
            text-align: center;
            margin-bottom: 30px;
            animation: fadeInDown 0.6s ease-out;
        }

        .logo-area {
            display: inline-flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 8px;
        }

        .logo-icon {
            font-size: 32px;
            filter: drop-shadow(0 0 10px rgba(99, 102, 241, 0.6));
        }

        h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 2.2rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #fff 30%, #a5b4fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .safe-mode-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
            padding: 6px 12px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 10px;
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.1);
        }

        .safe-mode-badge::before {
            content: "";
            width: 8px;
            height: 8px;
            background-color: var(--color-error);
            border-radius: 50%;
            display: inline-block;
            animation: pulse 1.5s infinite;
        }

        /* Health bar */
        .health-bar {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 24px;
            backdrop-filter: blur(12px) saturate(180%);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
            animation: fadeInUp 0.6s ease-out 0.1s both;
        }

        .health-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.85rem;
        }

        .health-label {
            color: var(--text-secondary);
            font-weight: 500;
        }

        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        .badge-success {
            background: rgba(16, 185, 129, 0.15);
            color: #6ee7b7;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .badge-error {
            background: rgba(239, 68, 68, 0.15);
            color: #fca5a5;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .badge-warn {
            background: rgba(245, 158, 11, 0.15);
            color: #fde047;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }

        /* Main Workspace Glass Card */
        main {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 35px;
            backdrop-filter: blur(16px) saturate(180%);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.05);
            margin-bottom: 24px;
            position: relative;
            animation: fadeInUp 0.6s ease-out 0.2s both;
        }

        main::after {
            content: "";
            position: absolute;
            top: 0;
            left: 10%;
            right: 10%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.3), transparent);
        }

        .recovery-card-header {
            margin-bottom: 24px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 20px;
        }

        .recovery-card-header h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 8px;
        }

        .recovery-card-header p {
            font-size: 0.95rem;
            color: var(--text-secondary);
            line-height: 1.5;
        }

        .guide-text {
            font-size: 0.95rem;
            line-height: 1.6;
            color: var(--text-secondary);
            margin-bottom: 20px;
        }

        /* Forms */
        .recovery-form {
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .form-group label {
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-secondary);
        }

        .input-wrapper {
            position: relative;
            display: flex;
            align-items: center;
        }

        input[type="text"], input[type="password"], select {
            width: 100%;
            background: rgba(10, 11, 16, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 12px 16px;
            color: #ffffff;
            font-size: 0.95rem;
            font-family: inherit;
            transition: all 0.2s;
        }

        input[type="text"]:focus, input[type="password"]:focus, select:focus {
            outline: none;
            border-color: var(--color-primary);
            box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
            background: rgba(10, 11, 16, 0.8);
        }

        .input-wrapper input {
            padding-right: 48px;
        }

        .btn-toggle-visibility {
            position: absolute;
            right: 12px;
            background: none;
            border: none;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 1.1rem;
            padding: 4px;
        }

        /* Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-family: inherit;
            font-size: 0.9rem;
            font-weight: 600;
            padding: 12px 24px;
            border-radius: 8px;
            border: 1px solid transparent;
            cursor: pointer;
            transition: all 0.2s;
            text-decoration: none;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--color-primary), #4f46e5);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
        }

        .btn-primary:hover {
            background: linear-gradient(135deg, #4f46e5, #4338ca);
            transform: translateY(-1px);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-primary);
            border: 1px solid var(--card-border);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.2);
        }

        .btn-danger {
            background: var(--btn-danger-bg);
            color: #fca5a5;
            border: 1px solid var(--btn-danger-border);
        }

        .btn-danger:hover {
            background: var(--btn-danger-hover);
        }

        .form-actions {
            margin-top: 10px;
        }

        /* Links */
        .link {
            color: var(--color-primary);
            text-decoration: none;
            font-weight: 500;
            transition: color 0.2s;
        }

        .link:hover {
            color: #818cf8;
            text-decoration: underline;
        }

        /* Error box */
        .error-box {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.25);
            border-radius: 8px;
            padding: 12px 16px;
            color: #fca5a5;
            font-size: 0.85rem;
            line-height: 1.5;
            margin-top: 16px;
        }

        /* DB Recovery layout */
        .db-actions-grid {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .db-action-item {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            padding: 20px;
        }

        .db-action-item h4 {
            font-size: 1rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 8px;
        }

        .db-action-item p {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 16px;
            line-height: 1.5;
        }

        .backup-selector-group {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        .form-select {
            flex: 1;
            min-width: 200px;
        }

        .danger-zone {
            border-color: rgba(239, 68, 68, 0.15);
            background: rgba(239, 68, 68, 0.02);
        }

        /* Onboarding Needs-Setup wizard placeholder */
        .wizard-placeholder {
            text-align: center;
            padding: 30px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px dashed var(--card-border);
            border-radius: 12px;
        }

        .wizard-icon {
            font-size: 48px;
            margin-bottom: 16px;
        }

        .wizard-placeholder h3 {
            margin-bottom: 8px;
        }

        .wizard-placeholder p {
            font-size: 0.9rem;
            color: var(--text-secondary);
            margin-bottom: 20px;
        }

        /* Intents List */
        .intents-list {
            list-style: none;
            display: flex;
            flex-direction: column;
            gap: 10px;
            margin-bottom: 20px;
        }

        .intent-item {
            display: flex;
            align-items: center;
            gap: 10px;
            background: rgba(255, 255, 255, 0.02);
            padding: 10px 14px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.04);
            font-size: 0.9rem;
        }

        .intent-item::before {
            content: "⚠️";
            font-size: 1rem;
        }

        .instructions-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .instructions-card h4 {
            margin-bottom: 12px;
            font-size: 0.95rem;
            color: #ffffff;
        }

        .instructions-card ol {
            padding-left: 20px;
            font-size: 0.88rem;
            color: var(--text-secondary);
            display: flex;
            flex-direction: column;
            gap: 8px;
            line-height: 1.5;
        }

        /* Bottom Actions Panel */
        .bottom-actions {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
            animation: fadeInUp 0.6s ease-out 0.3s both;
        }

        .diagnostics-panel {
            font-size: 0.85rem;
            color: var(--text-secondary);
        }

        .general-actions-group {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }

        /* Progress spinner overlay */
        .overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(10, 11, 16, 0.85);
            backdrop-filter: blur(8px);
            z-index: 100;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            gap: 20px;
            transition: opacity 0.3s;
        }

        .hidden {
            display: none !important;
            opacity: 0;
            pointer-events: none;
        }

        .spinner {
            width: 50px;
            height: 50px;
            border: 4px solid rgba(99, 102, 241, 0.1);
            border-top-color: var(--color-primary);
            border-radius: 50%;
            animation: spin 1s infinite linear;
        }

        .overlay h3 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.3rem;
            color: #ffffff;
        }

        .overlay p {
            color: var(--text-secondary);
            font-size: 0.9rem;
        }

        /* Animations */
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.5; }
            50% { transform: scale(1.1); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.5; }
        }

        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Responsive styles */
        @media (max-width: 600px) {
            main {
                padding: 24px 20px;
            }

            .health-bar {
                flex-direction: column;
                align-items: flex-start;
                padding: 12px 16px;
            }

            .bottom-actions {
                flex-direction: column;
                align-items: stretch;
            }

            .general-actions-group {
                flex-direction: column;
            }

            .btn {
                width: 100%;
            }

            .backup-selector-group {
                flex-direction: column;
            }
            
            .form-select {
                width: 100%;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-area">
                <span class="logo-icon">🛡️</span>
                <h1>Aegis Suite</h1>
            </div>
            <div>
                <span class="safe-mode-badge">Safe Mode Recovery</span>
            </div>
        </header>

        <!-- Dynamic Health Registry Indicators -->
        <section class="health-bar">
            <div class="health-item">
                <span class="health-label">Web Interface:</span>
                {web_status}
            </div>
            <div class="health-item">
                <span class="health-label">Database:</span>
                {db_status}
            </div>
            <div class="health-item">
                <span class="health-label">Discord Connection:</span>
                {bot_status}
            </div>
            <div class="health-item">
                <span class="health-label">Gateway Intents:</span>
                {intents_status}
            </div>
        </section>

        <!-- Recovery Card -->
        <main>
            <section class="recovery-card-header">
                <h2>{reason_title}</h2>
                <p>{reason_description}</p>
            </section>

            {reason_card_html}
        </main>

        <!-- Fallback and General controls -->
        <footer class="bottom-actions">
            <div class="diagnostics-panel">
                Need support? <a href="/api/diagnostics/package" class="link">Download Diagnostics Pack</a>
            </div>
            <div class="general-actions-group">
                <button class="btn btn-secondary" onclick="retryStartup()" id="btn-global-retry">Retry Startup Checks</button>
                <button class="btn btn-danger" onclick="restartApplication()" id="btn-global-restart">Restart Application</button>
            </div>
        </footer>
    </div>

    <!-- AJAX Loading Spinner Overlay -->
    <div id="progress-overlay" class="overlay hidden">
        <div class="spinner"></div>
        <h3 id="overlay-title">Processing Request</h3>
        <p id="overlay-text">Please wait while the system updates...</p>
    </div>

    <script>
        // Toggle Discord Token input password visibility
        function toggleTokenVisibility() {
            const input = document.getElementById("discord-token");
            if (input.type === "password") {
                input.type = "text";
            } else {
                input.type = "password";
            }
        }

        // Helper to show full-screen progress overlay
        function showProgress(title, text) {
            document.getElementById("overlay-title").innerText = title;
            document.getElementById("overlay-text").innerText = text;
            document.getElementById("progress-overlay").classList.remove("hidden");
        }

        function hideProgress() {
            document.getElementById("progress-overlay").classList.add("hidden");
        }

        // General retry routine
        async function retryStartup() {
            showProgress("Checking System Status", "Re-running startup checks, please wait...");
            try {
                const res = await fetch("/api/recovery/retry", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" }
                });
                const data = await res.json();
                
                if (res.ok && data.status === "running") {
                    showProgress("Recovery Success", "All checks passed! Loading dashboard...");
                    setTimeout(() => {
                        window.location.href = "/";
                    }, 1500);
                } else {
                    hideProgress();
                    // If retry failed, show updated error status by reloading page
                    window.location.reload();
                }
            } catch (err) {
                hideProgress();
                alert("Failed to reach the Aegis service. Please check if the server is running.");
            }
        }

        // Global restart request
        async function restartApplication() {
            if (!confirm("Are you sure you want to trigger a full process restart?")) return;
            showProgress("Restarting Application", "Initiating shutdown. The process manager will restart Aegis shortly.");
            try {
                await fetch("/api/recovery/restart", {
                    method: "POST"
                });
                // Poll periodically until server is back, then reload
                setTimeout(async () => {
                    for (let i = 0; i < 20; i++) {
                        try {
                            const res = await fetch("/api/health");
                            if (res.ok) {
                                window.location.href = "/";
                                return;
                            }
                        } catch(e) {}
                        await new Promise(r => setTimeout(r, 1000));
                    }
                    hideProgress();
                    alert("Aegis is taking longer than expected to restart. Please refresh manually.");
                }, 2000);
            } catch (err) {
                // Ignore errors as connection might close during restart
            }
        }

        // Submit new token
        async function submitToken(event) {
            event.preventDefault();
            const token = document.getElementById("discord-token").value;
            const errorBox = document.getElementById("token-error");
            errorBox.classList.add("hidden");

            showProgress("Validating Token", "Authenticating against Discord API...");
            try {
                const res = await fetch("/api/recovery/token", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token: token })
                });
                const data = await res.json();
                
                if (res.ok) {
                    // Token saved and validated successfully, retry startup to promote state
                    await retryStartup();
                } else {
                    hideProgress();
                    errorBox.innerText = data.detail || "Authentication probe failed. Verify your token is correct.";
                    errorBox.classList.remove("hidden");
                }
            } catch (err) {
                hideProgress();
                errorBox.innerText = "Error: Connection failed. Is Aegis running?";
                errorBox.classList.remove("hidden");
            }
        }

        // Database backups retrieval
        async function loadBackups() {
            const select = document.getElementById("backup-select");
            if (!select) return;

            try {
                const res = await fetch("/api/recovery/backups");
                const backups = await res.json();
                
                select.innerHTML = "";
                if (backups.length === 0) {
                    const opt = document.createElement("option");
                    opt.value = "";
                    opt.innerText = "No backups found";
                    select.appendChild(opt);
                    document.getElementById("btn-restore").disabled = true;
                } else {
                    backups.forEach(name => {
                        const opt = document.createElement("option");
                        opt.value = name;
                        opt.innerText = name;
                        select.appendChild(opt);
                    });
                }
            } catch (err) {
                select.innerHTML = '<option value="">Failed to load backups</option>';
            }
        }

        // Restore backup
        async function restoreBackup() {
            const select = document.getElementById("backup-select");
            const backupName = select.value;
            const errorBox = document.getElementById("db-error");
            if (!backupName) return;

            errorBox.classList.add("hidden");
            if (!confirm(`Are you sure you want to restore "${backupName}"? Current tables will be overwritten.`)) return;

            showProgress("Restoring Backup", "Restoring SQLite database file and sidecars...");
            try {
                const res = await fetch("/api/recovery/db/restore", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ backup_name: backupName })
                });
                const data = await res.json();
                
                if (res.ok) {
                    await retryStartup();
                } else {
                    hideProgress();
                    errorBox.innerText = data.detail || "Failed to restore database backup.";
                    errorBox.classList.remove("hidden");
                }
            } catch (err) {
                hideProgress();
                errorBox.innerText = "Error: Connection failed.";
                errorBox.classList.remove("hidden");
            }
        }

        // Rebuild database from scratch
        async function rebuildDatabase() {
            const errorBox = document.getElementById("db-error");
            errorBox.classList.add("hidden");

            if (!confirm("CRITICAL WARNING: This will completely destroy all local leveling, server configurations, and history tables, and rebuild the schema from scratch. Are you sure?")) return;

            showProgress("Rebuilding Database", "Re-initializing SQLite tables and executing Alembic migrations...");
            try {
                const res = await fetch("/api/recovery/db/rebuild", {
                    method: "POST"
                });
                const data = await res.json();
                
                if (res.ok) {
                    await retryStartup();
                } else {
                    hideProgress();
                    errorBox.innerText = data.detail || "Failed to rebuild database.";
                    errorBox.classList.remove("hidden");
                }
            } catch (err) {
                hideProgress();
                errorBox.innerText = "Error: Connection failed.";
                errorBox.classList.remove("hidden");
            }
        }

        // Run on page load
        window.addEventListener("DOMContentLoaded", () => {
            if ("{reason_code}" === "{ReasonCode.DB_RECOVERY}") {
                loadBackups();
            }
        });
    </script>
</body>
</html>
"""

    html = html.replace("{web_status}", web_status)
    html = html.replace("{db_status}", db_status)
    html = html.replace("{bot_status}", bot_status)
    html = html.replace("{intents_status}", intents_status)
    html = html.replace("{reason_title}", reason_title)
    html = html.replace("{reason_description}", reason_description)
    html = html.replace("{reason_card_html}", reason_card_html)
    html = html.replace("{reason_code}", reason_code)
    html = html.replace("{ReasonCode.DB_RECOVERY}", ReasonCode.DB_RECOVERY)
    
    return html
