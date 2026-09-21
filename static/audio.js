/**
 * Aegis Suite - Tactile UI Procedural Audio Engine (v2.7.5)
 * 
 * Procedural Web Audio API sound synthesis.
 * Zero external audio assets, zero download latency, zero network dependency.
 * Designed for sub-50ms responsive acoustic feedback with intelligent deduplication.
 */

(function (window) {
  'use strict';

  let audioCtx = null;
  const STORAGE_KEY = 'aegis_sound_enabled';

  // Rate-limiting / deduplication state to completely eliminate overlapping sounds
  let lastSoundTime = 0;
  let lastPreset = '';

  // Initialize or resume AudioContext
  function getAudioContext() {
    if (!audioCtx) {
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      if (AudioCtxClass) {
        audioCtx = new AudioCtxClass();
      }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
      audioCtx.resume().catch(() => {});
    }
    return audioCtx;
  }

  // Sound preference helpers
  function isSoundEnabled() {
    const pref = localStorage.getItem(STORAGE_KEY);
    return pref === null ? true : pref === 'true';
  }

  function setSoundEnabled(enabled) {
    localStorage.setItem(STORAGE_KEY, enabled ? 'true' : 'false');
    window.dispatchEvent(new CustomEvent('aegis-sound-state-changed', { detail: { enabled } }));
  }

  function toggleSoundMute() {
    const nextState = !isSoundEnabled();
    setSoundEnabled(nextState);
    if (nextState) {
      playUiSound('toggle');
    }
    return nextState;
  }

  /**
   * Play a procedural synthesized sound preset with deduplication guard.
   * @param {'click' | 'toggle' | 'success' | 'drawer' | 'error'} preset
   */
  function playUiSound(preset) {
    if (!isSoundEnabled()) return;

    const nowMs = performance.now();
    const elapsed = nowMs - lastSoundTime;

    // Strict deduplication: suppress any sound within 55ms unless higher priority
    if (elapsed < 55) {
      if ((preset === 'success' || preset === 'error') && (lastPreset === 'click' || lastPreset === 'toggle')) {
        // Allow success/error to take priority over immediate preceding click
      } else {
        return;
      }
    }

    // Suppress duplicate triggers of the exact same preset within 120ms
    if (elapsed < 120 && preset === lastPreset) {
      return;
    }

    lastSoundTime = nowMs;
    lastPreset = preset;

    try {
      const ctx = getAudioContext();
      if (!ctx) return;

      const now = ctx.currentTime;

      switch (preset) {
        case 'click': {
          // Ultra-crisp, subtle tactile click (Linear / macOS style, 20ms duration)
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'sine';
          osc.frequency.setValueAtTime(1100, now);
          osc.frequency.exponentialRampToValueAtTime(360, now + 0.02);

          gain.gain.setValueAtTime(0.035, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.02);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.022);
          break;
        }

        case 'toggle': {
          // Crisp dual-tone switch blip (subtle, 35ms duration)
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'triangle';
          osc.frequency.setValueAtTime(480, now);
          osc.frequency.exponentialRampToValueAtTime(680, now + 0.035);

          gain.gain.setValueAtTime(0.035, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.04);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.042);
          break;
        }

        case 'success': {
          // Soft harmonic chime chord (C5 -> E5 -> G5, gentle 160ms release)
          const notes = [
            { freq: 523.25, offset: 0.00 }, // C5
            { freq: 659.25, offset: 0.025 }, // E5
            { freq: 783.99, offset: 0.050 }  // G5
          ];

          notes.forEach(({ freq, offset }) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, now + offset);

            gain.gain.setValueAtTime(0.0001, now + offset);
            gain.gain.exponentialRampToValueAtTime(0.025, now + offset + 0.012);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.16);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start(now + offset);
            osc.stop(now + offset + 0.17);
          });
          break;
        }

        case 'drawer': {
          // Subtle air swoop for sliding panels & drawers
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'sine';
          osc.frequency.setValueAtTime(200, now);
          osc.frequency.exponentialRampToValueAtTime(420, now + 0.04);
          osc.frequency.exponentialRampToValueAtTime(260, now + 0.065);

          gain.gain.setValueAtTime(0.025, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.07);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.075);
          break;
        }

        case 'error': {
          // Soft low double tone warning
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'triangle';
          osc.frequency.setValueAtTime(220, now);
          osc.frequency.exponentialRampToValueAtTime(130, now + 0.08);

          gain.gain.setValueAtTime(0.04, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.09);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.095);
          break;
        }

        default:
          break;
      }
    } catch (e) {
      // Audio autoplay policy or hardware device unavailable
    }
  }

  // Delegated UI listeners for automatic tactile feedback
  document.addEventListener('DOMContentLoaded', () => {
    // Resume audio context on first user interaction anywhere in the window
    const unlockAudio = () => {
      getAudioContext();
      document.removeEventListener('pointerdown', unlockAudio);
    };
    document.addEventListener('pointerdown', unlockAudio, { once: true });

    // Global listener for interactive elements with event-handled deduplication
    document.addEventListener('click', (e) => {
      // If event was already handled by an inner listener, skip
      if (e._audioHandled) return;

      const target = e.target.closest('button, .nav-item, .drawer-filter-chip, a.btn, [role="button"]');
      if (!target || target.dataset.noSound === 'true') return;

      // Utility mute button has its own handler
      if (target.id === 'btn-sound-toggle') return;

      e._audioHandled = true;

      // Primary action buttons or general click
      if (target.classList.contains('nav-item')) {
        playUiSound('click');
      } else if (target.classList.contains('btn-primary') || target.classList.contains('btn-glow')) {
        playUiSound('click');
      } else if (target.classList.contains('btn-header-utility')) {
        playUiSound('click');
      }
    });

    // Checkbox toggles
    document.addEventListener('change', (e) => {
      if (e.target.matches('input[type="checkbox"], input[type="radio"]')) {
        if (e.target.dataset.noSound === 'true') return;
        playUiSound('toggle');
      }
    });
  });

  // Expose API globally
  window.playUiSound = playUiSound;
  window.isSoundEnabled = isSoundEnabled;
  window.setSoundEnabled = setSoundEnabled;
  window.toggleSoundMute = toggleSoundMute;

})(window);
