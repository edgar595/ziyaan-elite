/* ==========================================================================
   Ziyaan Elite — tiny built-in database client (no outside downloads needed)
   Talks directly to Supabase (database, login and photo storage) using
   the browser's own fetch(). Replaces the external supabase-js library so
   the site works even on browsers or networks that block CDNs.
   ========================================================================== */
(function () {
  function createClient(baseUrl, anonKey, opts) {
    var noSession = !!(opts && opts.auth && opts.auth.persistSession === false);
    var URL_ = String(baseUrl).replace(/\/+$/, '');
    var KEY = 'ziyaan-auth-' + URL_.replace(/^https?:\/\//, '').split('.')[0];
    var listeners = [];

    /* ---------------- session storage ---------------- */
    function readSession() { if (noSession) return null; try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; } }
    function writeSession(s) { try { if (s) localStorage.setItem(KEY, JSON.stringify(s)); else localStorage.removeItem(KEY); } catch (e) {} }
    function emit(ev, s) { listeners.forEach(function (cb) { try { cb(ev, s); } catch (e) {} }); }
    function toSession(j) {
      return { access_token: j.access_token, refresh_token: j.refresh_token,
        expires_at: j.expires_at || Math.floor(Date.now() / 1000) + (j.expires_in || 3600), user: j.user };
    }
    async function parse(res) {
      var txt = await res.text(), body = null;
      try { body = txt ? JSON.parse(txt) : null; } catch (e) { body = txt; }
      if (!res.ok) {
        var msg = (body && (body.message || body.msg || body.error_description || body.error)) || ('Request failed (' + res.status + ')');
        return { data: null, error: { message: String(msg), status: res.status, code: body && body.code } };
      }
      return { data: body, error: null };
    }
    var refreshing = null;
    async function getSession() {
      var s = readSession();
      if (!s) return null;
      if (s.expires_at && s.expires_at - 60 > Date.now() / 1000) return s;
      if (!s.refresh_token) { writeSession(null); return null; }
      if (!refreshing) refreshing = (async function () {
        try {
          var r = await parse(await fetch(URL_ + '/auth/v1/token?grant_type=refresh_token', {
            method: 'POST', headers: { apikey: anonKey, 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: s.refresh_token }) }));
          if (r.error) { writeSession(null); emit('SIGNED_OUT', null); return null; }
          var ns = toSession(r.data); writeSession(ns); emit('TOKEN_REFRESHED', ns); return ns;
        } catch (e) { return s; } finally { refreshing = null; }
      })();
      return refreshing;
    }
    async function headers(extra) {
      var s = await getSession();
      var h = { apikey: anonKey, Authorization: 'Bearer ' + (s ? s.access_token : anonKey) };
      for (var k in extra) h[k] = extra[k];
      return h;
    }

    /* ---------------- auth ---------------- */
    var auth = {
      getSession: async function () { return { data: { session: await getSession() }, error: null }; },
      signInWithPassword: async function (c) {
        try {
          var r = await parse(await fetch(URL_ + '/auth/v1/token?grant_type=password', {
            method: 'POST', headers: { apikey: anonKey, 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: c.email, password: c.password }) }));
          if (r.error) {
            if (r.error.status === 400) r.error.message = 'Invalid login credentials';
            return { data: null, error: r.error };
          }
          var s = toSession(r.data); writeSession(s); emit('SIGNED_IN', s);
          return { data: { session: s, user: s.user }, error: null };
        } catch (e) { return { data: null, error: { message: 'Failed to fetch' } }; }
      },
      signOut: async function () {
        var s = readSession();
        writeSession(null);
        if (s) { try { await fetch(URL_ + '/auth/v1/logout', { method: 'POST', headers: { apikey: anonKey, Authorization: 'Bearer ' + s.access_token } }); } catch (e) {} }
        emit('SIGNED_OUT', null);
        return { error: null };
      },
      onAuthStateChange: function (cb) { listeners.push(cb); return { data: { subscription: { unsubscribe: function () { listeners = listeners.filter(function (x) { return x !== cb; }); } } } }; }
    };

    /* ---------------- database queries ---------------- */
    function Query(table) { this.t = table; this.method = 'GET'; this.params = []; this.orders = []; this.body = null; this.wantRows = false; this.single = false; this.cols = '*'; }
    Query.prototype.select = function (cols) { if (this.method === 'GET') this.cols = cols || '*'; else this.wantRows = true; return this; };
    Query.prototype.eq = function (col, val) { this.params.push(encodeURIComponent(col) + '=eq.' + encodeURIComponent(val === null ? 'null' : String(val))); return this; };
    Query.prototype.order = function (col, o) { this.orders.push(col + '.' + (o && o.ascending === false ? 'desc' : 'asc')); return this; };
    Query.prototype.limit = function (n) { this.params.push('limit=' + n); return this; };
    Query.prototype.maybeSingle = function () { this.single = true; return this; };
    Query.prototype.insert = function (row) { this.method = 'POST'; this.body = row; return this; };
    Query.prototype.update = function (row) { this.method = 'PATCH'; this.body = row; return this; };
    Query.prototype.delete = function () { this.method = 'DELETE'; return this; };
    Query.prototype.run = async function () {
      var q = this.params.slice();
      if (this.method === 'GET') q.unshift('select=' + encodeURIComponent(this.cols));
      else if (this.wantRows) q.unshift('select=*');
      if (this.orders.length) q.push('order=' + this.orders.join(','));
      var h = await headers({ 'Content-Type': 'application/json' });
      if (this.method !== 'GET') h.Prefer = this.wantRows ? 'return=representation' : 'return=minimal';
      try {
        var r = await parse(await fetch(URL_ + '/rest/v1/' + this.t + (q.length ? '?' + q.join('&') : ''), {
          method: this.method, headers: h, body: this.body ? JSON.stringify(this.body) : undefined, cache: 'no-store' }));
        if (!r.error && this.single) r.data = Array.isArray(r.data) ? (r.data[0] || null) : r.data;
        if (!r.error && this.method !== 'GET' && !this.wantRows) r.data = null;
        return r;
      } catch (e) { return { data: null, error: { message: 'Failed to fetch' } }; }
    };
    Query.prototype.then = function (ok, bad) { return this.run().then(ok, bad); };

    /* ---------------- photo storage ---------------- */
    function encPath(p) { return String(p).split('/').map(encodeURIComponent).join('/'); }
    var storage = {
      from: function (bucket) {
        return {
          upload: async function (path, blob, opt) {
            opt = opt || {};
            var h = await headers({ 'Content-Type': opt.contentType || blob.type || 'application/octet-stream',
              'cache-control': 'max-age=' + (opt.cacheControl || '3600'), 'x-upsert': opt.upsert ? 'true' : 'false' });
            try {
              var r = await parse(await fetch(URL_ + '/storage/v1/object/' + bucket + '/' + encPath(path), { method: 'POST', headers: h, body: blob }));
              return r.error ? r : { data: { path: path }, error: null };
            } catch (e) { return { data: null, error: { message: 'Failed to fetch' } }; }
          },
          getPublicUrl: function (path) { return { data: { publicUrl: URL_ + '/storage/v1/object/public/' + bucket + '/' + encPath(path) } }; },
          remove: async function (paths) {
            var h = await headers({ 'Content-Type': 'application/json' });
            try { return await parse(await fetch(URL_ + '/storage/v1/object/' + bucket, { method: 'DELETE', headers: h, body: JSON.stringify({ prefixes: paths }) })); }
            catch (e) { return { data: null, error: { message: 'Failed to fetch' } }; }
          }
        };
      }
    };

    /* ---------------- server functions & quick event logging ---------------- */
    async function rpc(fn, args) {
      var h = await headers({ 'Content-Type': 'application/json' });
      try { return await parse(await fetch(URL_ + '/rest/v1/rpc/' + fn, { method: 'POST', headers: h, body: JSON.stringify(args || {}), cache: 'no-store' })); }
      catch (e) { return { data: null, error: { message: 'Failed to fetch' } }; }
    }
    function logEvent(table, row) {
      try {
        fetch(URL_ + '/rest/v1/' + table, { method: 'POST', keepalive: true,
          headers: { apikey: anonKey, Authorization: 'Bearer ' + anonKey, 'Content-Type': 'application/json', Prefer: 'return=minimal' },
          body: JSON.stringify(row) }).catch(function () {});
      } catch (e) {}
    }

    return { from: function (t) { return new Query(t); }, rpc: rpc, logEvent: logEvent, auth: auth, storage: storage };
  }
  window.ZiyaanDB = { createClient: createClient };
})();
