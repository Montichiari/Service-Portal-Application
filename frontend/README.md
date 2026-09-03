# Service Portal — Frontend

React + TypeScript + Vite skeleton (`react-ts` template) with `react-router-dom`.

## Requirements

- Node.js 20.19+ / 22.12+ (Vite 8 requirement)

## Install

```powershell
cd frontend
npm install
```

## Configure

```powershell
copy .env.example .env         # Windows
# cp .env.example .env         # macOS / Linux
```

`VITE_API_URL` points the frontend at the backend (default `http://localhost:8000`).

## Run

```powershell
npm run dev
```

Vite serves the app at http://localhost:5173. The `/` route renders "Service Portal".

## Other scripts

```powershell
npm run build      # type-check + production build to dist/
npm run preview    # serve the production build locally
npm run lint       # oxlint
```
