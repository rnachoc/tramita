// Development proxy for `npm start`: /api goes to the core with the REVIEWER key taken from the
// environment (TRAMITA_CONSOLE_API_KEY), so the key never reaches the browser.
export default {
  '/api': {
    target: process.env.TRAMITA_CORE_URL ?? 'http://localhost:8080',
    changeOrigin: true,
    headers: { 'X-Api-Key': process.env.TRAMITA_CONSOLE_API_KEY ?? '' },
  },
};
