import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig} from 'vite';

export default defineConfig(() => {
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
        '@packages/core': path.resolve(__dirname, 'packages/core/src'),
        '@packages/rag': path.resolve(__dirname, 'packages/rag/src'),
        '@packages/model-gateway': path.resolve(__dirname, 'packages/model-gateway/src'),
        '@packages/prompt': path.resolve(__dirname, 'packages/prompt/src'),
        '@packages/agent': path.resolve(__dirname, 'packages/agent/src'),
      },
    },
    server: {
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify—file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Disable file watching when DISABLE_HMR is true to save CPU during agent edits.
      watch: process.env.DISABLE_HMR === 'true' ? null : {},
    },
  };
});
