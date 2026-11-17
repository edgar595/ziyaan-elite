/* Ziyaan Élite — anonymous visit counter for the spray, category and about pages.
   Same rules as the shop page: no personal data, admins and ?notrack devices are skipped. */
(function () {
  var CFG = window.ZIYAAN_CONFIG || {};
  function ls(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
  function ss(k, v) { try { if (v === undefined) return sessionStorage.getItem(k); sessionStorage.setItem(k, v); } catch (e) { return null; } }
  var off = !CFG.supabaseUrl || !CFG.supabaseAnonKey || !window.ZiyaanDB || /^(localhost|127\.0\.0\.1|)$/.test(location.hostname);
  if (/[?&]notrack/.test(location.search)) ls('ziyaan-notrack', '1');
  if (ls('ziyaan-notrack') === '1') off = true;
  try { for (var i = 0; i < localStorage.length; i++) { if (String(localStorage.key(i)).indexOf('ziyaan-auth-') === 0) off = true; } } catch (e) {}
  if (off) { window.zTrack = function () {}; return; }
  var db = window.ZiyaanDB.createClient(CFG.supabaseUrl, CFG.supabaseAnonKey, { auth: { persistSession: false } });
  var vid = ls('ziyaan-vid');
  if (!vid || vid.length < 6) { vid = Array.from({ length: 16 }, function () { return Math.floor(Math.random() * 16).toString(16); }).join(''); ls('ziyaan-vid', vid); }
  var ua = navigator.userAgent || '', device = /iPad|Tablet/i.test(ua) ? 'tablet' : /Mobi|Android|iPhone/i.test(ua) ? 'phone' : 'computer';
  var src = ss('ziyaan-src');
  if (!src) {
    var q = location.search.match(/[?&](?:ref|utm_source)=([^&#]+)/i), ref = '';
    if (q) ref = decodeURIComponent(q[1]).toLowerCase();
    else { try { var h = new URL(document.referrer).hostname.replace(/^www\./, ''); if (h && h !== location.hostname) ref = h; } catch (e) {} }
    var map = [[/whatsapp|wa\.me/, 'whatsapp'], [/instagram/, 'instagram'], [/facebook|fb\.|messenger/, 'facebook'], [/tiktok/, 'tiktok'], [/google/, 'google'], [/twitter|x\.com|t\.co$/, 'x / twitter'], [/bing/, 'bing']];
    src = ref ? ref.slice(0, 40) : 'direct'; map.forEach(function (m) { if (m[0].test(ref)) src = m[1]; });
    ss('ziyaan-src', src);
  }
  var seen = {};
  window.zTrack = function (event, product, detail) {
    var key = event + '|' + (product || '') + '|' + (detail || '');
    if ((event === 'story_open' || event === 'search') && seen[key]) return; seen[key] = 1;
    db.logEvent('site_events', { visitor_id: vid, event: event, product: product ? String(product).slice(0, 160) : null,
      detail: detail ? String(detail).slice(0, 160) : null, source: src, device: device });
  };
})();
