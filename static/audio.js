/**
 * Aegis Suite - Tactile UI Procedural Audio Engine (v2.7.6)
 * 
 * Procedural Web Audio API sound synthesis.
 * Zero external audio assets, zero download latency, zero network dependency.
 * Designed for sub-50ms responsive acoustic feedback with intelligent deduplication,
 * active context resumption, and calibrated volume gains.
 */

(function (window) {
  'use strict';

  let audioCtx = null;
  const STORAGE_KEY = 'aegis_sound_enabled';

  // Rate-limiting / deduplication state to eliminate overlapping sounds
  let lastSoundTime = 0;
  let lastPreset = '';

  // Sound preference helpers (defaults to true if unset)
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
      playUiSound('toggle', { direction: 'on' });
    }
    return nextState;
  }

  // Obtain or create AudioContext instance
  function getAudioContext() {
    if (!audioCtx) {
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      if (AudioCtxClass) {
        audioCtx = new AudioCtxClass();
      }
    }
    return audioCtx;
  }

  // Ensure AudioContext is running before executing audio node synthesis
  function withRunningAudio(callback) {
    if (!isSoundEnabled()) return;

    const ctx = getAudioContext();
    if (!ctx) return;

    if (ctx.state === 'suspended') {
      ctx.resume().then(() => {
        if (ctx.state === 'running' && callback) {
          callback(ctx);
        }
      }).catch(() => {});
    } else if (ctx.state === 'running') {
      callback(ctx);
    }
  }

  /**
   * Play a procedural synthesized sound preset with deduplication guard.
   * @param {'click' | 'toggle' | 'success' | 'drawer' | 'error'} preset
   * @param {Object} [options]
   */
  function playUiSound(preset, options = {}) {
    if (!isSoundEnabled()) return;

    const nowMs = performance.now();
    const elapsed = nowMs - lastSoundTime;

    // Strict deduplication: suppress rapid duplicate sounds within 30ms
    if (elapsed < 30) {
      if ((preset === 'success' || preset === 'error') && (lastPreset === 'click' || lastPreset === 'toggle')) {
        // Allow higher priority alerts
      } else {
        return;
      }
    }

    if (elapsed < 60 && preset === lastPreset) {
      return;
    }

    lastSoundTime = nowMs;
    lastPreset = preset;

    withRunningAudio((ctx) => {
      try {
        const now = ctx.currentTime;

        switch (preset) {
          case 'click': {
            // Tactile mechanical key click (35ms duration, warm sine pitch sweep)
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(880, now);
            osc.frequency.exponentialRampToValueAtTime(360, now + 0.035);

            gain.gain.setValueAtTime(0.16, now);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.035);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start(now);
            osc.stop(now + 0.038);
            break;
          }

          case 'toggle': {
            // Crisp dual-tone switch blip with directional pitch (Apple / macOS style)
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'triangle';
            const isOff = options && options.direction === 'off';
            if (isOff) {
              // Soft descending tone for toggling OFF
              osc.frequency.setValueAtTime(640, now);
              osc.frequency.exponentialRampToValueAtTime(320, now + 0.045);
              gain.gain.setValueAtTime(0.14, now);
            } else {
              // Bright rising chime for toggling ON
              osc.frequency.setValueAtTime(440, now);
              osc.frequency.exponentialRampToValueAtTime(800, now + 0.045);
              gain.gain.setValueAtTime(0.18, now);
            }

            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.05);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start(now);
            osc.stop(now + 0.052);
            break;
          }

          case 'success': {
            // Soft harmonic chime chord (C5 -> E5 -> G5, gentle 240ms release)
            const notes = [
              { freq: 523.25, offset: 0.000 }, // C5
              { freq: 659.25, offset: 0.030 }, // E5
              { freq: 783.99, offset: 0.060 }  // G5
            ];

            notes.forEach(({ freq, offset }) => {
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();

              osc.type = 'sine';
              osc.frequency.setValueAtTime(freq, now + offset);

              gain.gain.setValueAtTime(0.0001, now + offset);
              gain.gain.exponentialRampToValueAtTime(0.14, now + offset + 0.015);
              gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.24);

              osc.connect(gain);
              gain.connect(ctx.destination);

              osc.start(now + offset);
              osc.stop(now + offset + 0.25);
            });
            break;
          }

          case 'drawer': {
            // Subtle air swoop for sliding panels & drawers
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(200, now);
            osc.frequency.exponentialRampToValueAtTime(460, now + 0.045);
            osc.frequency.exponentialRampToValueAtTime(280, now + 0.08);

            gain.gain.setValueAtTime(0.12, now);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.085);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start(now);
            osc.stop(now + 0.09);
            break;
          }

          case 'error': {
            // Soft low double tone warning
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'triangle';
            osc.frequency.setValueAtTime(220, now);
            osc.frequency.exponentialRampToValueAtTime(130, now + 0.09);

            gain.gain.setValueAtTime(0.16, now);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.1);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start(now);
            osc.stop(now + 0.105);
            break;
          }

          default:
            break;
        }
      } catch (e) {
        // Hardware device or synthesis failure
      }
    });
  }

  // Immediate and proactive user-activation unlock for Web Audio autoplay policy
  function unlockAudioContext() {
    const ctx = getAudioContext();
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
    }
  }

  // Bind early unlock listeners across all common gesture events
  ['click', 'pointerdown', 'mousedown', 'keydown', 'touchstart'].forEach(eventType => {
    window.addEventListener(eventType, unlockAudioContext, { capture: true, passive: true });
    document.addEventListener(eventType, unlockAudioContext, { capture: true, passive: true });
  });

  // Delegated UI listeners for automatic tactile feedback
  document.addEventListener('DOMContentLoaded', () => {
    // Global capture listener for interactive elements
    document.addEventListener('click', (e) => {
      if (e._audioHandled) return;

      const target = e.target.closest('button, .btn, .btn-circle, .btn-icon-only, .nav-item, .sub-tab-btn, .drawer-filter-chip, .tab-btn, a.btn, [role="button"]');
      if (!target || target.dataset.noSound === 'true') return;

      // Utility mute button has its own click handler
      if (target.id === 'btn-sound-toggle') return;

      e._audioHandled = true;
      playUiSound('click');
    }, true); // CAPTURE phase to ensure no inner stopPropagation intercepts tactile feedback

    // Checkbox toggles with directional acoustic feedback
    document.addEventListener('change', (e) => {
      if (e.target.matches('input[type="checkbox"], input[type="radio"]')) {
        if (e.target.dataset.noSound === 'true') return;
        const dir = e.target.checked ? 'on' : 'off';
        playUiSound('toggle', { direction: dir });
      }
    }, true);
  });

  // Diagnostic helper to test sound from DevTools or debug console
  window.testAegisAudio = function () {
    console.log('[Aegis Audio] Manual test triggered. Context:', audioCtx ? audioCtx.state : 'null', 'SoundEnabled:', isSoundEnabled());
    playUiSound('success');
  };

  // Expose API globally
  window.playUiSound = playUiSound;
  window.isSoundEnabled = isSoundEnabled;
  window.setSoundEnabled = setSoundEnabled;
  window.toggleSoundMute = toggleSoundMute;

})(window);
