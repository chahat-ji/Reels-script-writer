/**
 * tools/dashboard/static/script.js
 * Frontend controller for the Video-to-Style Verification Dashboard.
 * 
 * Features:
 * - Loads video catalog and dynamically populates selection menu.
 * - Streams video with range seeking support.
 * - Parses and renders compact extraction schema (Speakers, Scenes, Turns, Dynamics).
 * - Synchronizes active dialogue card in real-time with playback.
 * - Keeps active dialogue centered with auto-scrolling teleprompter.
 * - Interactive click-to-seek on any dialogue turn.
 */

// Application state
const state = {
  videos: [],
  currentVideoId: null,
  speakersMap: {},
  turns: [], // Array of { startMs, endMs, el, index }
  activeTurnIndex: -1,
  isUserScrolling: false,
};

// DOM References
const DOM = {
  videoSelect: document.getElementById('video-select'),
  badgeVideoId: document.getElementById('badge-video-id'),
  badgeScenes: document.getElementById('badge-scenes'),
  badgeTurns: document.getElementById('badge-turns'),
  turnsCounter: document.getElementById('turns-counter'),
  videoPlayer: document.getElementById('video-player'),
  timeOverlay: document.getElementById('time-overlay'),
  speakersList: document.getElementById('speakers-list'),
  dynamicsPanel: document.getElementById('dynamics-panel'),
  scriptContainer: document.getElementById('script-container'),
  autoscrollToggle: document.getElementById('autoscroll-toggle'),
  tabButtons: document.querySelectorAll('.tab-btn'),
  tabContents: document.querySelectorAll('.tab-content'),
};

/**
 * Format milliseconds into MM:SS.mmm format for display.
 */
function formatTime(ms) {
  if (typeof ms !== 'number' || isNaN(ms)) return '00:00.000';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const millis = Math.floor(ms % 1000);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`;
}

/**
 * Format milliseconds into clean MM:SS timestamp.
 */
function formatShortTime(ms) {
  if (typeof ms !== 'number' || isNaN(ms)) return '00:00';
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Initialize tab switching behavior for the Insights container.
 */
function setupTabs() {
  DOM.tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabTarget = btn.getAttribute('data-tab');
      DOM.tabButtons.forEach(b => b.classList.remove('active'));
      DOM.tabContents.forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetContent = document.getElementById(`tab-${tabTarget}`);
      if (targetContent) targetContent.classList.add('active');
    });
  });
}

/**
 * Fetch catalog of videos from server and populate dropdown.
 */
async function loadVideoCatalog() {
  try {
    const res = await fetch('/api/videos');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const videos = await res.json();
    state.videos = videos;

    DOM.videoSelect.innerHTML = '';
    if (videos.length === 0) {
      DOM.videoSelect.innerHTML = '<option value="">No videos found</option>';
      return;
    }

    let defaultVideoId = null;
    videos.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.video_id;
      const statusLabel = v.has_extraction ? '✓ Extracted' : v.status;
      opt.textContent = `${v.video_id} (${statusLabel})`;
      DOM.videoSelect.appendChild(opt);

      if (!defaultVideoId && v.has_extraction) {
        defaultVideoId = v.video_id;
      }
    });

    // Default to first extracted video or first item
    const selectedId = defaultVideoId || videos[0].video_id;
    DOM.videoSelect.value = selectedId;
    loadVideoData(selectedId);
  } catch (err) {
    console.error('Failed to load video catalog:', err);
    DOM.videoSelect.innerHTML = '<option value="">Error loading catalog</option>';
  }
}

/**
 * Fetch extraction payload and configure playback for selected video.
 */
async function loadVideoData(videoId) {
  state.currentVideoId = videoId;
  DOM.badgeVideoId.textContent = videoId;

  // Bind video source
  DOM.videoPlayer.src = `/stream/${videoId}`;
  DOM.videoPlayer.load();

  try {
    const res = await fetch(`/api/video/${videoId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    renderVideoPayload(data);
  } catch (err) {
    console.error('Failed to load video payload:', err);
    renderEmptyState('Failed to load extraction data for this video.');
  }
}

/**
 * Render characters, comedic mechanisms, scenes, and teleprompter turns.
 */
function renderVideoPayload(payload) {
  const extraction = payload.extraction;
  state.speakersMap = {};
  state.turns = [];
  state.activeTurnIndex = -1;

  if (!extraction) {
    renderEmptyState('No multimodal extraction found for this video yet. Run extraction first.');
    DOM.badgeScenes.textContent = '0 Scenes';
    DOM.badgeTurns.textContent = '0 Lines';
    DOM.turnsCounter.textContent = '0 lines';
    return;
  }

  // 1. Populate Speaker Map & Cast Tab
  DOM.speakersList.innerHTML = '';
  if (Array.isArray(extraction.sp)) {
    extraction.sp.forEach(sp => {
      state.speakersMap[sp.c] = sp.n || `Speaker ${sp.c}`;

      const card = document.createElement('div');
      card.className = 'speaker-card';
      card.innerHTML = `
        <div class="speaker-header">
          <span class="speaker-code-tag">${sp.c}</span>
          <span class="speaker-name">${escapeHtml(sp.n || 'Speaker ' + sp.c)}</span>
        </div>
        <p class="speaker-desc">${escapeHtml(sp.desc || 'No character description.')}</p>
      `;
      DOM.speakersList.appendChild(card);
    });
  }

  // 2. Populate Comedy Dynamics Tab
  DOM.dynamicsPanel.innerHTML = '';
  const cd = extraction.cd;
  if (cd) {
    let html = '';
    if (Array.isArray(cd.mech) && cd.mech.length > 0) {
      html += `
        <div class="dynamics-section">
          <div class="dynamics-title">Comedic Mechanisms</div>
          <div class="mechanism-chips">
            ${cd.mech.map(m => `<span class="chip">${escapeHtml(m)}</span>`).join('')}
          </div>
        </div>
      `;
    }
    if (cd.setup) html += `<div class="dynamic-row"><span class="dynamic-label">Setup:</span> ${escapeHtml(cd.setup)}</div>`;
    if (cd.esc) html += `<div class="dynamic-row"><span class="dynamic-label">Escalation:</span> ${escapeHtml(cd.esc)}</div>`;
    if (cd.rev) html += `<div class="dynamic-row"><span class="dynamic-label">Reversal:</span> ${escapeHtml(cd.rev)}</div>`;
    if (cd.punch) html += `<div class="dynamic-row"><span class="dynamic-label">Punchline:</span> ${escapeHtml(cd.punch)}</div>`;
    if (cd.rhythm) html += `<div class="dynamic-row"><span class="dynamic-label">Rhythm:</span> ${escapeHtml(cd.rhythm)}</div>`;
    if (cd.pace) html += `<div class="dynamic-row"><span class="dynamic-label">Pacing:</span> ${escapeHtml(cd.pace)}</div>`;
    DOM.dynamicsPanel.innerHTML = html || '<p class="placeholder-text">No dynamics parsed.</p>';
  } else {
    DOM.dynamicsPanel.innerHTML = '<p class="placeholder-text">No comedic dynamics available.</p>';
  }

  // 3. Build Teleprompter Script Container
  DOM.scriptContainer.innerHTML = '';
  const scenes = Array.isArray(extraction.sc) ? extraction.sc : [];
  let totalTurns = 0;

  DOM.badgeScenes.textContent = `${scenes.length} Scenes`;

  scenes.forEach((scene, sIdx) => {
    // Scene Divider Marker
    const sceneMarker = document.createElement('div');
    sceneMarker.style.padding = '0.5rem 0.25rem';
    sceneMarker.style.borderBottom = '1px solid rgba(255, 255, 255, 0.08)';
    sceneMarker.style.color = 'var(--text-muted)';
    sceneMarker.style.fontSize = '0.75rem';
    sceneMarker.style.fontFamily = 'var(--font-mono)';
    sceneMarker.innerHTML = `🎬 SCENE ${sIdx + 1} (${formatShortTime(scene.s)} - ${formatShortTime(scene.e)}) — <span style="color: var(--text-secondary);">${escapeHtml(scene.loc || 'Scene')}</span>`;
    DOM.scriptContainer.appendChild(sceneMarker);

    // Dialogue Turns in Scene
    const turns = Array.isArray(scene.x) ? scene.x : [];
    turns.forEach(turn => {
      // Compact Schema: [start_ms, end_ms, speaker_code, dialogue, emotion?, action?]
      const [startMs, endMs, spCode, dialogue, emotion, action] = turn;
      const speakerName = state.speakersMap[spCode] || `Speaker ${spCode}`;

      const card = document.createElement('div');
      card.className = 'turn-card';
      card.dataset.startMs = startMs;
      card.dataset.endMs = endMs;
      card.dataset.index = totalTurns;

      card.innerHTML = `
        <div class="turn-meta">
          <span class="turn-speaker-badge">${spCode} · ${escapeHtml(speakerName)}</span>
          <span class="turn-timestamp">${formatShortTime(startMs)} - ${formatShortTime(endMs)}</span>
          ${emotion ? `<span class="turn-emotion">${escapeHtml(emotion)}</span>` : ''}
        </div>
        <div class="turn-dialogue">${escapeHtml(dialogue)}</div>
        ${action ? `<div class="turn-action"><span>⚡</span> ${escapeHtml(action)}</div>` : ''}
      `;

      // Interactive Click-to-Seek
      card.addEventListener('click', () => {
        seekToTurn(startMs);
      });

      DOM.scriptContainer.appendChild(card);

      state.turns.push({
        startMs: Number(startMs),
        endMs: Number(endMs),
        el: card,
        index: totalTurns,
      });

      totalTurns++;
    });
  });

  DOM.badgeTurns.textContent = `${totalTurns} Lines`;
  DOM.turnsCounter.textContent = `${totalTurns} lines`;
}

/**
 * Handle seeking when user clicks on a dialogue card.
 */
function seekToTurn(startMs) {
  const seekSeconds = Math.max(0, (startMs / 1000) + 0.05);
  DOM.videoPlayer.currentTime = seekSeconds;
  DOM.videoPlayer.play().catch(() => {});
}

/**
 * Render empty or placeholder message in script container.
 */
function renderEmptyState(message) {
  DOM.scriptContainer.innerHTML = `
    <div class="teleprompter-empty-state">
      <span>📄</span>
      <p>${escapeHtml(message)}</p>
    </div>
  `;
}

/**
 * Escape HTML to prevent injection issues.
 */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Synchronize video playback time with script teleprompter.
 * Runs on every 'timeupdate' event from HTML5 video element.
 */
function handleTimeUpdate() {
  const currentTimeMs = DOM.videoPlayer.currentTime * 1000;
  DOM.timeOverlay.textContent = formatTime(currentTimeMs);

  if (state.turns.length === 0) return;

  // Find the turn matching the current playback time
  let activeIndex = -1;
  for (let i = 0; i < state.turns.length; i++) {
    const turn = state.turns[i];
    if (currentTimeMs >= turn.startMs && currentTimeMs <= turn.endMs) {
      activeIndex = i;
      break;
    }
  }

  // If between turns, find closest turn within 400ms margin
  if (activeIndex === -1) {
    for (let i = 0; i < state.turns.length; i++) {
      const turn = state.turns[i];
      if (currentTimeMs >= turn.startMs - 200 && currentTimeMs <= turn.endMs + 300) {
        activeIndex = i;
        break;
      }
    }
  }

  // Update active highlighted card if changed
  if (activeIndex !== state.activeTurnIndex) {
    if (state.activeTurnIndex !== -1 && state.turns[state.activeTurnIndex]) {
      state.turns[state.activeTurnIndex].el.classList.remove('active');
    }

    state.activeTurnIndex = activeIndex;

    if (activeIndex !== -1 && state.turns[activeIndex]) {
      const activeEl = state.turns[activeIndex].el;
      activeEl.classList.add('active');

      // Center active dialogue card in the teleprompter scrollbox
      if (DOM.autoscrollToggle.checked) {
        activeEl.scrollIntoView({
          behavior: 'smooth',
          block: 'center',
        });
      }
    }
  }
}

// Event Listeners
DOM.videoSelect.addEventListener('change', (e) => {
  if (e.target.value) {
    loadVideoData(e.target.value);
  }
});

DOM.videoPlayer.addEventListener('timeupdate', handleTimeUpdate);

// Startup initialization
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  loadVideoCatalog();
});

