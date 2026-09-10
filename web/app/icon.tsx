import { ImageResponse } from "next/og";

// Next's file-convention favicon -- no <link rel="icon"> needed in
// layout.tsx's metadata, this file alone gets picked up and served at
// /icon. Generated rather than a static PNG so it stays a single source
// of truth with the map's own station-marker styling below, instead of a
// hand-exported image quietly drifting from it.
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

// Echoes globals.css's --color-paper background and --color-low marker
// color (StationMap.tsx's "plenty of bikes" dot) rather than inventing new
// brand colors, so the tab icon reads as the same "live station" mark
// used on the map itself, just with the pulse permanently on "healthy".
export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0c1117",
          borderRadius: 7,
        }}
      >
        <div
          style={{
            width: 20,
            height: 20,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(47, 174, 102, 0.28)",
          }}
        >
          <div
            style={{
              width: 11,
              height: 11,
              borderRadius: "50%",
              background: "#2fae66",
            }}
          />
        </div>
      </div>
    ),
    { ...size }
  );
}
