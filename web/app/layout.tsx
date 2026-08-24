import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ecobici Pulse — CDMX bike-share, live",
  description:
    "Real-time occupancy map of Mexico City's Ecobici bike-share stations, streamed through Kafka into a live-updating map.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
