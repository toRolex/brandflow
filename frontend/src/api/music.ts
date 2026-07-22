import type { MusicTrack } from "../types/music";
import { request } from "./core";

export const listMusic = () => request<{ tracks: MusicTrack[] }>("/api/music");
