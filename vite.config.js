import { defineConfig } from 'vite';

export default defineConfig({
  // Keep the unrelated Newton web simulator out of the Windows release
  // directory used by PyInstaller (dist/OpenRGBTempSync).
  build: {
    outDir: 'web-dist',
    emptyOutDir: true
  },
  server: {
    port: 3000,
    open: true
  },
  test: {
    environment: 'jsdom',
    globals: true
  }
});
