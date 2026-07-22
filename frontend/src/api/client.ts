import * as assetLibrary from "./assetLibrary";
import * as assets from "./assets";
import * as config from "./config";
import * as coverTitle from "./coverTitle";
import * as exportTask from "./export";
import * as jobs from "./jobs";
import * as knowledge from "./knowledge";
import * as metrics from "./metrics";
import * as music from "./music";
import * as productConfig from "./productConfig";
import * as products from "./products";
import * as projects from "./projects";
import * as reviews from "./reviews";
import * as templates from "./templates";
import * as tts from "./tts";

/**
 * Backward-compatible API client barrel.
 *
 * New code can import directly from domain modules (e.g. `../api/jobs`).
 * Existing consumers continue to use `import { api } from "../api/client"`.
 */
export const api = {
	...projects,
	...assets,
	...assetLibrary,
	...jobs,
	...reviews,
	...config,
	...productConfig,
	...products,
	...tts,
	...music,
	...coverTitle,
	...metrics,
	...templates,
	...exportTask,
	...knowledge,
};

export type ApiClient = typeof api;
