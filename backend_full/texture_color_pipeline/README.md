# Texture-First, Source-Weighted Color Backend

This package adds a parallel experimental backend pipeline for the Schattdecor mini program.

The order is strict:

1. texture stage: combine scan and realshot texture scores by configurable source weights;
2. keep only the top texture families;
3. color stage: inside those families only, combine scan and realshot color scores by configurable source weights;
4. optionally use `metric_head.pt` for the texture stage;
5. expose the flow through `POST /recognize-texture-color`.

Main Chinese documentation:

```text
texture_color_pipeline\纹理优先颜色重排后端全流程说明.md
```

Quick commands:

```powershell
cd "D:\夏特项目\ImageClaster\部署 4.0"
python texture_color_pipeline\build_texture_color_gallery.py --limit 2
python texture_color_pipeline\train_texture_metric.py --feature-root data\texture_color_features
python texture_color_pipeline\recognize_texture_color.py --image "D:\path\to\photo.jpg"
uvicorn texture_color_pipeline.backend_texture_color:app --host 0.0.0.0 --port 8001
```

