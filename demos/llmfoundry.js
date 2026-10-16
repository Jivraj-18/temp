// Shared LLM Foundry token helper for all demos.
// The token is entered once on the home page and kept in this browser's localStorage.
// GitHub Pages serves every demo from the same origin, so each demo can read it.
(function () {
  const KEY = "llmfoundryToken";
  const BASE = "https://llmfoundry.straive.com";
  const read = () => { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } };

  window.llmFoundry = {
    base: BASE,
    getToken: read,
    hasToken: () => !!read(),
    setToken(token) { try { localStorage.setItem(KEY, token.trim()); } catch {} },
    clearToken() { try { localStorage.removeItem(KEY); } catch {} },
    // fetch() against LLM Foundry with the stored token, e.g.
    // llmFoundry.fetch("/openai/v1/chat/completions", { method: "POST", body: JSON.stringify({...}) })
    fetch(path, options = {}) {
      const token = read();
      if (!token) return Promise.reject(new Error("No LLM Foundry token. Add one on the demos home page."));
      const headers = { "Content-Type": "application/json", ...(options.headers || {}), Authorization: `Bearer ${token}:strategic-data-demos` };
      return fetch(BASE + path, { ...options, headers });
    },
  };
})();
