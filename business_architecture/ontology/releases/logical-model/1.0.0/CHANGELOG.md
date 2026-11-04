# logical-model

## 1.0.0 (2026-11-03)

- [major] **First release.** The module's vocabulary (`lm:LogicalModel` and four annotation properties) and shapes, with 1 logical model: `customer-logical-model`. Each model is two graphs: ER Studio's export as it is, in ER Studio's namespace (`<model>.erstudio.ttl`), and the annotation layer that links its entities to `party`, `system` and `data-product` (`<model>.layer.ttl`). The files the models were built from are listed, with their SHA-256, under `augment` in `manifest.json` (the decision of 2026-11-02).
