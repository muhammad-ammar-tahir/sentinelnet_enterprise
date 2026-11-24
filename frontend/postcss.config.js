/**
 * PostCSS configuration
 * Required by Tailwind CSS for its JIT compilation pipeline.
 * autoprefixer adds vendor prefixes for cross-browser compatibility.
 */
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
