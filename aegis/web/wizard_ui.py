def get_wizard_html(health_payload: dict) -> str:
    """Returns a premium, glassmorphic, responsive dark-themed Setup Wizard HTML page.
    Fully implements the 5 steps: Welcome, Token entry, Server selection, Template selection, and Finish.
    """
    
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

        /* Templates Layout */
        .templates-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .template-card {
            padding: 20px 15px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.04);
            border-radius: 12px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        }

        .template-card:hover {
            background: rgba(99, 102, 241, 0.08);
            border-color: rgba(99, 102, 241, 0.2);
            transform: translateY(-2px);
        }

        .template-card.selected {
            background: rgba(99, 102, 241, 0.15);
            border-color: var(--color-primary);
            box-shadow: 0 0 15px rgba(99, 102, 241, 0.2);
        }

        .template-icon {
            font-size: 2rem;
            margin-bottom: 10px;
        }

        .template-title {
            font-size: 0.9rem;
            font-weight: 600;
            color: #fff;
        }

        .template-preview-area {
            background: rgba(10, 11, 16, 0.6);
            border: 1px solid var(--card-border);
            border-radius: 8px;
            padding: 16px;
            max-height: 180px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        .preview-header {
            font-weight: bold;
            color: #fff;
            margin-bottom: 8px;
        }

        .preview-item {
            margin-left: 12px;
            margin-bottom: 4px;
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
            <div class="step-dot" id="dot-5">5</div>
        </div>

        <main>
            <!-- STEP 1: Welcome -->
            <div class="wizard-step-panel active" id="step-panel-1">
                <h2>Welcome to Aegis Suite Onboarding</h2>
                <p class="description">This step-by-step wizard will configure your server environment, connect your Discord bot credentials securely, and set up your initial server template.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <div style="font-size: 64px;">🚀</div>
                    <p style="margin-top: 15px; color: var(--text-secondary);">Everything will be configured within your browser without command line tools.</p>
                </div>
            </div>

            <!-- STEP 2: Token Entry -->
            <div class="wizard-step-panel" id="step-panel-2">
                <h2>Discord Bot Connection</h2>
                <p class="description">Enter your Discord application's Bot Token. This credentials key is stored securely in the local DPAPI Secret Store on your system.</p>
                <div class="form-group">
                    <label for="discord-token">Discord Bot Token</label>
                    <div class="input-wrapper">
                        <input type="password" id="discord-token" placeholder="Paste Discord Bot token here..." />
                        <button type="button" class="btn-toggle-visibility" onclick="toggleToken()">👁️</button>
                    </div>
                </div>
                <div style="margin-top: 15px;">
                    <button class="btn btn-primary" onclick="verifyToken()" id="btn-verify-token">Validate & Save Token</button>
                </div>
                <div id="token-error" class="error-box hidden"></div>
                <div id="token-success" class="success-box hidden">✓ Token validation succeeded. Proceeding to server selection.</div>
            </div>

            <!-- STEP 3: Server Selection -->
            <div class="wizard-step-panel" id="step-panel-3">
                <h2>Select Discord Server</h2>
                <p class="description">Choose the target guild from the list of servers that your bot has been added to.</p>
                <div class="guild-list-container" id="guilds-list">
                    <p style="padding: 10px; color: var(--text-muted);">Loading servers list...</p>
                </div>
                <div id="guilds-error" class="error-box hidden"></div>
            </div>

            <!-- STEP 4: Template Selection -->
            <div class="wizard-step-panel" id="step-panel-4">
                <h2>Choose Community Structure</h2>
                <p class="description">Select a server design layout template. A structural blueprint of roles and channels will be applied.</p>
                
                <div class="templates-grid">
                    <div class="template-card" onclick="selectTemplate('gaming')" id="tpl-gaming">
                        <div class="template-icon">🎮</div>
                        <div class="template-title">Gaming</div>
                    </div>
                    <div class="template-card" onclick="selectTemplate('community')" id="tpl-community">
                        <div class="template-icon">📣</div>
                        <div class="template-title">Community</div>
                    </div>
                    <div class="template-card" onclick="selectTemplate('creator')" id="tpl-creator">
                        <div class="template-icon">🎥</div>
                        <div class="template-title">Creator</div>
                    </div>
                    <div class="template-card" onclick="selectTemplate('empty')" id="tpl-empty">
                        <div class="template-icon">🛡️</div>
                        <div class="template-title">Start Empty</div>
                    </div>
                </div>

                <div class="template-preview-area" id="template-preview">
                    <div class="preview-header">Template Preview</div>
                    <p style="color: var(--text-muted);">Select a template above to preview its structure.</p>
                </div>
            </div>

            <!-- STEP 5: Finish Onboarding -->
            <div class="wizard-step-panel" id="step-panel-5">
                <h2>Complete Setup Onboarding</h2>
                <p class="description">Ready to complete setup? Clicking complete will activate your configurations and promote your system to the running dashboard.</p>
                
                <div style="background: rgba(255, 255, 255, 0.02); border: 1px solid var(--card-border); border-radius: 8px; padding: 20px; line-height: 1.6;">
                    <h4>Configuration Overview:</h4>
                    <p style="color: var(--text-secondary); font-size: 0.9rem; margin-top: 10px;" id="summary-details">
                        Target Guild: (Selected Guild)<br>
                        Template: (Selected Template)
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
        const totalSteps = 5;
        
        let tokenValidated = false;
        let selectedGuildId = "";
        let selectedGuildName = "";
        let selectedTemplate = "";
        
        const templatesData = {
            gaming: {
                roles: ["Admin", "Moderator", "Gamer"],
                channels: ["Categories: INFORMATION, TEXT CHANNELS, VOICE", "Channels: #rules, #announcements, #general, #lfg, General Voice, Gaming Room"]
            },
            community: {
                roles: ["Admin", "Moderator", "Member"],
                channels: ["Categories: WELCOME, DISCUSSION, VOICE", "Channels: #welcome, #rules, #general, #chat, Lobby, Lounge"]
            },
            creator: {
                roles: ["Admin", "Moderator", "Subscriber", "Viewer"],
                channels: ["Categories: INFORMATION, CHAT, CONTENT", "Channels: #rules, #live-updates, #announcements, #general, #video-chat"]
            },
            empty: {
                roles: ["Admin"],
                channels: ["Categories: GENERAL", "Channels: #general, General Voice"]
            }
        };

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
            if (step === 2) {
                nextBtn.disabled = !tokenValidated;
            } else if (step === 3) {
                nextBtn.disabled = !selectedGuildId;
            } else if (step === 4) {
                nextBtn.disabled = !selectedTemplate;
            } else {
                nextBtn.disabled = false;
            }
            
            updateStepDots();
        }

        function nextStep() {
            if (currentStep < totalSteps) {
                currentStep++;
                if (currentStep === 3) {
                    loadGuilds();
                } else if (currentStep === 5) {
                    document.getElementById("summary-details").innerHTML = `
                        Target Guild: <strong>${selectedGuildName}</strong> (ID: ${selectedGuildId})<br>
                        Applied Template: <strong>${selectedTemplate.toUpperCase()}</strong>
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

        function toggleToken() {
            const input = document.getElementById("discord-token");
            input.type = input.type === "password" ? "text" : "password";
        }

        function showOverlay(title, text) {
            document.getElementById("overlay-title").innerText = title;
            document.getElementById("overlay-text").innerText = text;
            document.getElementById("progress-overlay").classList.remove("hidden");
        }

        function hideOverlay() {
            document.getElementById("progress-overlay").classList.add("hidden");
        }

        async function verifyToken() {
            const token = document.getElementById("discord-token").value.trim();
            const errBox = document.getElementById("token-error");
            const successBox = document.getElementById("token-success");
            
            errBox.classList.add("hidden");
            successBox.classList.add("hidden");
            
            if (!token) {
                errBox.innerText = "Token cannot be empty.";
                errBox.classList.remove("hidden");
                return;
            }
            
            showOverlay("Validating Token", "Connecting to Discord auth gateway...");
            
            try {
                const response = await fetch("/wizard/token", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ token: token })
                });
                
                const data = await response.json();
                hideOverlay();
                
                if (response.ok) {
                    tokenValidated = true;
                    successBox.classList.remove("hidden");
                    document.getElementById("btn-next").disabled = false;
                    setTimeout(nextStep, 1000);
                } else {
                    tokenValidated = false;
                    document.getElementById("btn-next").disabled = true;
                    errBox.innerText = data.detail || "Validation failed.";
                    errBox.classList.remove("hidden");
                }
            } catch (e) {
                hideOverlay();
                tokenValidated = false;
                document.getElementById("btn-next").disabled = true;
                errBox.innerText = "Failed to reach backend API server: " + e;
                errBox.classList.remove("hidden");
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
                    guilds.forEach(g => {
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
            
            document.querySelectorAll(".guild-item").forEach(item => {
                item.classList.remove("selected");
            });
            document.getElementById("guild-" + id).classList.add("selected");
            document.getElementById("radio-" + id).checked = true;
            
            document.getElementById("btn-next").disabled = false;
        }

        function selectTemplate(kind) {
            selectedTemplate = kind;
            
            document.querySelectorAll(".template-card").forEach(card => {
                card.classList.remove("selected");
            });
            document.getElementById("tpl-" + kind).classList.add("selected");
            
            const preview = document.getElementById("template-preview");
            const data = templatesData[kind];
            
            preview.innerHTML = `
                <div class="preview-header">${kind.toUpperCase()} Template Preview</div>
                <div class="preview-item"><strong>Roles:</strong> ${data.roles.join(", ")}</div>
                <div class="preview-item"><strong>Structure:</strong></div>
                ${data.channels.map(c => `<div class="preview-item" style="color: var(--text-muted);">${c}</div>`).join("")}
            `;
            
            document.getElementById("btn-next").disabled = false;
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
                        template_kind: selectedTemplate
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
    return html
