export default {
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["recharts"],
          utilities: ["axios", "lucide-react"]
        }
      }
    }
  }
};
