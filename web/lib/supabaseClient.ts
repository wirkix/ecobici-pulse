import { createClient } from "@supabase/supabase-js";

// Publishable client-side client, same pattern as professional-website's
// src/lib/supabase/client.ts -- anon key only, RLS on `station_snapshot`
// restricts it to read-only (see db/supabase/schema.sql).
export const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export type StationSnapshot = {
  station_id: string;
  name: string;
  lat: number;
  lon: number;
  capacity: number;
  bikes_available: number;
  docks_available: number;
  occupancy_pct: number;
  is_renting: boolean;
  is_returning: boolean;
  updated_at: string;
};
