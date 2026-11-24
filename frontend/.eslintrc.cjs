module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh'],
  rules: {
    // Warn on components that can't be hot-reloaded cleanly
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    // Disallow `any` — use proper types
    '@typescript-eslint/no-explicit-any': 'error',
    // Unused vars are errors (TypeScript catches these anyway, but keep for clarity)
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    // Prefer const
    'prefer-const': 'error',
  },
}
