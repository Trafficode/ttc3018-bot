import {defineConfig} from 'vite';
export default defineConfig({
  esbuild: {jsx: 'automatic', jsxImportSource: 'preact'},
  server: {host: '127.0.0.1', proxy: {'/api': 'http://127.0.0.1:8766', '/camera': 'http://127.0.0.1:8766'}},
  build: {outDir: '../web', emptyOutDir: false, sourcemap: false,
    rollupOptions: {output: {entryFileNames: 'app.js',
      assetFileNames: asset => asset.names?.some(name => name.endsWith('.css')) ? 'style.css' : '[name][extname]'}}},
});
