/**
 * tools/dashboard/static/studio.js
 * Frontend controller for the Phase 6 Script Studio and Human Review Interface.
 */

const studioState = {
  scripts: [],
  currentScriptId: null,
  currentRating: 0,
};

const studioDOM = {
  // Navigation
  navReelsBtn: document.getElementById('nav-reels-btn'),
  navStudioBtn: document.getElementById('nav-studio-btn'),
  viewReels: document.getElementById('view-reels'),
  viewStudio: document.getElementById('view-studio'),

  // Script List & Sidebar
  scriptsCount: document.getElementById('studio-scripts-count'),
  scriptList: document.getElementById('studio-script-list'),
  bibleToggleBtn: document.getElementById('studio-bible-toggle'),
  bibleBody: document.getElementById('studio-bible-body'),
  bibleContent: document.getElementById('studio-bible-content'),
  refReelsList: document.getElementById('studio-ref-reels'),

  // Screenplay Viewer
  scriptIdHeading: document.getElementById('studio-script-id'),
  scriptPremise: document.getElementById('studio-script-premise'),
  badgeRuntime: document.getElementById('studio-badge-runtime'),
  badgeWords: document.getElementById('studio-badge-words'),
  badgeStatus: document.getElementById('studio-badge-status'),
  screenplayPaper: document.getElementById('studio-screenplay-paper'),

  // Review Controls
  reviewStatusSelect: document.getElementById('review-status-select'),
  starBtns: document.querySelectorAll('.star-btn'),
  starRatingText: document.getElementById('star-rating-text'),
  reviewNotesInput: document.getElementById('review-notes-input'),
  saveReviewBtn: document.getElementById('save-review-btn'),
  reviewToast: document.getElementById('review-toast'),
};

/**
 * Switch active top-level tab between Reel Verification and Script Studio.
 */
function switchTab(target) {
  if (target === 'studio') {
    studioDOM.navReelsBtn.classList.remove('active');
    studioDOM.navStudioBtn.classList.add('active');
    studioDOM.viewReels.style.display = 'none';
    studioDOM.viewStudio.style.display = 'grid';
    loadScriptCatalog();
  } else {
    studioDOM.navStudioBtn.classList.remove('active');
    studioDOM.navReelsBtn.classList.add('active');
    studioDOM.viewStudio.style.display = 'none';
    studioDOM.viewReels.style.display = 'grid';
  }
}

/**
 * Fetch list of generated scripts from backend.
 */
async function loadScriptCatalog() {
  try {
    const res = await fetch('/api/scripts');
    if (!res.ok) throw new Error('Failed to fetch scripts');
    const scripts = await res.json();
    studioState.scripts = scripts;

    if (studioDOM.scriptsCount) {
      studioDOM.scriptsCount.textContent = scripts.length;
    }

    renderScriptList(scripts);

    // Auto-select first script or keep current selection
    if (scripts.length > 0) {
      const targetId = studioState.currentScriptId || scripts[0].script_id;
      selectScript(targetId);
    }
  } catch (err) {
    console.error('Error loading scripts catalog:', err);
  }
}

/**
 * Render script cards in the left sidebar.
 */
function renderScriptList(scripts) {
  if (!studioDOM.scriptList) return;

  if (scripts.length === 0) {
    studioDOM.scriptList.innerHTML = '<p class="placeholder-text">No scripts generated yet.</p>';
    return;
  }

  studioDOM.scriptList.innerHTML = '';
  scripts.forEach((s) => {
    const card = document.createElement('div');
    card.className = `script-item-card ${s.script_id === studioState.currentScriptId ? 'active' : ''}`;
    card.dataset.id = s.script_id;

    const statusClass = (s.status || 'draft').toLowerCase().replace(' ', '_');
    const statusLabel = (s.status || 'Draft').toUpperCase();

    card.innerHTML = `
      <div class="script-item-top">
        <span class="script-item-id">${s.script_id}</span>
        <span class="status-badge ${statusClass}">${statusLabel}</span>
      </div>
      <div class="script-item-premise">${escapeHtml(s.premise)}</div>
      <div class="script-item-footer">
        <span>⏱️ ${s.est_duration_sec}s (${s.word_count}w)</span>
        <span>${s.rating ? '★'.repeat(s.rating) : 'Unrated'}</span>
      </div>
    `;

    card.addEventListener('click', () => selectScript(s.script_id));
    studioDOM.scriptList.appendChild(card);
  });
}

/**
 * Load and render complete payload for selected script.
 */
async function selectScript(scriptId) {
  studioState.currentScriptId = scriptId;

  // Highlight active sidebar item
  document.querySelectorAll('.script-item-card').forEach((el) => {
    el.classList.toggle('active', el.dataset.id === scriptId);
  });

  try {
    const res = await fetch(`/api/script/${scriptId}`);
    if (!res.ok) throw new Error('Failed to load script payload');
    const data = await res.json();

    // Banner metadata
    if (studioDOM.scriptIdHeading) studioDOM.scriptIdHeading.textContent = `${data.script_id} (${data.creator_name || data.style_id})`;
    if (studioDOM.scriptPremise) studioDOM.scriptPremise.textContent = data.premise;
    if (studioDOM.badgeRuntime) studioDOM.badgeRuntime.textContent = `⏱️ ~${data.est_duration_sec} sec`;
    if (studioDOM.badgeWords) studioDOM.badgeWords.textContent = `${data.word_count} words`;

    const statusClass = (data.status || 'draft').toLowerCase().replace(' ', '_');
    if (studioDOM.badgeStatus) {
      studioDOM.badgeStatus.className = `badge status-badge ${statusClass}`;
      studioDOM.badgeStatus.textContent = (data.status || 'draft').toUpperCase();
    }

    // Render formatted screenplay paper
    renderScreenplayPaper(data.parsed_elements);

    // Style Bible
    if (studioDOM.bibleContent) {
      studioDOM.bibleContent.textContent = data.style_bible || 'No Style Bible found for this creator.';
    }

    // Reference Reels
    renderReferenceReels(data.reference_videos || []);

    // Review Card state
    if (studioDOM.reviewStatusSelect) {
      studioDOM.reviewStatusSelect.value = data.status || 'draft';
    }
    setRating(data.rating || 0);
    if (studioDOM.reviewNotesInput) {
      studioDOM.reviewNotesInput.value = data.review_notes || '';
    }
  } catch (err) {
    console.error('Error selecting script:', err);
  }
}

/**
 * Render screenplay parsed elements with typography classes.
 */
function renderScreenplayPaper(elements) {
  if (!studioDOM.screenplayPaper) return;
  studioDOM.screenplayPaper.innerHTML = '';

  if (!elements || elements.length === 0) {
    studioDOM.screenplayPaper.innerHTML = '<p class="placeholder-text">No screenplay lines found.</p>';
    return;
  }

  elements.forEach((el) => {
    if (el.type === 'blank') {
      const spacer = document.createElement('div');
      spacer.style.height = '0.75rem';
      studioDOM.screenplayPaper.appendChild(spacer);
      return;
    }

    const lineEl = document.createElement('div');
    lineEl.className = `sp-${el.type}`;
    lineEl.textContent = el.text;
    studioDOM.screenplayPaper.appendChild(lineEl);
  });
}

/**
 * Render reference reels list with quick jump button.
 */
function renderReferenceReels(refs) {
  if (!studioDOM.refReelsList) return;
  studioDOM.refReelsList.innerHTML = '';

  if (refs.length === 0) {
    studioDOM.refReelsList.innerHTML = '<p class="placeholder-text">No reference reels linked.</p>';
    return;
  }

  refs.forEach((r) => {
    const item = document.createElement('div');
    item.className = 'ref-reel-item';
    item.innerHTML = `
      <span style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-secondary);">${r.video_id}</span>
      <button class="play-reel-btn" data-video-id="${r.video_id}">▶ View Reel</button>
    `;

    const playBtn = item.querySelector('.play-reel-btn');
    playBtn.addEventListener('click', () => {
      jumpToReelVerification(r.video_id);
    });

    studioDOM.refReelsList.appendChild(item);
  });
}

/**
 * Quick jump from Script Studio to Reel Verification tab.
 */
function jumpToReelVerification(videoId) {
  switchTab('reels');
  if (DOM.videoSelect) {
    DOM.videoSelect.value = videoId;
    if (typeof loadVideoData === 'function') {
      loadVideoData(videoId);
    }
  }
}

/**
 * Set and visualize star rating (1-5).
 */
function setRating(rating) {
  studioState.currentRating = rating;
  studioDOM.starBtns.forEach((btn) => {
    const starVal = parseInt(btn.dataset.rating, 10);
    btn.classList.toggle('active', starVal <= rating);
  });

  if (studioDOM.starRatingText) {
    studioDOM.starRatingText.textContent = rating > 0 ? `${rating} / 5 Stars` : 'Not Rated';
  }
}

/**
 * Save human review decision to backend.
 */
async function saveReview() {
  if (!studioState.currentScriptId) return;

  const status = studioDOM.reviewStatusSelect.value;
  const rating = studioState.currentRating;
  const review_notes = studioDOM.reviewNotesInput.value;

  try {
    studioDOM.saveReviewBtn.disabled = true;
    studioDOM.saveReviewBtn.textContent = 'Saving...';

    const res = await fetch(`/api/script/${studioState.currentScriptId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, rating, review_notes }),
    });

    if (!res.ok) throw new Error('Save failed');
    const updated = await res.json();

    // Show toast
    if (studioDOM.reviewToast) {
      studioDOM.reviewToast.textContent = '✓ Review and rating saved!';
      studioDOM.reviewToast.classList.add('show');
      setTimeout(() => studioDOM.reviewToast.classList.remove('show'), 3000);
    }

    // Refresh script catalog to update badges
    await loadScriptCatalog();
    selectScript(studioState.currentScriptId);
  } catch (err) {
    console.error('Error saving review:', err);
    alert('Failed to save review. Please check server logs.');
  } finally {
    studioDOM.saveReviewBtn.disabled = false;
    studioDOM.saveReviewBtn.textContent = '💾 Save Human Review';
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/**
 * Download Hollywood standard screenplay PDF.
 */
function downloadPdf() {
  if (!studioState.currentScriptId) return;
  window.open(`/api/script/${studioState.currentScriptId}/export/pdf`, '_blank');
}

/**
 * Open and render shooting beat sheet modal table.
 */
async function openBeatSheetModal() {
  if (!studioState.currentScriptId) return;
  const overlay = document.getElementById('beatsheet-overlay');
  const body = document.getElementById('beatsheet-modal-body');
  const title = document.getElementById('beatsheet-modal-title');

  if (overlay) overlay.style.display = 'flex';
  if (body) body.innerHTML = '<p class="placeholder-text" style="text-align: center; padding: 2rem;">Generating shooting beat sheet...</p>';

  try {
    const res = await fetch(`/api/script/${studioState.currentScriptId}/beat_sheet`);
    if (!res.ok) throw new Error('Failed to load beat sheet');
    const data = await res.json();

    if (title) title.textContent = `🎬 Shooting Beat Sheet: ${data.script_id} (${data.total_beats} Beats | ~${data.est_total_duration})`;

    let html = `
      <table class="beatsheet-table">
        <thead>
          <tr>
            <th style="width: 60px;">Beat</th>
            <th style="width: 105px;">Time</th>
            <th style="width: 140px;">Phase</th>
            <th style="width: 200px;">Camera Framing</th>
            <th style="width: 120px;">Character</th>
            <th>Dialogue Cue</th>
            <th>Blocking & Props</th>
          </tr>
        </thead>
        <tbody>
    `;

    data.beats.forEach((b) => {
      html += `
        <tr>
          <td><span class="beat-num-badge">#${b.beat_number}</span></td>
          <td><span class="beat-time-badge">${b.time_range}</span></td>
          <td style="color: var(--text-secondary); font-size: 0.76rem;">${b.phase}</td>
          <td><span class="beat-framing-badge">${b.framing}</span></td>
          <td style="font-weight: 700; color: #fbbf24;">${b.character}</td>
          <td style="font-style: italic;">"${escapeHtml(b.dialogue_cue)}"</td>
          <td style="color: var(--text-muted); font-size: 0.76rem;">${escapeHtml(b.blocking_notes)}</td>
        </tr>
      `;
    });

    html += '</tbody></table>';
    if (body) body.innerHTML = html;
  } catch (err) {
    console.error('Error loading beat sheet:', err);
    if (body) body.innerHTML = '<p class="placeholder-text" style="color: #ef4444;">Failed to load beat sheet.</p>';
  }
}

/**
 * Download shooting beat sheet markdown file.
 */
function downloadBeatSheetMarkdown() {
  if (!studioState.currentScriptId) return;
  window.open(`/api/script/${studioState.currentScriptId}/export/beat_sheet`, '_blank');
}

/**
 * Setup listeners for Script Studio.
 */
function setupStudio() {
  // Navigation tabs
  if (studioDOM.navReelsBtn) studioDOM.navReelsBtn.addEventListener('click', () => switchTab('reels'));
  if (studioDOM.navStudioBtn) studioDOM.navStudioBtn.addEventListener('click', () => switchTab('studio'));

  // Star ratings
  studioDOM.starBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      const val = parseInt(btn.dataset.rating, 10);
      setRating(val);
    });
  });

  // Save review button
  if (studioDOM.saveReviewBtn) {
    studioDOM.saveReviewBtn.addEventListener('click', saveReview);
  }

  // Style Bible toggle
  if (studioDOM.bibleToggleBtn && studioDOM.bibleBody) {
    studioDOM.bibleToggleBtn.addEventListener('click', () => {
      const isVisible = studioDOM.bibleBody.style.display !== 'none';
      studioDOM.bibleBody.style.display = isVisible ? 'none' : 'block';
    });
  }

  // Export buttons
  const pdfBtn = document.getElementById('export-pdf-btn');
  if (pdfBtn) pdfBtn.addEventListener('click', downloadPdf);

  const beatsBtn = document.getElementById('export-beats-btn');
  if (beatsBtn) beatsBtn.addEventListener('click', openBeatSheetModal);

  const closeBeatsBtn = document.getElementById('close-beatsheet-btn');
  const overlay = document.getElementById('beatsheet-overlay');
  if (closeBeatsBtn && overlay) {
    closeBeatsBtn.addEventListener('click', () => {
      overlay.style.display = 'none';
    });
  }

  const downloadMdBtn = document.getElementById('download-beatsheet-md-btn');
  if (downloadMdBtn) downloadMdBtn.addEventListener('click', downloadBeatSheetMarkdown);
}

document.addEventListener('DOMContentLoaded', () => {
  setupStudio();
});

