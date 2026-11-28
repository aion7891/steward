# Frontend

React 18 + Vite 5, plain JavaScript, no CSS framework. Built into static files served by nginx.

## Code map

```
frontend/
├── Dockerfile · nginx.conf · .dockerignore      # node:22 build → nginx-unprivileged:1.27 (uid 101)
├── vite.config.js                               # dev proxy /steward → STEWARD_API_URL (default :7777)
└── src/
    ├── main.jsx · App.jsx                       # router; each page lazy-loaded
    ├── api/client.js                            # fetch wrapper: timeouts, FastAPI errors → ApiError
    ├── api/steward.js                           # ONE function per API route
    ├── hooks/useApi.js · usePolling.js          # load-once / poll-until-done with loading+error
    ├── chat/ChatProvider.jsx                    # chat state ABOVE the routes: one job per chat, 1 s polling, Stop, recent chats (+ running), deleteChat
    ├── utils/format.js · chatStorage.js         # sizes, times, paths · chat history + session id
    ├── utils/chatJobs.js · chatInsights.js      # job → message, saved chats · step summary, suggestion prompts
    ├── styles/tokens.css                        # design tokens (light + dark)
    ├── styles/base.css · components.css         # layout + shared components
    ├── styles/{dashboard,scan,chat,chat-panel,reports,settings}.css   # page-specific
    ├── components/layout/                       # AppShell (health polling, sidebar collapsed flag), Sidebar (collapses to icons), RecentChats (working dots, delete; compact), TopBar (badge → /dashboard#todo), PageHeader
    ├── components/chat/                         # ChatHome, Composer (Send ⇄ Stop), MessageList, StepTrail, FolderCard, ChatPanel, ApprovalCard
    ├── components/settings/DataSettings.jsx     # Data & cleanup: clear / delete for good (type DELETE) / backups (helpers in dataCleanup.js)
    ├── components/settings/EverythingPanel.jsx  # Delete everything (+ ConfirmBox.jsx, shared confirm with typed DELETE)
    ├── utils/layoutPrefs.js · todoView.js       # remembered sidebar/To-do choices (safe localStorage) · first 10 + summary
    ├── utils/dataEvents.js                      # steward:data-changed → AppShell reloads health (badge) at once
    ├── components/ui/                           # Card, Button, Badge, StatCard, Alert, EmptyState, Spinner
    ├── components/{dashboard,scan,chat,reports,settings}/  # page parts
    └── pages/{Dashboard,Scan,Chat,Reports,Settings}Page.jsx
```

## Patterns to follow

| Pattern | Why |
|:--|:--|
| Call the API only through `src/api/steward.js` | One place for every URL and body |
| Show `error.message` from `ApiError` directly | The API already writes user-friendly messages |
| `useApi(loader, deps)` for page data, `usePolling(loader, ms, enabled)` for jobs/health | Consistent loading/error state; polling stops when `enabled` turns false |
| Colours/spacing only via CSS variables in `tokens.css` | Dark mode works automatically |
| Keep logic in small exported helpers (`describeResult`, `stepsFor`, `pickFormat`, `replyToMessage`) and test them | Vitest runs in Node without a DOM |
| Never render document text as HTML | Markdown via `react-markdown` with `skipHtml`; links/images neutralized in chat; reports in `<iframe sandbox="">` |

## Design system

- Palette (0.12, neumorphism): `#E8E8E8` page (`--color-bg`), `#FFFFFF` cards (`--color-surface`),
  `#D0D0D0` lines (`--color-border`), `#C8E0F4` accent fill (`--color-accent`, text `--color-on-accent`),
  `#F5E0E8` approvals/warnings (`--color-warning-soft`). Light accents are surfaces only; text on
  them uses deeper shades of the same hue. Every text pair is at least 4.5:1 (light and dark).
- Tokens: `--color-brand` (deeper blue for lines, links, focus, progress), surfaces, text, status
  (`success/warning/danger/info` + `-soft`, `--color-on-status`), chart colours, spacing
  `--space-1…10`, radii, soft shadows `--shadow-sm|md|inset`. Dark values in
  `@media (prefers-color-scheme: dark)`.
- Components: `.card`, `.btn--primary|secondary|ghost|danger`, `.badge--…`, `.alert--…`, `.stat`,
  `.switch`, `.segmented`, `.input`, `.chip`.
- System font stack: no web fonts, works offline.

## How to add a page (example: "Recycle bin")

1. **API**: add a route in `steward/web_routes.py` (or a new `*_routes`/service module if it grows),
   test it in `tests/`.
2. **Client**: add `export function getRecycleBin() { return request("/steward/recycle"); }` to
   `src/api/steward.js`.
3. **Page**: create `src/pages/RecyclePage.jsx`:
   ```jsx
   import { getRecycleBin } from "../api/steward.js";
   import PageHeader from "../components/layout/PageHeader.jsx";
   import Alert from "../components/ui/Alert.jsx";
   import { Loading } from "../components/ui/Spinner.jsx";
   import { useApi } from "../hooks/useApi.js";

   export default function RecyclePage() {
     const { data, error, loading } = useApi(getRecycleBin, []);
     return (
       <>
         <PageHeader title="Recycle bin" subtitle="Files Steward moved aside." />
         {error && <Alert tone="danger" error={error} />}
         {loading && !data ? <Loading /> : <pre>{JSON.stringify(data, null, 2)}</pre>}
       </>
     );
   }
   ```
4. **Route**: in `src/App.jsx` add `const RecyclePage = lazy(() => import("./pages/RecyclePage.jsx"));`
   and `<Route path="/recycle" element={<Page><RecyclePage /></Page>} />`.
5. **Nav**: add `{ to: "/recycle", label: "Recycle bin", icon: Trash2 }` to `LINKS` in `Sidebar.jsx`.
6. **Styles**: page-only CSS in `src/styles/recycle.css`, imported by the page.
7. **Check**: `npm run build && npm test`, then look at it in the browser (light + dark).

> Naming gotcha: the root `.gitignore` used to ignore any folder called `reports/`, `data/`,
> `knowledge/`… anywhere. It's now anchored to the repo root (`/reports/`), so component folders
> with those names are fine.

## Dependencies (pinned, each release ≥ 2 weeks old when added)

`react 18.3.1`, `react-dom 18.3.1`, `react-router-dom 6.30.6`, `recharts 3.10.1`,
`react-markdown 9.1.0`, `lucide-react 1.69.0`; dev: `vite 5.4.21`, `@vitejs/plugin-react 4.7.0`, `vitest 2.1.9`.
