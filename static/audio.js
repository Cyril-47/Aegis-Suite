/**
 * Aegis Suite - Tactile UI Procedural Audio Engine (v2.7.4)
 * 
 * Procedural Web Audio API sound synthesis.
 * Zero external audio assets, zero download latency, zero network dependency.
 * Designed for sub-50ms responsive acoustic feedback.
 */

(function (window) {
  'use strict';

  let audioCtx = null;
  const STORAGE_KEY = 'aegis_sound_enabled';

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
      // Play a confirmation blip when unmuting
      playUiSound('toggle');
    }
    return nextState;
  }

  /**
   * Play a procedural synthesized sound preset.
   * @param {'click' | 'toggle' | 'success' | 'drawer' | 'error'} preset
   */
  function playUiSound(preset) {
    if (!isSoundEnabled()) return;

    try {
      const ctx = getAudioContext();
      if (!ctx) return;

      const now = ctx.currentTime;

      switch (preset) {
        case 'click': {
          // Ultra-crisp percussive tick (Linear / Raycast style)
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'sine';
          osc.frequency.setValueAtTime(820, now);
          osc.frequency.exponentialRampToValueAtTime(200, now + 0.04);

          gain.gain.setValueAtTime(0.065, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.045);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.05);
          break;
        }

        case 'toggle': {
          // Crisp dual-tone switch blip
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'triangle';
          osc.frequency.setValueAtTime(460, now);
          osc.frequency.exponentialRampToValueAtTime(740, now + 0.055);

          gain.gain.setValueAtTime(0.06, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.06);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.065);
          break;
        }

        case 'success': {
          // Elegant harmonic chime chord (C5 -> E5 -> G5 -> C6 arpeggio)
          const notes = [
            { freq: 523.25, offset: 0.00 }, // C5
            { freq: 659.25, offset: 0.03 }, // E5
            { freq: 783.99, offset: 0.06 }, // G5
            { freq: 1046.50, offset: 0.09 } // C6
          ];

          notes.forEach(({ freq, offset }) => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(freq, now + offset);

            gain.gain.setValueAtTime(0.0001, now + offset);
            gain.gain.exponentialRampToValueAtTime(0.045, now + offset + 0.015);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.22);

            osc.connect(gain);
            gain.connect(ctx.destination);

            osc.start(now + offset);
            osc.stop(now + offset + 0.23);
          });
          break;
        }

        case 'drawer': {
          // Soft air swoop for sliding panels & drawers
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'sine';
          osc.frequency.setValueAtTime(240, now);
          osc.frequency.exponentialRampToValueAtTime(520, now + 0.05);
          osc.frequency.exponentialRampToValueAtTime(320, now + 0.08);

          gain.gain.setValueAtTime(0.04, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.085);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.09);
          break;
        }

        case 'error': {
          // Subtle double tone low bump
          const osc = ctx.createOscillator();
          const gain = ctx.createGain();

          osc.type = 'triangle';
          osc.frequency.setValueAtTime(260, now);
          osc.frequency.exponentialRampToValueAtTime(140, now + 0.1);

          gain.gain.setValueAtTime(0.07, now);
          gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.11);

          osc.connect(gain);
          gain.connect(ctx.destination);

          osc.start(now);
          osc.stop(now + 0.12);
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
    // Resume audio context on first user click anywhere in the window
    const unlockAudio = () => {
      getAudioContext();
      document.removeEventListener('pointerdown', unlockAudio);
    };
    document.addEventListener('pointerdown', unlockAudio, { once: true });

    // Global listener for interactive elements
    document.addEventListener('click', (e) => {
      const target = e.target.closest('button, .nav-item, .drawer-filter-chip, a.btn, [role="button"]');
      if (!target || target.dataset.noSound === 'true') return;

      // Check if button is utility mute button (handled by its own listener)
      if (target.id === 'btn-sound-toggle') return;

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
