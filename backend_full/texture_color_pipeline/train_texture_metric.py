from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import List, Tuple

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
import torch.nn.functional as F

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from texture_color_pipeline.config import PipelineConfig, pattern_family_id
from texture_color_pipeline.gallery import load_json, load_source_feature_banks


class ProjectionHead(nn.Module):
    def __init__(self, input_dim: int, embedding_dim: int = 256) -> None:
        super().__init__()
        hidden = max(embedding_dim * 2, input_dim // 2)
        self.layers = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, embedding_dim),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return F.normalize(self.layers(features), p=2, dim=1)


def supervised_contrastive_loss(embeddings: torch.Tensor, labels: torch.Tensor, temperature: float = 0.07) -> torch.Tensor:
    logits = embeddings @ embeddings.T / temperature
    identity = torch.eye(labels.shape[0], dtype=torch.bool, device=labels.device)
    positive = labels[:, None].eq(labels[None, :]) & ~identity
    logits = logits.masked_fill(identity, -1e9)
    log_prob = logits - torch.logsumexp(logits, dim=1, keepdim=True)
    positive_count = positive.sum(dim=1)
    valid = positive_count > 0
    if not torch.any(valid):
        return torch.tensor(0.0, device=embeddings.device, requires_grad=True)
    mean_log_prob = (log_prob * positive).sum(dim=1)[valid] / positive_count[valid].float()
    return -mean_log_prob.mean()


def load_training_matrix(
    config: PipelineConfig,
    label_level: str,
    max_templates_per_pattern: int,
    seed: int,
) -> Tuple[torch.Tensor, torch.Tensor, List[str]]:
    source_banks = load_source_feature_banks(config)
    manifest = load_json(config.manifest_path) if config.manifest_path.exists() else {}
    rng = random.Random(seed)
    rows = []
    label_names = []
    label_to_index: dict[str, int] = {}
    classes = manifest.get("classes", {})
    for source, banks in source_banks.items():
        vit_bank = banks["vit"]
        conv_bank = banks["conv"]
        for pattern_id in sorted(set(vit_bank.keys()) & set(conv_bank.keys())):
            vit = vit_bank[pattern_id]
            conv = conv_bank[pattern_id]
            count = min(vit.shape[0], conv.shape[0])
            if count == 0:
                continue
            indices = list(range(count))
            rng.shuffle(indices)
            indices = indices[: min(max_templates_per_pattern, count)]
            combined = F.normalize(torch.cat([vit[indices], conv[indices]], dim=1), p=2, dim=1)
            if label_level == "pattern":
                label_name = pattern_id
            else:
                label_name = classes.get(pattern_id, {}).get("family_id") or pattern_family_id(pattern_id)
            if label_name not in label_to_index:
                label_to_index[label_name] = len(label_to_index)
                label_names.append(label_name)
            label = label_to_index[label_name]
            rows.append((combined, torch.full((combined.shape[0],), label, dtype=torch.long)))
    if not rows:
        raise RuntimeError("No paired ViT/ConvNeXt texture features found. Run build_texture_color_gallery.py first.")
    features = torch.cat([item[0] for item in rows], dim=0)
    labels = torch.cat([item[1] for item in rows], dim=0)
    return features, labels, label_names


def train_metric_head(
    config: PipelineConfig,
    output: Path,
    label_level: str = "family",
    embedding_dim: int = 256,
    max_templates_per_pattern: int = 256,
    batch_size: int = 256,
    epochs: int = 30,
    learning_rate: float = 1e-3,
    seed: int = 42,
) -> dict:
    torch.manual_seed(seed)
    features, labels, label_names = load_training_matrix(config, label_level, max_templates_per_pattern, seed)
    dataset = TensorDataset(features, labels)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=False)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ProjectionHead(features.shape[1], embedding_dim=embedding_dim).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)
    history = []
    for epoch in range(1, epochs + 1):
        model.train()
        losses = []
        for batch_features, batch_labels in loader:
            batch_features = batch_features.to(device)
            batch_labels = batch_labels.to(device)
            embeddings = model(batch_features)
            loss = supervised_contrastive_loss(embeddings, batch_labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(float(loss.item()))
        mean_loss = sum(losses) / max(1, len(losses))
        history.append({"epoch": epoch, "loss": mean_loss})
        print(f"epoch {epoch:03d} loss={mean_loss:.4f}")

    output.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "projection_state": model.state_dict(),
        "input_dim": int(features.shape[1]),
        "embedding_dim": embedding_dim,
        "label_level": label_level,
        "label_names": label_names,
        "config": {
            "feature_root": str(config.output_root),
            "scan_root": str(config.scan_root),
            "realshot_root": str(config.realshot_root),
            "max_templates_per_pattern": max_templates_per_pattern,
            "batch_size": batch_size,
            "epochs": epochs,
            "learning_rate": learning_rate,
        },
        "history": history,
    }
    torch.save(checkpoint, output)
    (output.parent / "metric_training_history.json").write_text(
        json.dumps({"history": history, "labels": label_names}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Metric head written: {output}")
    return checkpoint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a texture metric projection head from precomputed features.")
    parser.add_argument("--feature-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--label-level", choices=["family", "pattern"], default="family")
    parser.add_argument("--embedding-dim", type=int, default=256)
    parser.add_argument("--max-templates-per-pattern", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PipelineConfig(output_root=args.feature_root.resolve() if args.feature_root else PipelineConfig().output_root)
    output = args.output.resolve() if args.output else config.metric_head_path
    train_metric_head(
        config=config,
        output=output,
        label_level=args.label_level,
        embedding_dim=args.embedding_dim,
        max_templates_per_pattern=args.max_templates_per_pattern,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
