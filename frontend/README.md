# TomBot frontend

React 19 + TypeScript + Tailwind CSS 4, built with Vite. Flask serves the build
output (`dist/`) under `/static`; this folder is only needed to change the UI.

```
npm ci            # install (Node 22)
npm run dev       # dev server on :5173 with hot reload; proxies /api and /media to :8080
npm run build     # typecheck + production build into dist/
npm run watch     # rebuild dist/ on every save (what `make dev` runs)
npm run check     # typecheck + eslint + prettier --check   (CI runs this)
npm run format    # prettier --write, including Tailwind class order
```

From the repo root, `make run` / `make dev` / `make frontend` wrap these. The
folder layout and the conventions are in the root `CLAUDE.md` under "Frontend".
