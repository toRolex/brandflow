# Asset Library, AI Classification, and TTS Stabilization Spec

Status: Draft for implementation PR
Date: 2026-07-13
Owner: Codex-assisted triage
Scope: Brandflow asset library, category AI suggestions, asset indexing confidence, visible batch selection, and TTS voice selection

## Background

The current UI exposes two asset-library experiences:

- The global library at `/assets`, backed by the shared asset library.
- The project workbench tab labeled "智能素材库", rendered with a `projectId` and backed by a project-local asset database.

The user-visible result is confusing: categories exist but filter counts can be zero, clips indexed through fallback classification show `0%` confidence, the two libraries do not share data, visible select-all is missing, TTS voices are not available during job creation, and AI category suggestions are unavailable.

This spec turns those symptoms into an implementation plan.

## Evidence

### Split Asset Library Data Sources

- `frontend/src/App.tsx` renders `/assets` with `SmartAssetLibrary` and no `projectId`.
- `frontend/src/components/ProjectTabs.tsx:80` renders `<SmartAssetLibrary projectId={projectId} />` inside the project workbench.
- `frontend/src/api/client.ts:51` calls `/api/projects/{projectId}/assets/indexed`.
- `frontend/src/api/client.ts:96` calls `/api/assets/indexed`.
- `apps/control_plane/routes/api_projects.py:107` stores project asset indexes at `project_dir / "asset_index.db"`.
- `packages/file_store/paths.py:18` stores the shared asset index at `workspace/shared_assets/asset_index.db`.
- `apps/control_plane/routes/api_assets.py:579` already contains a migration route that copies project assets into the shared library.

### Category Filtering and Counting Mismatch

- `frontend/src/pages/SmartAssetLibrary.tsx` loads configured categories from `/api/assets/categories`.
- The same component counts categories from locally loaded assets after product filtering.
- The project endpoint `apps/control_plane/routes/api_projects.py:111` accepts `category` and `q`, but not `product`.
- The shared endpoint `apps/control_plane/routes/api_assets.py:116` accepts `category`, `q`, and `product`.
- Screenshot evidence shows configured categories such as "挖出来", "产品特写", "产品展示", "松茸美食", and "处理松茸", while cards are mostly categorized as "产品特写" with `0%` confidence.

### Vision Fallback and Zero Confidence

- `packages/pipeline_services/asset_library/indexer.py:262` classifies a frame through `VisionClient`.
- `packages/pipeline_services/asset_library/indexer.py:271` logs vision classification failure and falls back to "产品特写".
- `packages/pipeline_services/asset_library/indexer.py:273` returns fallback confidence `0.0`.
- This makes backend failure look like a valid categorized clip in the UI.

### Select-All Is Hidden

- `frontend/src/components/AssetGrid.tsx:18` implements `Ctrl/Cmd + A` selection only when the grid is focused.
- There is no visible "select all current results" control in the asset-library toolbar or batch action bar.

### TTS Voice Selection Is Not Connected to Job Creation

- `frontend/src/api/client.ts:338` exposes `getTTSVoices`.
- `frontend/src/components/CreateJobForm.tsx:396` only lets users choose between `tts` and `upload`.
- `frontend/src/api/client.ts:168` sends `createJob` payloads without `tts_model`, `tts_voice`, or a per-job TTS override.
- `packages/pipeline_services/phase_orchestrator.py` resolves TTS config globally/product-wide, not from job-level options.

### AI Category Suggestions Contract Mismatch

- `apps/control_plane/routes/category_suggestion.py:41` requires a `SuggestRequest` body.
- `frontend/src/api/client.ts:486` sends POST `/api/assets/categories/suggest` without a body.
- The backend response model returns `categories`; the frontend client type expects `suggestions`.
- This likely causes 422 responses or unusable response data.

## Goals

1. Make there be one obvious smart asset library source of truth.
2. Preserve existing project asset data through migration or compatibility reads.
3. Make category counts, filters, and configured category names consistent.
4. Prevent silent AI classification failure from appearing as successful classification.
5. Add visible selection controls for batch asset operations.
6. Expose TTS voice selection where users create jobs.
7. Restore AI category suggestion by aligning request and response contracts.

## Non-Goals

- Redesign the whole project workbench.
- Replace the current category-management system.
- Replace the current TTS provider architecture.
- Implement a new visual model provider.
- Reclassify all historical assets automatically without explicit user action.

## Proposed Solution

Use the shared asset library as the single source of truth for "智能素材库".

The project workbench should either hide the duplicate "智能素材库" tab or route it to the same shared library filtered by the active product. Project-only scene uploads should remain separate under "场景素材".

Classification failures should become explicit states, not successful clips with `0%` confidence. The UI should make these clips reviewable and batch-correctable.

## Requirements

### R1. Unify Smart Asset Library Source of Truth

- Keep `/assets` backed by `/api/assets/indexed`.
- Remove, hide, or repurpose the project workbench "智能素材库" tab.
- Recommended default: hide the project-scoped smart asset tab and keep only "场景素材" in the project workbench.
- If the tab remains, render the shared library without `projectId` and initialize the product filter from the active project product.
- Run or expose a one-time migration from project `asset_index.db` files into `workspace/shared_assets/asset_index.db`.
- Do not delete project-local DB files during the initial rollout.

### R2. Make Category Logic Consistent

- Server-side asset queries must support `product`, `category`, and `q` consistently.
- Category dropdown counts must be derived from the same result set as the displayed assets.
- Show configured categories even when empty.
- Show an additional "未映射/历史分类" group when assets have categories not present in current config.
- Provide a batch reassignment action for selected assets.
- When a category is renamed or removed, do not orphan historical clips silently.

### R3. Make Vision Classification Failures Explicit

- Validate Vision provider, endpoint, model, and API key before indexing starts.
- If validation fails, stop indexing with a clear UI error.
- If one clip fails classification, mark it with a dedicated failure signal instead of a valid category with `confidence = 0`.
- Add a field or tag equivalent to `classification_status`: `classified`, `fallback`, `failed`, or `needs_review`.
- Preserve the raw error message in logs and expose a user-safe summary in index progress UI.
- Keep fallback assignment available only as a user-visible recovery path.

### R4. Add Visible Select-All

- Add a checkbox or button near asset filters:
  - "全选当前筛选结果"
  - "清空选择"
- The selected count must update immediately.
- Batch actions must apply only to selected IDs.
- If future pagination is added, distinguish "current page" from "all filtered results".

### R5. Expose TTS Voice Selection During Job Creation

- Load `/api/tts/voices` when audio source is `tts`.
- Show current global/product TTS model and voice.
- Provide a voice selector in `CreateJobForm` and batch job creation if batch supports TTS.
- Extend create-job payloads with optional job-level TTS overrides:
  - `tts_model`
  - `tts_voice`
  - optional style/instructions fields only if already supported by provider config.
- Backend job creation should persist those overrides in the job manifest.
- TTS generation should merge config in this order:
  1. provider defaults
  2. global/product TTS config
  3. job-level overrides

### R6. Fix AI Category Suggestions

- Make backend body optional: `body: SuggestRequest = SuggestRequest()`, or send `{}` from the frontend.
- Align response contract:
  - Preferred: frontend expects `categories`.
  - Compatibility option: backend returns both `categories` and `suggestions` for one release.
- Surface backend `errors` in the Category Manager UI.
- Ensure suggestions sample from the shared source of truth after R1.

## API and Data Contract Changes

### Asset Records

Add optional fields without breaking older records:

```json
{
  "classification_status": "classified | fallback | failed | needs_review",
  "classification_error": "string | null"
}
```

If the DB migration is deferred, these can be emitted as derived response fields first.

### Create Job

Extend create-job request bodies:

```json
{
  "audio_source": "tts",
  "tts_model": "mimo-v2.5-tts",
  "tts_voice": "Mia"
}
```

These fields are optional and should fall back to existing config behavior.

### Category Suggestion

Preferred response:

```json
{
  "categories": [],
  "sampled_assets": 0,
  "model_used": "",
  "descriptions": [],
  "errors": []
}
```

## Migration Plan

1. Run the existing shared asset migration endpoint or equivalent CLI once per deployment.
2. Keep project-local `asset_index.db` files read-only for rollback.
3. Verify migrated clip counts by product and category.
4. Hide or reroute project-local smart asset UI only after migration verification.
5. Add a manual "重新分类/批量归类" path for clips imported with fallback categories.

## Acceptance Criteria

- The app presents one smart asset library for reusable clips.
- Project pages no longer show a second disconnected smart asset library.
- Selecting a configured category with assets reliably displays those assets.
- Assets whose category is not in current config remain visible under "未映射/历史分类".
- New indexing fails fast when Vision config is missing or invalid.
- A Vision failure is visible as a reviewable state, not only `产品特写 / 0%`.
- Users can click a visible select-all control and batch edit selected assets.
- Job creation displays available TTS voices for the selected provider.
- A selected TTS voice is used when generating audio for that job.
- AI category suggestions return without 422 and populate the Category Manager UI.

## Validation Plan

- Frontend unit tests:
  - `SmartAssetLibrary` category counts include configured and unmapped categories.
  - visible select-all selects filtered assets.
  - `CreateJobForm` loads and submits selected TTS voice.
  - `CategoryManager` consumes `categories` response and renders errors.
- Backend tests:
  - shared asset endpoint filters by product/category/q.
  - category suggestion POST accepts empty body.
  - create job accepts optional TTS overrides.
  - indexer emits classification failure status when VisionClient fails.
- Manual checks:
  - open `/assets` and verify the 松茸 library count.
  - open a project page and verify there is no disconnected smart library.
  - run category suggestion from Category Manager.
  - create a TTS job with a non-default voice and verify generated audio metadata/logs.

## Suggested Implementation Order

1. Fix AI category suggestion contract because it is small and high-confidence.
2. Add visible select-all because it is isolated frontend work.
3. Add TTS voice display and job-level override fields.
4. Unify or hide the duplicate project smart asset library.
5. Add category unmapped handling and batch reassignment polish.
6. Make Vision fallback explicit and add indexing validation.
7. Add or update tests after each step.

## Suggested PR Description

### Summary

- Document and prepare the stabilization plan for Brandflow smart asset library, AI category suggestions, asset classification fallback, select-all, and TTS voice selection.
- Identify the shared asset library as the intended source of truth and define migration/compatibility requirements.
- Define API contract changes for category suggestions, TTS overrides, and classification failure state.

### Testing

- Documentation-only PR: no runtime tests required.
- Skill validation completed for newly added local workflow skills outside the repository.

### Follow-up Implementation Issues

1. Fix `/api/assets/categories/suggest` request/response contract.
2. Add visible asset select-all controls.
3. Add TTS voice selector to job creation and persist overrides.
4. Hide or unify project-scoped smart asset library.
5. Add unmapped category handling and migration verification.
6. Replace silent Vision fallback with explicit classification failure state.
