import { ImageResponse } from "next/og";

// Same file-convention approach as icon.tsx, at the 180x180 size iOS
// expects for "Add to Home Screen" -- see that file for the color/shape
// rationale (mirrors StationMap.tsx's "plenty of bikes" marker).
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
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
        }}
      >
        <div
          style={{
            width: 112,
            height: 112,
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(47, 174, 102, 0.28)",
          }}
        >
          <div
            style={{
              width: 62,
              height: 62,
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
