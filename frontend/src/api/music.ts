import { request } from "./core";
import type { MusicTrack } from "../types/music";

export const listMusic = () =>
	request<{ tracks: MusicTrack[] }>("/api/music");
