import StationMap from "@/components/StationMap";

export default function Home() {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-line px-5 py-3">
        <div>
          <h1 className="text-lg font-semibold">Ecobici Pulse</h1>
          <p className="text-sm text-muted">
            Mexico City bike-share, live — polled every 60s through Kafka.
          </p>
        </div>
        <a
          href="https://github.com/wirkix/ecobici-pulse"
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-muted hover:text-ink"
        >
          GitHub →
        </a>
      </header>
      <main className="flex-1">
        <StationMap />
      </main>
    </div>
  );
}
