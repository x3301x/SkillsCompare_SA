/* SkillsCompare SA: progressive enhancement only. Every page works without this file. */
(function () {
  'use strict';
  var small = window.matchMedia('(max-width: 55.99em)');

  /* Mobile navigation: a button toggles the nav list; without JS the list is simply visible. */
  var toggle = document.querySelector('.nav-toggle');
  var nav = document.getElementById('site-nav');
  if (toggle && nav) {
    var sync = function () { if (small.matches) { nav.hidden = toggle.getAttribute('aria-expanded') !== 'true'; } else { nav.hidden = false; } };
    toggle.addEventListener('click', function () {
      toggle.setAttribute('aria-expanded', toggle.getAttribute('aria-expanded') === 'true' ? 'false' : 'true'); sync();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true' && small.matches) { toggle.setAttribute('aria-expanded', 'false'); sync(); toggle.focus(); }
    });
    (small.addEventListener ? small.addEventListener('change', sync) : small.addListener(sync));
    sync();
  }


  /* Filter drawer (results page): a bottom sheet on phones, a plain sidebar on desktop. */
  var btn = document.querySelector('.filters-btn'), panel = document.getElementById('filters');
  if (btn && panel) {
    var scrim = document.querySelector('.scrim'), closeBtn = panel.querySelector('.filters__close');
    var open = function () {
      panel.classList.add('is-open'); scrim.hidden = false; btn.setAttribute('aria-expanded', 'true');
      panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); document.body.classList.add('lock');
      closeBtn.focus();
    };
    var close = function (ret) {
      panel.classList.remove('is-open'); scrim.hidden = true; btn.setAttribute('aria-expanded', 'false');
      panel.removeAttribute('role'); panel.removeAttribute('aria-modal'); document.body.classList.remove('lock');
      if (ret) btn.focus();
    };
    btn.addEventListener('click', function () { panel.classList.contains('is-open') ? close(true) : open(); });
    closeBtn.addEventListener('click', function () { close(true); });
    scrim.addEventListener('click', function () { close(true); });
    document.addEventListener('keydown', function (e) {
      if (!panel.classList.contains('is-open')) return;
      if (e.key === 'Escape') { close(true); return; }
      if (e.key === 'Tab') {   /* keep focus inside the open sheet */
        var f = panel.querySelectorAll('a[href],button:not([disabled]),input,select,textarea');
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    });
    (small.addEventListener ? small.addEventListener('change', function () { if (!small.matches) close(false); }) : 0);
  }

  /* Copy buttons: <button data-copy="text"> copies and announces via its own aria-live label. */
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-copy]'); if (!b) return;
    var text = b.getAttribute('data-copy'), label = b.getAttribute('data-label') || b.textContent;
    var done = function () { b.textContent = 'Copied'; setTimeout(function () { b.textContent = label; }, 1600); };
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done); }
    else { var t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); done(); } catch (x) {} document.body.removeChild(t); }
  });
})();
