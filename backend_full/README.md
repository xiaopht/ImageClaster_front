# Full Backend Source

This folder mirrors the production backend source code used by the deployed
Schattdecor Sense API.

It includes:

- `main_full.py`: FastAPI entrypoint for the full API.
- `xiaote_platform.py`: user, admin, pattern, PDF, OSS and database APIs.
- `texture_color_pipeline/`: texture-first, color-reranked recognition code.

It intentionally excludes:

- model weights
- extracted feature banks
- uploaded user images
- database files
- `.env` files and credentials

The current recognition flow is:

1. Use family-level texture retrieval to select the top texture families.
2. Use each selected family's representative texture score as the stage-2
   texture score.
3. Compute color score from available scan and realshot descriptors:
   `(w_scan * scan + w_realshot * realshot) / (w_scan + w_realshot)`.
4. Rank pattern variants by
   `stage2_texture_weight * family_texture_score + stage2_color_weight * color_score`.
