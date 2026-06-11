def get_wizard_html(health_payload: dict) -> str:
    """Returns a premium, glassmorphic, responsive dark-themed Setup Wizard HTML page.
    Implements exactly 4 steps: Connect Bot, Select Server, Verify Permissions, and Complete Setup.
    """
    import os
    token_preset = bool(os.environ.get("DISCORD_BOT_TOKEN"))
    if token_preset:
        token_input_html = """
                <div class="form-group">
                    <label for="discord-token">Discord Bot Token</label>
                    <div class="input-wrapper">
                        <input type="password" id="discord-token" value="••••••••••••••••••••" disabled />
                    </div>
                </div>
                <div class="success-box" style="margin-top: 16px;">
                    ✓ Discord bot token is pre-configured via the system environment. You may proceed.
                </div>
        """
        password_fields_html = ""
        btn_text = "Proceed"
        js_token_validated = "true"
    else:
        token_input_html = """
                <div class="form-group">
                    <label for="discord-token">Discord Bot Token</label>
                    <div class="input-wrapper">
                        <input type="password" id="discord-token" placeholder="Paste Discord Bot token here..." />
                        <button type="button" class="btn-toggle-visibility" onclick="togglePassword('discord-token')">👁️</button>
                    </div>
                </div>
        """
        password_fields_html = """
                <div class="form-group" id="pwd-group-1">
                    <label for="admin-password">Create Admin Password</label>
                    <div class="input-wrapper">
                        <input type="password" id="admin-password" placeholder="Min 8 characters..." />
                        <button type="button" class="btn-toggle-visibility" onclick="togglePassword('admin-password')">👁️</button>
                    </div>
                </div>
                <div class="form-group" id="pwd-group-2">
                    <label for="confirm-password">Confirm Admin Password</label>
                    <div class="input-wrapper">
                        <input type="password" id="confirm-password" placeholder="Confirm your password..." />
                        <button type="button" class="btn-toggle-visibility" onclick="togglePassword('confirm-password')">👁️</button>
                    </div>
                </div>
        """
        btn_text = "Validate & Save Token"
        js_token_validated = "false"

    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Aegis Suite - Setup Wizard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/responsive.css">
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

        header {
            text-align: center;
            margin-bottom: 30px;
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

        .wizard-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(99, 102, 241, 0.15);
            border: 1px solid rgba(99, 102, 241, 0.3);
            color: #a5b4fc;
            padding: 6px 12px;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 10px;
        }

        /* Step Indicator */
        .step-indicator {
            display: flex;
            justify-content: space-between;
            margin-bottom: 30px;
            position: relative;
        }

        .step-indicator::before {
            content: "";
            position: absolute;
            top: 15px;
            left: 5%;
            right: 5%;
            height: 2px;
            background: rgba(255, 255, 255, 0.08);
            z-index: 1;
        }

        .step-progress-bar {
            position: absolute;
            top: 15px;
            left: 5%;
            width: 0%;
            height: 2px;
            background: var(--color-primary);
            z-index: 2;
            transition: width 0.3s;
        }

        .step-dot {
            width: 32px;
            height: 32px;
            background: #111827;
            border: 2px solid rgba(255, 255, 255, 0.08);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.85rem;
            font-weight: 600;
            z-index: 3;
            transition: all 0.3s;
            color: var(--text-secondary);
        }

        .step-dot.active {
            border-color: var(--color-primary);
            color: #fff;
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.4);
            background: var(--color-primary);
        }

        .step-dot.completed {
            border-color: var(--color-success);
            color: #fff;
            background: var(--color-success);
        }

        /* Card styles */
        main {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 35px;
            backdrop-filter: blur(16px) saturate(180%);
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            margin-bottom: 24px;
            position: relative;
        }

        .wizard-step-panel {
            display: none;
        }

        .wizard-step-panel.active {
            display: block;
        }

        h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 1.5rem;
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 12px;
        }

        p.description {
            font-size: 0.95rem;
            color: var(--text-secondary);
            line-height: 1.6;
            margin-bottom: 24px;
        }

        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
            margin-bottom: 20px;
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
        }

        .actions-bar {
            display: flex;
            justify-content: space-between;
            margin-top: 30px;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 20px;
        }

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

        .success-box {
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.25);
            border-radius: 8px;
            padding: 12px 16px;
            color: #a7f3d0;
            font-size: 0.85rem;
            line-height: 1.5;
            margin-top: 16px;
        }

        .warning-box {
            background: rgba(245, 158, 11, 0.1);
            border: 1px solid rgba(245, 158, 11, 0.25);
            border-radius: 8px;
            padding: 12px 16px;
            color: #fde047;
            font-size: 0.85rem;
            line-height: 1.5;
            margin-top: 16px;
        }

        /* Guild List Layout */
        .guild-list-container {
            max-height: 250px;
            overflow-y: auto;
            border: 1px solid var(--card-border);
            border-radius: 8px;
            background: rgba(10, 11, 16, 0.4);
            padding: 8px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .guild-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 14px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            cursor: pointer;
            transition: all 0.2s;
        }

        .guild-item:hover {
            background: rgba(99, 102, 241, 0.08);
            border-color: rgba(99, 102, 241, 0.2);
        }

        .guild-item.selected {
            background: rgba(99, 102, 241, 0.15);
            border-color: var(--color-primary);
        }

        .guild-item input[type="radio"] {
            accent-color: var(--color-primary);
        }

        .guild-name {
            font-size: 0.95rem;
            font-weight: 500;
        }

        /* Permissions checklist */
        .permissions-checklist {
            display: flex;
            flex-direction: column;
            gap: 10px;
            background: rgba(10, 11, 16, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 20px;
        }

        .permission-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 4px 0;
            font-size: 0.9rem;
        }

        .permission-badge {
            font-size: 0.75rem;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 4px;
        }

        .perm-granted {
            background: rgba(16, 185, 129, 0.15);
            color: var(--color-success);
        }

        .perm-denied {
            background: rgba(239, 68, 68, 0.15);
            color: var(--color-error);
        }

        /* Overlay */
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
        }

        .spinner {
            width: 50px;
            height: 50px;
            border: 4px solid rgba(99, 102, 241, 0.1);
            border-top-color: var(--color-primary);
            border-radius: 50%;
            animation: spin 1s infinite linear;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        @media (max-width: 600px) {
            main {
                padding: 25px 20px;
            }
            .actions-bar {
                flex-direction: column;
                gap: 12px;
            }
            .btn {
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
            <div style="color: var(--text-secondary); font-size: 0.95rem; margin-top: 6px;">Welcome to Aegis Suite Onboarding</div>
            <div>
                <span class="wizard-badge">Setup Wizard</span>
            </div>
        </header>

        <!-- Stepper Dots -->
        <div class="step-indicator">
            <div class="step-progress-bar" id="progress-bar"></div>
            <div class="step-dot active" id="dot-1">1</div>
            <div class="step-dot" id="dot-2">2</div>
            <div class="step-dot" id="dot-3">3</div>
            <div class="step-dot" id="dot-4">4</div>
        </div>

        <main>
            <!-- STEP 1: Connect Bot -->
            <div class="wizard-step-panel active" id="step-panel-1">
                <h2>Discord Bot Connection</h2>
                <p class="description">Enter your Discord application's Bot Token. This credentials key is stored securely in the local DPAPI Secret Store on your system.</p>
                %%TOKEN_INPUT_HTML%%
                %%PASSWORD_FIELDS_HTML%%
                <div style="margin-top: 15px;">
                    <button class="btn btn-primary" onclick="verifyToken()" id="btn-verify-token">%%BTN_TEXT%%</button>
                </div>
                <div class="warning-box" style="margin-top: 16px;">
                    ⚠️ <strong>Gateway Intents Notice:</strong> Successful token validation verifies bot credentials, but <em>cannot</em> verify if privileged Gateway Intents (Presence, Server Members, Message Content) are enabled in the <a href="https://discord.com/developers/applications" target="_blank" style="color: #818cf8; text-decoration: underline;">Discord Developer Portal</a>. Please ensure these intents are enabled under the "Bot" tab of your application settings.
                </div>
                <div id="token-error" class="error-box hidden"></div>
                <div id="token-success" class="success-box hidden">✓ Token validation succeeded. Proceeding to server selection.</div>
            </div>

            <!-- STEP 2: Select Server -->
            <div class="wizard-step-panel" id="step-panel-2">
                <h2>Select target server</h2>
                <p class="description">Choose the target guild from the list of servers that your bot has been added to.</p>
                <div class="guild-list-container" id="guilds-list">
                    <p style="padding: 10px; color: var(--text-muted);">Loading servers list...</p>
                </div>
                <div id="guilds-error" class="error-box hidden"></div>
            </div>

            <!-- STEP 3: Verify Permissions -->
            <div class="wizard-step-panel" id="step-panel-3">
                <h2>Verify Bot Permissions</h2>
                <p class="description">Verifying bot's active permissions checklist on the selected server. A correct permission scope prevents template deployment failures.</p>
                
                <div class="permissions-checklist" id="permissions-checklist-container">
                    <!-- Dynamic Checklist -->
                </div>
                <div id="permissions-notice"></div>
            </div>

            <!-- STEP 4: Complete Setup -->
            <div class="wizard-step-panel" id="step-panel-4">
                <h2>Complete Setup Onboarding</h2>
                <p class="description">Ready to complete setup? Clicking complete will activate your configurations and promote your system to the running dashboard.</p>
                
                <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--card-border); border-radius: 8px; padding: 20px; line-height: 1.6;">
                    <h4>Configuration Overview:</h4>
                    <p style="color: var(--text-secondary); font-size: 0.9rem; margin-top: 10px;" id="summary-details">
                        Target Guild: (Selected Guild)
                    </p>
                </div>
                <div id="finish-error" class="error-box hidden"></div>
            </div>

            <!-- Global Actions Bar -->
            <div class="actions-bar">
                <button class="btn btn-secondary" onclick="prevStep()" id="btn-prev" disabled>Back</button>
                <button class="btn btn-primary" onclick="nextStep()" id="btn-next">Next</button>
            </div>
        </main>
    </div>

    <!-- Spinner overlay -->
    <div id="progress-overlay" class="overlay hidden">
        <div class="spinner"></div>
        <h3 id="overlay-title">Processing</h3>
        <p id="overlay-text">Connecting to Discord API...</p>
    </div>

    <script>
        let currentStep = 1;
        const totalSteps = 4;
        
        let tokenValidated = %%JS_TOKEN_VALIDATED%%;
        let selectedGuildId = "";
        let selectedGuildName = "";
        let selectedGuildPermissions = "0";
        let guildPermissionsMap = {};
        
        function updateStepDots() {
            for (let i = 1; i <= totalSteps; i++) {
                const dot = document.getElementById("dot-" + i);
                if (i < currentStep) {
                    dot.className = "step-dot completed";
                } else if (i === currentStep) {
                    dot.className = "step-dot active";
                } else {
                    dot.className = "step-dot";
                }
            }
            const progressPct = ((currentStep - 1) / (totalSteps - 1)) * 90;
            document.getElementById("progress-bar").style.width = progressPct + "%";
        }

        function showStep(step) {
            document.querySelectorAll(".wizard-step-panel").forEach(panel => {
                panel.classList.remove("active");
            });
            document.getElementById("step-panel-" + step).classList.add("active");
            
            // Manage button visibility/state
            document.getElementById("btn-prev").disabled = (step === 1);
            
            const nextBtn = document.getElementById("btn-next");
            if (step === totalSteps) {
                nextBtn.innerText = "Complete Setup";
                nextBtn.onclick = finishWizard;
            } else {
                nextBtn.innerText = "Next";
                nextBtn.onclick = nextStep;
            }
            
            // Step-specific locks
            if (step === 1) {
                nextBtn.disabled = !tokenValidated;
            } else if (step === 2) {
                nextBtn.disabled = !selectedGuildId;
            } else if (step === 3) {
                nextBtn.disabled = false; // Warnings shown but user can proceed
            } else {
                nextBtn.disabled = false;
            }
            
            updateStepDots();
        }

        function nextStep() {
            if (currentStep < totalSteps) {
                currentStep++;
                if (currentStep === 2) {
                    loadGuilds();
                } else if (currentStep === 3) {
                    verifyPermissions();
                } else if (currentStep === 4) {
                    document.getElementById("summary-details").innerHTML = `
                        Target Guild: <strong>${selectedGuildName}</strong> (ID: ${selectedGuildId})
                    `;
                }
                showStep(currentStep);
            }
        }

        function prevStep() {
            if (currentStep > 1) {
                currentStep--;
                showStep(currentStep);
            }
        }

        function togglePassword(id) {
            const input = document.getElementById(id);
            if (input) {
                input.type = input.type === "password" ? "text" : "password";
            }
        }

        function showOverlay(title, text) {
            const overlayTitle = document.getElementById("overlay-title");
            const overlayText = document.getElementById("overlay-text");
            if (overlayTitle) overlayTitle.innerText = title;
            if (overlayText) overlayText.innerText = text;
            const progressOverlay = document.getElementById("progress-overlay");
            if (progressOverlay) progressOverlay.classList.remove("hidden");
        }

        function hideOverlay() {
            const progressOverlay = document.getElementById("progress-overlay");
            if (progressOverlay) progressOverlay.classList.add("hidden");
        }

        async function verifyToken() {
            const tokenInput = document.getElementById("discord-token");
            const token = tokenInput ? tokenInput.value.trim() : "";
            const errBox = document.getElementById("token-error");
            const successBox = document.getElementById("token-success");
            
            if (errBox) errBox.classList.add("hidden");
            if (successBox) successBox.classList.add("hidden");
            
            if (token === "••••••••••••••••••••") {
                tokenValidated = true;
                nextStep();
                return;
            }
            
            if (!token) {
                if (errBox) {
                    errBox.innerText = "Token cannot be empty.";
                    errBox.classList.remove("hidden");
                }
                return;
            }
            
            // Validate password inputs if not preset
            const passwordInput = document.getElementById("admin-password");
            const confirmInput = document.getElementById("confirm-password");
            let password = "";
            if (passwordInput && confirmInput) {
                password = passwordInput.value.trim();
                const confirm = confirmInput.value.trim();
                if (password.length < 8) {
                    if (errBox) {
                        errBox.innerText = "Admin password must be at least 8 characters.";
                        errBox.classList.remove("hidden");
                    }
                    return;
                }
                if (password !== confirm) {
                    if (errBox) {
                        errBox.innerText = "Passwords do not match.";
                        errBox.classList.remove("hidden");
                    }
                    return;
                }
            }
            
            showOverlay("Validating Token", "Connecting to Discord auth gateway...");
            
            try {
                const payload = { token: token };
                if (password) {
                    payload.admin_password = password;
                }
                const response = await fetch("/wizard/token", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                
                const data = await response.json();
                hideOverlay();
                
                if (response.ok) {
                    tokenValidated = true;
                    if (successBox) successBox.classList.remove("hidden");
                    const nextBtn = document.getElementById("btn-next");
                    if (nextBtn) nextBtn.disabled = false;
                    setTimeout(nextStep, 1000);
                } else {
                    tokenValidated = false;
                    const nextBtn = document.getElementById("btn-next");
                    if (nextBtn) nextBtn.disabled = true;
                    if (errBox) {
                        errBox.innerText = data.detail || "Validation failed.";
                        errBox.classList.remove("hidden");
                    }
                }
            } catch (e) {
                hideOverlay();
                tokenValidated = false;
                const nextBtn = document.getElementById("btn-next");
                if (nextBtn) nextBtn.disabled = true;
                if (errBox) {
                    errBox.innerText = "Failed to reach backend API server: " + e;
                    errBox.classList.remove("hidden");
                }
            }
        }

        async function loadGuilds() {
            const listContainer = document.getElementById("guilds-list");
            const errBox = document.getElementById("guilds-error");
            const nextBtn = document.getElementById("btn-next");
            
            listContainer.innerHTML = '<p style="padding: 10px; color: var(--text-muted);">Fetching accessible guilds list...</p>';
            errBox.classList.add("hidden");
            nextBtn.disabled = true;
            
            try {
                const response = await fetch("/wizard/guilds");
                const guilds = await response.json();
                
                if (response.ok) {
                    if (guilds.length === 0) {
                        listContainer.innerHTML = '<p style="padding: 10px; color: var(--color-error);">No accessible guilds found. The bot must be invited to a server first.</p>';
                        errBox.innerText = "Error: Bot has not been invited to any guild. Please invite it and retry.";
                        errBox.classList.remove("hidden");
                        return;
                    }
                    
                    listContainer.innerHTML = "";
                    guildPermissionsMap = {};
                    guilds.forEach(g => {
                        guildPermissionsMap[g.id] = g.permissions || "0";
                        const div = document.createElement("div");
                        div.className = "guild-item";
                        div.id = "guild-" + g.id;
                        div.onclick = () => selectGuild(g.id, g.name);
                        div.innerHTML = `
                            <input type="radio" name="guild-radio" id="radio-${g.id}" ${selectedGuildId === g.id ? 'checked' : ''} />
                            <span class="guild-name">${g.name}</span>
                        `;
                        listContainer.appendChild(div);
                    });
                    
                    if (selectedGuildId) {
                        const preselected = document.getElementById("guild-" + selectedGuildId);
                        if (preselected) preselected.classList.add("selected");
                        nextBtn.disabled = false;
                    }
                } else {
                    listContainer.innerHTML = '<p style="padding: 10px; color: var(--color-error);">Failed to load guilds.</p>';
                    errBox.innerText = guilds.detail || "Failed to load servers.";
                    errBox.classList.remove("hidden");
                }
            } catch (e) {
                listContainer.innerHTML = '<p style="padding: 10px; color: var(--color-error);">API Error.</p>';
                errBox.innerText = "API Exception: " + e;
                errBox.classList.remove("hidden");
            }
        }

        function selectGuild(id, name) {
            selectedGuildId = id;
            selectedGuildName = name;
            selectedGuildPermissions = guildPermissionsMap[id] || "0";
            
            document.querySelectorAll(".guild-item").forEach(item => {
                item.classList.remove("selected");
            });
            document.getElementById("guild-" + id).classList.add("selected");
            document.getElementById("radio-" + id).checked = true;
            
            document.getElementById("btn-next").disabled = false;
        }

        function verifyPermissions() {
            const container = document.getElementById("permissions-checklist-container");
            const noticeContainer = document.getElementById("permissions-notice");
            container.innerHTML = "";
            
            const perms = BigInt(selectedGuildPermissions);
            const required = [
                { name: "Manage Channels", bit: 0x10n },
                { name: "Manage Roles", bit: 0x10000000n },
                { name: "Send Messages", bit: 0x800n },
                { name: "Embed Links", bit: 0x4000n },
                { name: "Read Message History", bit: 0x10000n },
                { name: "Connect (Voice playback)", bit: 0x100000n },
                { name: "Speak (Voice playback)", bit: 0x200000n }
            ];
            
            let allGranted = true;
            required.forEach(p => {
                const hasPerm = (perms & p.bit) === p.bit;
                if (!hasPerm) allGranted = false;
                
                const row = document.createElement("div");
                row.className = "permission-row";
                row.innerHTML = `
                    <span>${p.name}</span>
                    <span class="permission-badge ${hasPerm ? 'perm-granted' : 'perm-denied'}">
                        ${hasPerm ? '✓ Granted' : '✗ Missing'}
                    </span>
                `;
                container.appendChild(row);
            });
            
            if (allGranted) {
                noticeContainer.innerHTML = `
                    <div class="success-box">
                        ✓ All required bot permissions are successfully verified!
                    </div>
                `;
            } else {
                noticeContainer.innerHTML = `
                    <div class="warning-box">
                        ⚠️ <strong>Bot Lacks Permissions:</strong> Some required permissions are missing. You can continue, but server customization or voice playback features may fail unless you update the bot's role permissions in Discord.
                    </div>
                `;
            }
        }

        async function finishWizard() {
            const errBox = document.getElementById("finish-error");
            errBox.classList.add("hidden");
            
            showOverlay("Activating Setup", "Configuring application tables and starting bot task...");
            
            try {
                const response = await fetch("/wizard/finish", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        guild_id: selectedGuildId,
                        template_kind: ""
                    })
                });
                
                const data = await response.json();
                hideOverlay();
                
                if (response.ok) {
                    showOverlay("Success!", "Setup complete. Redirecting to dashboard...");
                    setTimeout(() => {
                        window.location.href = "/";
                    }, 1500);
                } else {
                    errBox.innerText = data.detail || "Finish endpoint returned non-OK status.";
                    errBox.classList.remove("hidden");
                }
            } catch (e) {
                hideOverlay();
                errBox.innerText = "Finish Request Failed: " + e;
                errBox.classList.remove("hidden");
            }
        }
    </script>
</body>
</html>
"""
    html = html.replace("%%TOKEN_INPUT_HTML%%", token_input_html)
    html = html.replace("%%PASSWORD_FIELDS_HTML%%", password_fields_html)
    html = html.replace("%%BTN_TEXT%%", btn_text)
    html = html.replace("%%JS_TOKEN_VALIDATED%%", js_token_validated)
    return html
