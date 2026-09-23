// maplibre-gl v6 runs its tile parsing in a separate ES-module worker
// (maplibre-gl-worker.mjs, which imports maplibre-gl-shared.mjs). Next's
// bundler doesn't emit that worker, so serve both files as static assets
// and point maplibre at them with setWorkerUrl() (see StationMap.tsx).
// Copied on every dev/build so they always match the installed version.
import { copyFileSync, mkdirSync } from "node:fs";

const src = "node_modules/maplibre-gl/dist";
const dest = "public/maplibre";
mkdirSync(dest, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) {
  copyFileSync(`${src}/${f}`, `${dest}/${f}`);
}
